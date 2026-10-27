"""Docling on a Drive file: OCR the pictures in a deck, or read a PDF."""

import io
import tempfile
import zipfile
from pathlib import Path

from . import connect_drive, intake, parse_tika

OUT = connect_drive.OUT / "docling"


def image_names(names, folder):
    suffixes = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
    return [
        name
        for name in names
        if name.startswith(folder) and name.lower().endswith(suffixes)
    ]


def pictures(data, folder):
    # A deck keeps its pictures in ppt/media, a Word file in word/media. A native Word chart is
    # chart XML and an embedded sheet, so it has no picture to OCR.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        charts = [n for n in names if n.startswith("word/charts/") and n.endswith(".xml")]
        return [(name, archive.read(name)) for name in image_names(names, folder)], charts


def _self_check():
    names = ["ppt/slides/slide1.xml", "ppt/media/image1.png", "ppt/media/logo.JPG"]
    assert image_names(names, "ppt/media/") == ["ppt/media/image1.png", "ppt/media/logo.JPG"]
    assert image_names(names, "word/media/") == []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/media/image1.png", b"x")
        archive.writestr("word/charts/chart1.xml", b"<c/>")
    found, charts = pictures(buffer.getvalue(), "word/media/")
    assert [name for name, _ in found] == ["word/media/image1.png"]
    assert charts == ["word/charts/chart1.xml"]


def ocr_image(converter, path):
    document = converter.convert(str(path)).document
    return document.export_to_markdown().strip()


def write_pictures(converter, found, stem):
    images = OUT / "images"
    images.mkdir(exist_ok=True)
    lines = []
    texts = []
    # shortcut: Docling does not OCR pictures inside a zip, so each image is converted alone
    for name, raw in found:
        dest = images / Path(name).name
        dest.write_bytes(raw)
        text = ocr_image(converter, dest)
        texts.append(text)
        lines.append(f"{dest.name}: {len(text)} chars")
    # One file per document: the image folder is shared by every file in the intake.
    (OUT / f"{stem}.images.md").write_text("\n\n".join(texts))
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
    service = connect_drive.drive_service()
    OUT.mkdir(parents=True, exist_ok=True)
    converter = None
    for row in intake.entries():
        item = parse_tika.find_file(service, row["name"])
        if not parse_tika.shaped(item["mimeType"]):
            print(f"skip {item['name']}: Docling has no reader for {item['mimeType']}")
            continue
        data = parse_tika.file_bytes(service, item)
        stem = connect_drive.safe_name(item["name"], "")
        folder = "ppt/media/" if item["mimeType"] == parse_tika.SLIDES else "word/media/"
        found, charts = ([], []) if item["mimeType"] == parse_tika.PDF else pictures(data, folder)
        if charts:
            print(f"{stem}: {len(charts)} native chart(s), no picture to OCR")
        if not found and item["mimeType"] != parse_tika.PDF:
            print(f"{stem}: no pictures")
            continue
        if converter is None:
            # A PDF, a deck, or a docx with pictures needs Docling, so a plain docx run does not import torch.
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()
        if item["mimeType"] == parse_tika.PDF:
            write_pdf(converter, data, stem)
        else:
            write_pictures(converter, found, stem)


if __name__ == "__main__":
    _self_check()
    main()
