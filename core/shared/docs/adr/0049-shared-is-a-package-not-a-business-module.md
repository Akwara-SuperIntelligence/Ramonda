# Shared is a package with a contract, not a twelfth business module

Status: accepted

Two records disagree about what shared is. 0031 says the event log is not a module. 0048 gives shared a `MODULE.md` with the same five headings as every other module. Both are right about different questions: shared is one package with a one-page contract, its own decisions and its own code, but it has no business capability of its own, publishes no domain events, and is not one of the eleven business modules in 0029.

A contract is needed because every module calls shared, and a caller must be able to read what shared exposes without reading its source. A business module is not the right name because shared has nothing to sell: it records, stores, transports and queues, and it never decides.

## Consequences

- Shared is reviewed and versioned like a module, but it never appears in the module list and is never counted as a capability.
- The question "is this shared?" is not "is it important?" It is "does it decide anything about the business?" If it does, it belongs to a module.
- Splitting shared into several packages is deferred until its primitives stop agreeing about their dependencies. Until then one package, one contract.
- A shared package that needs a client's word, or a module's word, is proof the boundary is wrong (0028).
