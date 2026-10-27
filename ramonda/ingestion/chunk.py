"""Chunk Unstructured blocks and Docling text with a hierarchical parser."""

import hashlib
import json

from . import connect_drive

# shortcut: LlamaIndex defaults are 2048/512/128, retune when documents dwarf these two files


def sections_from_blocks(blocks):
    titles = []
    bucket = []
    sections = []
    tables = []
    emitted = False

    def crumb():
        return " > ".join(title for _, title in titles)

    def flush():
        nonlocal emitted
        body = "\n".join(bucket).strip()
        bucket.clear()
        if body:
            sections.append((crumb(), body))
            emitted = True

    def close_page():
        nonlocal emitted
        flush()
        if titles and not emitted:
            sections.append((crumb(), titles[-1][1]))
        # A heading survives the page break: the next page still belongs to its section.
        emitted = False

    for block in blocks:
        kind = block.get("type")
        text = (block.get("text") or "").strip()
        # A docx repeats its header and footer on every page. They are not the body.
        if kind in ("Header", "Footer"):
            continue
        if kind == "Table":
            flush()
            table = (block.get("html") or text).strip()
            if table:
                tables.append((crumb(), table))
        elif kind == "PageBreak":
            close_page()
        elif kind == "Title" and text:
            flush()
            depth = int(block.get("depth") or 0)
            while titles and titles[-1][0] >= depth:
                titles.pop()
            titles.append((depth, text))
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
    from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
    from llama_index.core.schema import Document

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
    nodes = get_leaf_nodes(
        HierarchicalNodeParser.from_defaults().get_nodes_from_documents(docs)
    )
    chunks = []
    for node in nodes:
        section = node.metadata.get("section")
        chunks.append(
            {
                "kind": "text",
                "text": node.get_content(),
                "breadcrumb": crumbs[int(section)] if section is not None else "",
                "id": node.node_id,
                # shortcut: leaves only, so a parent_id would point nowhere; Fortune 500 stores the parents for context.
                "parent_id": None,
            }
        )
    return chunks


def identified(chunks, stem):
    # shortcut: a content hash is the id for a table chunk; Fortune 500 uses the source record id.
    seen = set()
    kept = []
    for chunk in chunks:
        key = (chunk.get("kind"), chunk["text"], chunk.get("breadcrumb") or "")
        if key in seen:
            continue
        seen.add(key)
        chunk["file_id"] = stem
        if not chunk.get("id"):
            chunk["id"] = hashlib.sha1(
                f"{stem}\0{chunk.get('kind') or ''}\0{chunk.get('breadcrumb') or ''}\0{chunk['text']}".encode()
            ).hexdigest()
        kept.append(chunk)
    return kept


def titled(chunks, stem):
    # The document title comes from the intake. A model asked for a title writes a paragraph.
    path = connect_drive.OUT / f"{stem}.intake.json"
    if not path.exists():
        return chunks
    name = json.loads(path.read_text())["name"]
    for suffix in (".docx", ".pdf", ".pptx"):
        name = name.removesuffix(suffix)
    for chunk in chunks:
        chunk["document_title"] = name
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
    assert all(chunk["parent_id"] is None for chunk in chunks)
    assert len({chunk["text"] for chunk in chunks}) == len(chunks)
    short = hierarchize([("Intro", "One sentence.")])
    assert len(short) == 1 and short[0]["text"] == "One sentence."
    table = [{"kind": "table", "text": "| a |", "breadcrumb": "B"}]
    first = identified(table, "f")
    assert first[0]["file_id"] == "f" and first[0]["id"]
    again = identified([{"kind": "table", "text": "| a |", "breadcrumb": "B"}], "f")
    assert again[0]["id"] == first[0]["id"]
    other = identified([{"kind": "table", "text": "| a |", "breadcrumb": "B"}], "g")
    assert other[0]["id"] != first[0]["id"]
    dup = identified(
        [
            {"kind": "table", "text": "| a |", "breadcrumb": "B"},
            {"kind": "table", "text": "| a |", "breadcrumb": "B"},
        ],
        "f",
    )
    assert len(dup) == 1
    split = identified(
        [
            {"kind": "text", "text": "A", "breadcrumb": "one"},
            {"kind": "text", "text": "A", "breadcrumb": "two"},
        ],
        "f",
    )
    assert len(split) == 2
    with_id = identified([{"id": "x", "kind": "text", "text": "t", "breadcrumb": ""}], "f")
    assert with_id[0]["id"] == "x"
    assert titled([{"text": "t"}], "no such stem")[0].get("document_title") is None
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
    # The PDF's Docling text, and the OCR of the pictures inside a deck. One file per document.
    for name in (f"{stem}.md", f"{stem}.images.md"):
        path = connect_drive.OUT / "docling" / name
        if path.exists():
            texts.append(path.read_text())
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
        chunks = titled(identified(chunks, stem), stem)
        dest = connect_drive.OUT / f"{stem}.chunks.json"
        dest.write_text(json.dumps(chunks, indent=2, ensure_ascii=False))
        print(f"{len(chunks)} chunks -> {dest}")


if __name__ == "__main__":
    _self_check()
    main()
