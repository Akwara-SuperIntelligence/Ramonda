"""Partition the same Drive deck into Unstructured's typed blocks."""

import io
import json
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


def blocks_from(data):
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
    item = parse_tika.find_file(service)
    blocks = blocks_from(parse_tika.export_pptx(service, item))
    connect_drive.OUT.mkdir(exist_ok=True)
    path = connect_drive.OUT / f"{connect_drive.safe_name(item['name'], '')}.unstructured.json"
    path.write_text(json.dumps(blocks, indent=2, ensure_ascii=False))
    counts = Counter(block["type"] for block in blocks)
    print(f"{len(blocks)} blocks -> {path}")
    for name, count in sorted(counts.items()):
        print(f"  {name}: {count}")


if __name__ == "__main__":
    _self_check()
    main()
