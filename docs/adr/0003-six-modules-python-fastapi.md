# Six modules, Python, FastAPI

One modular monolith: `documents`, `harness`, `rules`, `work`, `evidence`, `access`. One package per module, one public `__init__.py` per module, and `import-linter` in CI rejecting any import deeper than another module's `__init__`.

Rejected: Rust. It was the previous plan and it was reversed. Document AI, parsing and evaluation tooling are Python, the team is small, and the compiler guarantee was buying correctness we can buy three cheaper ways: one function that builds a `Verified` value, one function that scopes a query to a Tenant, and one lint step that enforces the module graph.

**Consequence:** the type-level guarantee becomes a runtime check plus a test. The lint step becomes the compiler, and it must never be skipped.
