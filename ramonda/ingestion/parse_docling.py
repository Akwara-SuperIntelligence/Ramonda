"""Docling on a Drive file: OCR the pictures in a deck, or read a PDF."""

import io
import tempfile
import zipfile
from pathlib import Path

from . import connect_drive, parse_tika

OUT = connect_drive.OUT / "docling"


def image_names(names):
    suffixes = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
    return [
        name
        for name in names
        if name.startswith("ppt/media/") and name.lower().endswith(suffixes)
    ]


def _self_check():
    names = image_names(["ppt/slides/slide1.xml", "ppt/media/image1.png", "ppt/media/logo.JPG"])
    assert names == ["ppt/media/image1.png", "ppt/media/logo.JPG"]


def ocr_image(converter, path):
    document = converter.convert(str(path)).document
    return document.export_to_markdown().strip()


def write_pictures(converter, data):
    images = OUT / "images"
    images.mkdir(exist_ok=True)
    lines = []
    # shortcut: Docling does not OCR pictures inside a pptx, so each image is converted alone
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in image_names(archive.namelist()):
            dest = images / Path(name).name
            dest.write_bytes(archive.read(name))
            text = ocr_image(converter, dest)
            (images / f"{dest.stem}.md").write_text(text)
            lines.append(f"{dest.name}: {len(text)} chars")
    summary = "\n".join(lines) + "\n"
    (OUT / "summary.txt").write_text(summary)
    print(summary, end="")


def write_pdf(converter, data, stem):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(data)
        tmp.flush()
        text = converter.convert(tmp.name).document.export_to_markdown().strip()
    path = OUT / f"{stem}.md"
    path.write_text(text)
    print(f"{stem}: {len(text)} chars -> {path}")


def main():
    from docling.document_converter import DocumentConverter

    service = connect_drive.drive_service()
    OUT.mkdir(parents=True, exist_ok=True)
    converter = DocumentConverter()
    for name in parse_tika.FILES:
        item = parse_tika.find_file(service, name)
        data = parse_tika.file_bytes(service, item)
        if item["mimeType"] == parse_tika.PDF:
            write_pdf(converter, data, connect_drive.safe_name(item["name"], ""))
        else:
            write_pictures(converter, data)


if __name__ == "__main__":
    _self_check()
    main()
