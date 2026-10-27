# A citation anchors on section, paragraph, and a frozen quote — never on a page alone

**Status:** accepted

Both source documents are `.docx`, which have no pagination until something renders them: Word's page count is 54, the parse emits 46 page breaks, and `retrieval.chunk` has no page column at all. A page-anchored citation would therefore be a number the pipeline invents, and Azure's own layout model demonstrates the invention — for DOCX it counts 3,000 characters as "one page unit". So the canonical anchor is the section breadcrumb plus a paragraph range within it, always with `anchor_quote`: about eighty characters of the chunk's own text, frozen at citation time, so that a citation whose text has since moved is detectable rather than silently wrong. This is the layered-selector idea from the W3C annotation model, reduced to the two selectors this pipeline can actually produce.

`anchor_page` exists and is used when the source prints pages, because a reader holding a PDF deserves to be pointed at page 12. It is always the number printed on the page, never a positional index, and it is never the thing the system depends on.

**Considered options:** page only (rejected: impossible for `.docx` and Google Docs without inventing the number); both anchors co-equal (rejected: two citation formats for the agent to get wrong and two code paths in evaluation); character offsets (rejected: they survive neither re-parse nor version change, and the text around them is a better selector).

**Consequences:** retrieval needs four new anchor columns and an index for section expansion. Table chunks anchor by row range rather than paragraph, because a table's evidence is its rows. A citation that cannot reconstruct its section is a contract violation, not a display problem.
