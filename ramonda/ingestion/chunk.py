"""Chunk Unstructured blocks and Docling text with a hierarchical parser."""

import json

from . import connect_drive

# shortcut: LlamaIndex defaults are 2048/512/128, retune when documents dwarf these two files


def sections_from_blocks(blocks):
    titles = []
    bucket = []
    sections = []
    tables = []
    emitted = False

    def flush():
        nonlocal emitted
        body = "\n".join(bucket).strip()
        bucket.clear()
        if body:
            sections.append((" > ".join(titles), body))
            emitted = True

    def close_page():
        nonlocal emitted
        flush()
        if titles and not emitted:
            sections.append((" > ".join(titles), titles[-1]))
        titles.clear()
        emitted = False

    for block in blocks:
        kind = block.get("type")
        text = (block.get("text") or "").strip()
        if kind == "Table":
            flush()
            table = (block.get("html") or text).strip()
            if table:
                tables.append((" > ".join(titles), table))
        elif kind == "PageBreak":
            close_page()
        elif kind == "Title" and text:
            flush()
            titles.append(text)
        elif text:
            bucket.append(text)
    close_page()
    return tables, sections


def split_markdown(markdown):
    stack = []
    buf = []
    table = []
    sections = []
    tables = []

    def crumb():
        return " > ".join(title for _, title in stack)

    def flush_buf():
        body = "\n".join(buf).strip()
        buf.clear()
        if body:
            sections.append((crumb(), body))

    def flush_table():
        if table:
            tables.append((crumb(), "\n".join(table)))
            table.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush_buf()
            flush_table()
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped.lstrip("#").strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        elif stripped.startswith("|"):
            flush_buf()
            table.append(stripped)
        elif stripped == "<!-- image -->":
            flush_table()
        else:
            flush_table()
            buf.append(line)
    flush_buf()
    flush_table()
    return tables, sections


def flat(text):
    return " ".join(text.split())


def novel(text, corpus):
    sample = flat(text)[:120]
    return bool(sample) and sample not in flat(corpus)


def hierarchize(sections):
    from llama_index.core.node_parser import HierarchicalNodeParser
    from llama_index.core.schema import Document, NodeRelationship

    crumbs = []
    docs = []
    for crumb, text in sections:
        if not text.strip():
            continue
        crumbs.append(crumb)
        # The breadcrumb is longer than the smallest chunk, so it stays off the node metadata.
        docs.append(Document(text=text, metadata={"section": len(crumbs) - 1}))
    if not docs:
        return []
    nodes = HierarchicalNodeParser.from_defaults().get_nodes_from_documents(docs)
    chunks = []
    for node in nodes:
        parent = node.relationships.get(NodeRelationship.PARENT)
        section = node.metadata.get("section")
        chunks.append(
            {
                "kind": "text",
                "text": node.get_content(),
                "breadcrumb": crumbs[int(section)] if section is not None else "",
                "id": node.node_id,
                "parent_id": parent.node_id if parent else None,
            }
        )
    return chunks


def _self_check():
    blocks = [
        {"type": "Title", "text": "Cover"},
        {"type": "PageBreak", "text": ""},
        {"type": "Title", "text": "Intro"},
        {"type": "NarrativeText", "text": "Hello world."},
        {"type": "Table", "text": "| a | b |"},
    ]
    tables, sections = sections_from_blocks(blocks)
    assert tables == [("Intro", "| a | b |")]
    assert sections[0] == ("Cover", "Cover")
    assert sections[1] == ("Intro", "Hello world.")
    md_tables, md_sections = split_markdown("## Form\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nOnly here.")
    assert md_tables[0][0] == "Form"
    assert md_tables[0][1].startswith("| a |")
    assert "Only here" in md_sections[0][1]
    _, headed = split_markdown("## One\n\nAlpha.\n\n## Two\n\nBeta.")
    assert headed[0][0] == "One" and headed[1][0] == "Two"
    assert not novel("Hello world. extra", "Hello world. extra stays")
    assert novel("scanned form answer 750", "Hello world.")
    prose = " ".join(f"Sentence {i} is long enough to split." for i in range(60))
    crumb = "Intro " + ("section " * 40)
    chunks = hierarchize([(crumb, prose)])
    assert chunks
    assert all(chunk["breadcrumb"] == crumb for chunk in chunks)
    assert any(chunk["parent_id"] for chunk in chunks)
    assert reads_blocks([{"type": "Title", "text": "A"}])
    assert not reads_blocks(None)


def reads_blocks(blocks):
    return blocks is not None


def from_tika(text):
    # shortcut: flat Tika text has no headings or tables, upgrade when a format brings them
    body = (text or "").strip()
    return hierarchize([("", body)]) if body else []


def docling_extra(stem, blocks):
    texts = []
    named = connect_drive.OUT / "docling" / f"{stem}.md"
    if named.exists():
        texts.append(named.read_text())
    # shortcut: picture OCR is the deck, the PDF's Docling text is the named markdown
    if not stem.endswith(".pdf"):
        image_dir = connect_drive.OUT / "docling" / "images"
        if image_dir.is_dir():
            texts.extend(path.read_text() for path in sorted(image_dir.glob("*.md")))
    corpus = "\n".join(block.get("text") or "" for block in blocks)
    tables = []
    sections = []
    for text in texts:
        found_tables, found_sections = split_markdown(text)
        tables.extend(found_tables)
        sections.extend((crumb, body) for crumb, body in found_sections if novel(body, corpus))
    return tables, sections


def chunks_from_blocks(stem, blocks):
    tables, sections = sections_from_blocks(blocks)
    extra_tables, extra_sections = docling_extra(stem, blocks)
    chunks = [
        {"kind": "table", "text": text, "breadcrumb": crumb}
        for crumb, text in tables + extra_tables
        if text.strip()
    ]
    chunks.extend(hierarchize(sections + extra_sections))
    return chunks


def main():
    blocks_by_stem = {
        path.name.removesuffix(".unstructured.json"): path
        for path in connect_drive.OUT.glob("*.unstructured.json")
    }
    tika_by_stem = {
        path.name.removesuffix(".txt"): path
        for path in connect_drive.OUT.glob("*.txt")
    }
    stems = sorted(set(blocks_by_stem) | set(tika_by_stem))
    if not stems:
        raise SystemExit("No parser output in out/. Run the parsers first.")
    for stem in stems:
        blocks = json.loads(blocks_by_stem[stem].read_text()) if stem in blocks_by_stem else None
        if reads_blocks(blocks):
            chunks = chunks_from_blocks(stem, blocks)
        else:
            chunks = from_tika(tika_by_stem[stem].read_text())
        # shortcut: the output name is the file id; Fortune 500 uses the Drive file id.
        for chunk in chunks:
            chunk["file_id"] = stem
        dest = connect_drive.OUT / f"{stem}.chunks.json"
        dest.write_text(json.dumps(chunks, indent=2, ensure_ascii=False))
        print(f"{len(chunks)} chunks -> {dest}")


if __name__ == "__main__":
    _self_check()
    main()
