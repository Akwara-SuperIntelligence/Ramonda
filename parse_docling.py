"""OCR the chart pictures in the same Drive deck with Docling."""

import io
import zipfile
from pathlib import Path

import connect_drive
import parse_tika

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


def main():
    from docling.document_converter import DocumentConverter

    service = connect_drive.drive_service()
    item = parse_tika.find_file(service)
    data = parse_tika.export_pptx(service, item)
    OUT.mkdir(parents=True, exist_ok=True)
    images = OUT / "images"
    images.mkdir(exist_ok=True)
    converter = DocumentConverter()
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


if __name__ == "__main__":
    _self_check()
    main()
