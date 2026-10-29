# Retrieval ships whole, not as a reduced funnel

Status: accepted

Retrieval is built to the full nine-system shape from v0.1: parse with structure (Tika for text, Docling for layout and tables), chunk by meaning (heading and boundary detection, tables kept atomic), enrich with metadata, then retrieval as a funnel — SQL/metadata filtering, hybrid vector plus BM25, re-ranking. No reduced funnel.

Retrieval quality is the difference between a system that cites a page and one that invents one. The failure modes appear at scale, when it is too late to rebuild.

## Consequences

- This is the most expensive part of v0.1 relative to a small corpus. The small corpus makes correctness cheap to verify while the scale machinery is proven.
