# Runbook: a new client

Ten steps. Steps 1–6 are Pack work and are the real cost. Step 7 is the only step that can produce code, and only when a Source cannot be read any other way.

1. **Collect.** Take the client's documents, an example of every Source, and the client's own words for their work.
2. **Pack.** Copy `packs/aml-bank/` to `packs/<client>/`. Fill `manifest.yaml`, `vocabulary.yaml`, `document-types.yaml`.
3. **Map.** For each Source, write `sources.yaml` and a Mapping. Assign a **Source class** to each Source; anything sharing an upstream gets the same class.
4. **Rules.** Write `rules/`. Have the client's compliance team read them and sign them.
5. **Checks.** Write `checks/`. Each Claim names the two Source classes that must confirm it. There is no tolerance.
6. **Fixtures and tests.** Generate fixtures from the Pack's schemas, including deliberately disagreeing fixtures. Write one expected outcome per fixture. Run the Pack tests until green.
7. **Connectors.** List the Sources. For each one no existing Connector can read, write one Connector in this repository. Never fork the repository.
8. **Cell.** Provision one Cell: one database, three processes, one Docling sidecar. Run migrations. Install the signed Pack.
9. **Identity.** Connect the client's IdP to that Cell's JWKS. Map their groups to Principals and Classifications. Test that one Principal cannot see a document above their Clearance.
10. **First real Case.** Run one real Case with a person beside the screen. Open the regulator bundle together. Only then open the next Case.

## After the first client

The platform did not change. The next client is steps 1–10 again, and the only new code is Connectors for Sources we could not read.

## The signal that a boundary is wrong

If steps 3–6 force a change in `corpus`, `agent`, `rules`, `case` or `evidence`, stop. Fix the boundary instead of shipping the change. One client forcing module code is a design smell; two clients forcing it is a fork in progress.
