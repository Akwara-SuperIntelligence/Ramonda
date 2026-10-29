# Document structure is extracted from the client's own files, confirmed once, and stored in the deployment

Status: accepted

The agent runs an `extract_structure` tool against the client's finished documents — DOCX, XLSX, PPTX, PDF and charts, not DOCX alone. It returns a Structure Spec: ordered sections, their parts, heading levels, numbering, table shapes, chart types, and the styles that carry fonts, sizes, colours and spacing. Where several examples disagree, it reports the variance instead of picking silently.

A human confirms the Spec once. From then on the Spec is versioned client configuration stored in the client's deployment, and two things read it: the artifact builder writes into its sections and styles, and the structural check compares output against it deterministically.

No template file and no client document enters the repository. At enterprise scale this is not a preference: the archive lives in the client's sources and is orders of magnitude larger than any codebase.

## Consequences

- Onboarding a client includes a structure-extraction pass over their historical outputs.
- The one-time confirmation exists because an unreviewed extraction silently becomes the definition of correct for every future document.
- DOCX and XLSX examples are preferred over PDF, because styles and cell formats are machine-readable in the former and guessed in the latter.
- The Spec is data, so a rebrand or a format change is a new Spec version, not a code change.
