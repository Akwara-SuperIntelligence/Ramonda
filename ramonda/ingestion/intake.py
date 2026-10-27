"""The files this run ingests, and what each one is.

The manifest is the source of the document fields. A field the report needs is
set here, by a person, and never inferred from the text by the model.
"""

import json

from . import connect_drive

MANIFEST = connect_drive.ROOT / "corpus" / "intake.json"


def checked(rows):
    for row in rows:
        if not row.get("name") or not row.get("doc_type"):
            raise ValueError(f"intake row needs a name and a doc_type: {row!r}")
    return rows


def entries(path=MANIFEST):
    return checked(json.loads(path.read_text()))


def record(row, stem):
    # The chunker and the save step read this. One file, one set of document fields.
    path = connect_drive.OUT / f"{stem}.intake.json"
    path.write_text(json.dumps(row, indent=2, ensure_ascii=False))
    return path


def _self_check():
    assert checked([{"name": "a", "doc_type": "annual_report"}])
    for bad in ([{}], [{"name": "a"}], [{"doc_type": "b"}]):
        try:
            checked(bad)
        except ValueError:
            continue
        raise AssertionError(f"row was accepted: {bad}")
