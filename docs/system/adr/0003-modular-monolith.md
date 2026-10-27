# Six modules, three libraries, enforced boundaries

The system is a modular monolith: six crates — `corpus`, `agent`, `rules`, `case`, `evidence`, `identity`. There are no library crates until a library has a caller; a module with no dependants is an unfinished thought, not a boundary.

Modules are cut by **one reason to change**, not by pipeline step. The previous system split `ingestion` from `retrieval` even though both change when we learn to read a new document format, and the split produced three different chunk-id schemes and a contract type the index never matched. Merging them into `corpus` is the correction.

Two edges are banned rather than discouraged: `rules` may not depend on `models`, which is what makes the determinism claim structural, and `evidence` may only depend on `platform`, so the ledger can never grow an opinion about Cases. `scripts/check-boundaries.sh` reads the manifests and fails the build on a forbidden edge.
