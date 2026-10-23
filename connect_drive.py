"""Sign in to Drive, list one folder, export one Doc and one Sheet."""

import io
import re
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

ROOT = Path(__file__).resolve().parent
CREDENTIALS = ROOT / "credentials.json"
TOKEN = ROOT / "token.json"
OUT = ROOT / "out"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
EXPORTS = {
    DOC: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    SHEET: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
}


def parent_from_arg(arg):
    if not arg:
        return "root"
    if "/folders/" in arg:
        arg = arg.split("/folders/", 1)[1].split("?", 1)[0].split("/", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", arg):
        sys.exit("Pass a Drive folder id or folder URL.")
    return arg


def safe_name(name, suffix):
    cleaned = "".join(c if c.isalnum() or c in " ._-" else "_" for c in name).strip(" .")
    return (cleaned[:80] or "file") + suffix


def _self_check():
    url = "https://drive.google.com/drive/folders/abc123?usp=sharing"
    assert parent_from_arg(None) == "root"
    assert parent_from_arg(url) == "abc123"
    assert parent_from_arg("abc123") == "abc123"
    assert safe_name("a/b", ".docx") == "a_b.docx"


def drive_service():
    if not CREDENTIALS.exists():
        sys.exit("credentials.json is missing from the project root.")
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES) if TOKEN.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds)


def list_children(service, parent):
    # shortcut: first 50 direct children only, page when a folder is larger than that
    query = f"'{parent}' in parents and trashed = false"
    result = (
        service.files()
        .list(
            q=query,
            pageSize=50,
            fields="nextPageToken, files(id, name, mimeType)",
            orderBy="folder,name",
        )
        .execute()
    )
    return result.get("files", []), bool(result.get("nextPageToken"))


def first_of_type(service, parent, mime):
    query = f"mimeType = '{mime}' and '{parent}' in parents and trashed = false"
    result = (
        service.files()
        .list(
            q=query,
            pageSize=1,
            fields="files(id, name, mimeType)",
            orderBy="modifiedTime desc",
        )
        .execute()
    )
    files = result.get("files", [])
    return files[0] if files else None


def export_file(service, item):
    mime, suffix = EXPORTS[item["mimeType"]]
    request = service.files().export_media(fileId=item["id"], mimeType=mime)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    OUT.mkdir(exist_ok=True)
    path = OUT / safe_name(item["name"], suffix)
    path.write_bytes(buffer.getvalue())
    return path


def main():
    parent = parent_from_arg(sys.argv[1] if len(sys.argv) > 1 else None)
    service = drive_service()
    try:
        files, more = list_children(service, parent)
        doc = first_of_type(service, parent, DOC)
        sheet = first_of_type(service, parent, SHEET)
    except HttpError as err:
        if err.resp.status == 403:
            sys.exit(
                "Drive refused the token. Enable the Drive API, add the "
                "drive.readonly scope, delete token.json, and run again."
            )
        raise
    print(f"Folder {parent}: {len(files)} file(s)" + (" (more not listed)" if more else ""))
    for item in files:
        print(f"{item['mimeType']}\t{item['name']}")
    # shortcut: this folder only, not subfolders, pass the nested folder url when docs live deeper
    for label, item in (("Doc", doc), ("Sheet", sheet)):
        if not item:
            print(f"No Google {label} directly in this folder.")
            continue
        path = export_file(service, item)
        print(f"Exported {item['name']} -> {path}")


if __name__ == "__main__":
    _self_check()
    main()
