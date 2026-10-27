//! The append-only evidence ledger. This crate depends on nothing in the workspace,
//! so it cannot grow an opinion about Cases or Documents (adr/0006).

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Entry {
    NumberAsserted {
        case: String,
        field: String,
        value: String,
        anchor: String,
        extractor: String,
    },
    SourceConfirmed {
        case: String,
        check: String,
        source: String,
        source_class: String,
        anchor: String,
    },
    RuleEvaluated {
        case: String,
        rule: String,
        pack_version: String,
        outcome: String,
        inputs_hash: String,
    },
    CheckFailed {
        case: String,
        check: String,
        claim: String,
        values: serde_json::Value,
    },
    HumanSigned {
        case: String,
        principal: String,
        decision: String,
    },
    PackInstalled {
        pack: String,
        version: String,
        signature: String,
    },
}

/// One entry chained to the previous hash. Editing a row breaks every later hash.
pub fn hash(prev: &str, entry: &Entry) -> String {
    let body = serde_json::to_vec(entry).expect("evidence entry is serialisable");
    let mut hasher = blake3::Hasher::new();
    hasher.update(prev.as_bytes());
    hasher.update(&body);
    hasher.finalize().to_hex().to_string()
}
