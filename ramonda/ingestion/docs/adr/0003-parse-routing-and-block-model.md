# Parse routing is byte-sniffed dispatch into one block model, and an unparseable file is quarantined

**Status:** accepted

Format support was a four-MIME allowlist (`parse_tika.shaped`) and two `if mime ==` branches per parser, so every new format was a code change and anything unrecognised was `skip`ped into silence. The pipeline now routes on sniffed bytes, not on extension and not on `doc_type`, and every adapter's output is normalised into one block model — heading with depth, paragraph, list item, table with rows, figure with caption, page break — so the chunker has one vocabulary instead of Unstructured's categories, Docling's markdown, and Tika's flat text in three shapes. A file no adapter can parse becomes `quarantined` with its reason recorded, never a silent skip.

Unstructured already ships the dispatch this pipeline was hand-building: `partition()` detects the file type with libmagic (falling back to the `filetype` package, then to the declared content type) and routes to a per-type partition function, with documented fallback chains from `fast` to `ocr_only`. So the router is not ours to write; ours is the normalisation and the fallback for what a partitioner cannot see — a scanned page, or a picture inside a `.docx` zip, which is why Docling runs on the extracted images.

Docling is the normalisation target and the fallback, not an accuracy claim: independent benchmarks put it well below MinerU and Marker on hard scans. MinerU is AGPL-3.0 and Marker's weights are OpenRAIL-M, which caps free use at $5M revenue; neither belongs in a product sold into enterprises, and the benchmark gap is the price of a licence you can ship.

**Considered options:** one parser per MIME, extended by hand (rejected: that is the status quo); run all parsers on every file and pick the most complete output (rejected: three times the parse cost for a tie-break nobody can defend).

**Consequences:** `parse_warnings` exists because a partial parse is normal — Unstructured may return text where Docling would find a table. Tika stays for metadata and sniffing, not for text: its own documentation disclaims it as a security boundary for polyglot files, so isolation belongs in its per-document JVM, not in a Python `try/except`. Every document records `parser`, `parser_version`, and `parser_strategy`, because when a table comes out wrong, which adapter produced it is the first question.
