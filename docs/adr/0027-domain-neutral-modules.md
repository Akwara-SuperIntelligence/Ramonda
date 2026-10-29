# Modules are named for platform capability, never for a client's domain

Status: accepted

No core module is named after any client's paperwork. `positions`, `consultation` and any similar name are banned from the core: they describe one customer, and a second customer would have to rename them, fork them, or bolt on a parallel module.

The core modules describe capabilities every regulated desk needs: who may act, where material comes from, what the material says, what the enterprise is made of, how its written rules compute, how a work product is built and versioned, and what governs the agent. Each client supplies its own vocabulary, Procedure, templates, definitions, adapters and skills as configuration inside its own deployment.

Client-specific behaviour that the core genuinely lacks is added as a client module, and client modules may depend on core modules but never the reverse.

## Consequences

- The test for any new core module is: does every client need this, or does this client want it? The second answer means configuration or a client module.
- Each client has its own composition root selecting the modules and configuration that deployment runs.
- The client's vocabulary lives in the client's configuration and the artifact, not in import paths.
