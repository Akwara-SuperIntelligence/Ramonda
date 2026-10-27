//! The unit of work. A Case pins its Pack version and is judged only by that version.

use ramonda_rules::{Decision, Verified};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum State {
    Open,
    Running,
    Stopped,
    Drafted,
    Signed,
    Closed,
}

#[derive(Debug, Clone)]
pub struct Trigger {
    pub source: String,
    pub source_ref: String,
}

#[derive(Debug, Clone)]
pub enum Event {
    RunStarted,
    Stopped,
    Drafted,
    /// Only a Decision that passed every Check can be signed.
    Signed {
        decision: Verified<Decision>,
        by: String,
    },
}
