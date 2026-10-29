# The artifact's format comes from the client's Structure Spec

Status: accepted

The client's Structure Spec declares what the deliverable is: DOCX for the first workflow, and XLSX, PPTX, chart-bearing or PDF-ready outputs for other clients and other work products. The `artifacts` module renders the declared format and exports it; PDF is rendered at signature.

For the first workflow, DOCX is canonical: tables are first-class blocks, import and export round-trip through Word, and anything that cannot survive that round trip is fixed before signing. A positions document is judged on the Word file that circulates and the PDF that is signed.

Real-time collaborative editing is deliberately not built. With two users, single-editor-at-a-time with versioned saves is the honest model; pretending to be a shared canvas corrupts the version history.

## Consequences

- Adding a format is a renderer plus a Structure Spec variant, not a new module.
- Export is a first-class feature, available from the workspace.
- The document model must express what a work product needs: headings, numbered items, real tables, charts, footnotes and page references.
