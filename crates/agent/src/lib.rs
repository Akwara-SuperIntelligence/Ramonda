//! The reasoning loop, and the only module allowed to call a model.

use ramonda_rules::Decision;

#[derive(Debug, Clone)]
pub struct Side {
    pub source: String,
    pub source_class: String,
    pub value: String,
    pub anchor: String,
}

#[derive(Debug, Clone)]
pub struct Discrepancy {
    pub claim: String,
    pub left: Side,
    pub right: Side,
}

#[derive(Debug, Clone)]
pub enum Outcome {
    Drafted(Decision),
    /// Sources disagreed. The Case stops and a person sees both sides.
    Stopped(Vec<Discrepancy>),
    Escalated(String),
}
