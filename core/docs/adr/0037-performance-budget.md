# Performance budget

Status: accepted

Speed is a product requirement, not a tuning exercise. The budget:

- first section visible after the job starts: **under 60 seconds**
- a forty-item document fully drafted: **under 20 minutes**
- one item regenerated: **under 2 minutes**
- a chat answer about the evidence: **under 5 seconds**

## Consequences

- Ingestion does the expensive work up front: parsing, chunking, embeddings and metadata are computed before a job ever runs.
- Retrieval results, archived pages and extracted claims are cached per item and reused across regenerations.
- The context budget per section (0036) is the main lever: smaller bundles are faster and cheaper.
- Fan-out is the default. A design that processes items sequentially fails this budget by construction, and is rejected on that basis alone.
