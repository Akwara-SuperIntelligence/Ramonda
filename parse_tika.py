"""Send one Drive file through Tika and keep the text and the metadata."""

import io
import json
import subprocess
import time
import urllib.request

from googleapiclient.http import MediaIoBaseDownload

import connect_drive

NAME = "19th June 2026 - End-User Features & Applications_Robust Tech Template"
PDF_NAME = "laboratory proporsal st theresa-2.pdf"
FILES = (NAME, PDF_NAME)
SLIDES = "application/vnd.google-apps.presentation"
PDF = "application/pdf"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
CONTENT_KEYS = ("X-TIKA:content", "tk:content")


def split_rmeta(payload):
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError("Tika returned no document record.")
    record = payload[0]  # shortcut: main document only, keep later records when embedded pictures matter
    text = ""
    for key in CONTENT_KEYS:
        if record.get(key):
            text = str(record[key]).strip()
            break
    meta = {key: value for key, value in record.items() if key not in CONTENT_KEYS}
    return text, meta


def _self_check():
    text, meta = split_rmeta([{"tk:content": " hello ", "Content-Type": "application/pdf"}])
    assert text == "hello"
    assert meta == {"Content-Type": "application/pdf"}
    try:
        split_rmeta([])
    except ValueError:
        return
    raise AssertionError("empty Tika payload was accepted")


def find_file(service, name=NAME):
    # Shared-drive file. A My Drive query does not return it.
    escaped = name.replace("\\", "\\\\").replace("'", "\\'")
    result = (
        service.files()
        .list(
            q=f"name = '{escaped}' and trashed = false",
            pageSize=2,
            fields="files(id, name, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = result.get("files", [])
    if len(files) != 1:
        raise SystemExit(f"Expected one file named {name!r}, found {len(files)}.")
    return files[0]


def file_bytes(service, item):
    if item["mimeType"] == SLIDES:
        return export_pptx(service, item)
    if item["mimeType"] != PDF:
        raise SystemExit(f"{item['name']} is {item['mimeType']}.")
    request = service.files().get_media(fileId=item["id"])
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def export_pptx(service, item):
    if item["mimeType"] != SLIDES:
        raise SystemExit(f"{item['name']} is {item['mimeType']}, not a Google Slides file.")
    return (
        service.files()
        .export(fileId=item["id"], mimeType=PPTX)
        .execute()
    )


def tika_ready():
    try:
        urllib.request.urlopen("http://127.0.0.1:9998/version", timeout=2)
    except OSError:
        return False
    return True


def ensure_tika():
    # shortcut: local Docker Tika on port 9998, point this at the cluster when Tika is deployed
    if tika_ready():
        return
    started = subprocess.run(["docker", "start", "ramonda-tika"], capture_output=True)
    if started.returncode != 0:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                "ramonda-tika",
                "-p",
                "9998:9998",
                "apache/tika:latest",
            ],
            check=True,
        )
    for _ in range(60):
        if tika_ready():
            return
        time.sleep(1)
    raise SystemExit("Tika did not answer on port 9998.")


def tika_rmeta(data):
    request = urllib.request.Request(
        "http://127.0.0.1:9998/rmeta",
        data=data,
        method="PUT",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    ensure_tika()
    service = connect_drive.drive_service()
    connect_drive.OUT.mkdir(exist_ok=True)
    for name in FILES:
        item = find_file(service, name)
        text, meta = split_rmeta(tika_rmeta(file_bytes(service, item)))
        stem = connect_drive.safe_name(item["name"], "")
        text_path = connect_drive.OUT / f"{stem}.txt"
        meta_path = connect_drive.OUT / f"{stem}.meta.json"
        text_path.write_text(text)
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        print(f"Text {len(text)} chars -> {text_path}")
        print(f"Metadata {len(meta)} fields -> {meta_path}")


if __name__ == "__main__":
    _self_check()
    main()
