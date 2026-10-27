"""Partition a Drive file into Unstructured's typed blocks."""

import io
import json
import re
from collections import Counter

from . import connect_drive, intake, parse_tika


def as_block(category, text, html, depth=None):
    # depth is a docx heading level: 0 is a chapter, 1 is a sub-heading under it.
    block = {"type": category, "text": text, "depth": depth}
    if html:
        block["html"] = html
    return block


def _self_check():
    title = as_block("Title", "Intro", None)
    table = as_block("Table", "a b", "<table></table>")
    assert title == {"type": "Title", "text": "Intro", "depth": None}
    assert table["html"] == "<table></table>"
    assert as_block("Title", "Chapter", None, 0)["depth"] == 0


def _use_simple_tokenize():
    # shortcut: spaCy 3.8 crashes loading its English model in this image, so splits are regex
    import unstructured.nlp.tokenize as tokenize
    import unstructured.partition.text_type as text_type

    def sent_tokenize(text):
        text = str(text).strip()
        parts = [part for part in re.split(r"(?<=[.!?])\s+", text) if part]
        return parts or ([text] if text else [])

    def word_tokenize(text):
        return re.findall(r"\w+|[^\w\s]", str(text))

    def pos_tag(text):
        return [(word, "NN") for word in word_tokenize(text)]

    for module in (tokenize, text_type):
        module.sent_tokenize = sent_tokenize
        module.word_tokenize = word_tokenize
        module.pos_tag = pos_tag


def blocks_from(data, mime):
    _use_simple_tokenize()
    if mime == parse_tika.PDF:
        from unstructured.partition.pdf import partition_pdf

        # shortcut: fast reads the text layer; run this venv on Python 3.12 (no torch wheel for 3.15). Docling OCRs a scan
        elements = partition_pdf(file=io.BytesIO(data), strategy="fast")
    elif mime in (parse_tika.DOC, parse_tika.DOCX):
        from unstructured.partition.docx import partition_docx

        elements = partition_docx(file=io.BytesIO(data))
    else:
        from unstructured.partition.pptx import partition_pptx

        # shortcut: text already in the pptx, Docling reads the chart pictures
        elements = partition_pptx(file=io.BytesIO(data))
    blocks = []
    for element in elements:
        html = getattr(element.metadata, "text_as_html", None)
        depth = getattr(element.metadata, "category_depth", None)
        blocks.append(as_block(element.category, element.text or "", html, depth))
    return blocks


def main():
    service = connect_drive.drive_service()
    connect_drive.OUT.mkdir(exist_ok=True)
    for row in intake.entries():
        item = parse_tika.find_file(service, row["name"])
        if not parse_tika.shaped(item["mimeType"]):
            print(f"skip {item['name']}: Unstructured has no partition for {item['mimeType']}")
            continue
        blocks = blocks_from(parse_tika.file_bytes(service, item), item["mimeType"])
        path = connect_drive.OUT / f"{connect_drive.safe_name(item['name'], '')}.unstructured.json"
        path.write_text(json.dumps(blocks, indent=2, ensure_ascii=False))
        counts = Counter(block["type"] for block in blocks)
        print(f"{len(blocks)} blocks -> {path}")
        for kind, count in sorted(counts.items()):
            print(f"  {kind}: {count}")


if __name__ == "__main__":
    _self_check()
    main()
