"""Run the ingestion steps, and write the labelled chunks to retrieval when a caller is given."""

import json
import os


def ingest(caller=None):
    from . import chunk, enrich, intake, parse_docling, parse_tika, parse_unstructured

    intake._self_check()
    parse_tika.main()
    parse_unstructured.main()
    parse_docling.main()
    chunk.main()
    enrich.main()
    # Retrieval is off for now. Uncomment the next line to write the chunks and index them.
    # label_and_save(caller)


def labelled(chunks, label, user):
    # shortcut: no doc_date, doc_type, or department yet; Fortune 500 sets them from the source.
    for chunk in chunks:
        chunk["security_label"] = label
        chunk["access"] = [f"user:{user}"]
    return chunks


def label_and_save(caller):
    from .. import retrieval
    from . import connect_drive

    # shortcut: one operator, one label, and the operator is the only reader; a re-run replaces the access list.
    # Fortune 500: map folders to an organisation and a label, read each permission list, and re-read it on a schedule.
    label = os.environ.get("DEFAULT_LABEL", "restricted")
    for path in sorted(connect_drive.OUT.glob("*.chunks.json")):
        retrieval.save(caller, labelled(json.loads(path.read_text()), label, caller.user))


def _self_check():
    chunks = labelled([{"text": "x", "file_id": "f"}], "internal", "a@b")
    assert chunks[0]["security_label"] == "internal"
    assert chunks[0]["access"] == ["user:a@b"]
    assert labelled([], "internal", "a@b") == []
