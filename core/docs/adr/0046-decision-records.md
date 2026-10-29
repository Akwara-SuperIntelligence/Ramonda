# Decision records: global numbering, placed by scope, with precedence

Status: accepted

**Numbering is global.** Numbers run sequentially from 0001 across the whole repository, are never reused, and never change. Moving a record between folders does not renumber it. A number identifies a decision for the life of the system, even after the folder it sits in is reorganised.

**Placement follows scope, not importance:**

| Scope | Folder | Binds |
|---|---|---|
| System | `core/docs/adr/` | every module, the shell, and every client |
| Module | `core/<module>/docs/adr/` | only inside that module's boundary |
| Shell | `platform/<app>/docs/adr/` | only that deployable |
| Client | `clients/<client>/docs/adr/` | only that client's configuration and code |

**Precedence is one-way.** A narrower record may elaborate a broader one; it may never contradict it. A module record that contradicts a system record is void until the system record is amended. A client record that contradicts a system or module record is void in the same way. To change a broad decision, amend the broad record first, then adjust what depends on it.

Numbering is not local to a folder because local numbering recreates the ambiguity the folder split removes: two `0001` files would both answer to "see 0001".

## Consequences

- Every cross-reference in the corpus keeps resolving when files move.
- A reader asking "what binds me here?" reads the narrowest record first, then the broader ones above it.
- Superseding means editing the record and noting the supersession, never deleting it.
