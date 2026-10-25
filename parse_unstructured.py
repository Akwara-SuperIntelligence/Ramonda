"""Partition a Drive file into Unstructured's typed blocks."""

import io
import json
import re
from collections import Counter

import connect_drive
import parse_tika


def as_block(category, text, html):
    block = {"type": category, "text": text}
    if html:
        block["html"] = html
    return block


def _self_check():
    title = as_block("Title", "Intro", None)
    table = as_block("Table", "a b", "<table></table>")
    assert title == {"type": "Title", "text": "Intro"}
    assert table["html"] == "<table></table>"


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
    else:
        from unstructured.partition.pptx import partition_pptx

        # shortcut: text already in the pptx, Docling reads the chart pictures
        elements = partition_pptx(file=io.BytesIO(data))
    blocks = []
    for element in elements:
        html = getattr(element.metadata, "text_as_html", None)
        blocks.append(as_block(element.category, element.text or "", html))
    return blocks


def main():
    service = connect_drive.drive_service()
    connect_drive.OUT.mkdir(exist_ok=True)
    for name in parse_tika.FILES:
        item = parse_tika.find_file(service, name)
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
