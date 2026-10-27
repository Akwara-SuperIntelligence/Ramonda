//! Documents: intake, the Block model, chunks and citations (adr/0011).

#[derive(Debug, Clone)]
pub struct Intake {
    pub source: String,
    pub source_ref: String,
    pub media_type: String,
}

/// A retrievable piece of one Document version, with exactly one citation anchor.
#[derive(Debug, Clone)]
pub struct Hit {
    pub document_version: String,
    pub breadcrumb: String,
    pub quote: String,
    /// Only where the document has printed pages.
    pub page: Option<u32>,
    pub score: f32,
}
