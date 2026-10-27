//! The deterministic engine's vocabulary. It has no model dependency (adr/0004), and
//! `Verified` is the only way a Decision can exist: a Check that has not run cannot
//! produce one (adr/0006).

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Outcome {
    Suspicious,
    Routine,
    Escalate,
}

#[derive(Debug, Clone)]
pub struct Decision {
    pub outcome: Outcome,
    pub rationale: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CheckStatus {
    Confirmed,
    Discrepancy,
    Missing,
}

#[derive(Debug, Clone)]
pub struct Verified<T>(T);

impl<T> Verified<T> {
    pub fn get(&self) -> &T {
        &self.0
    }
}

/// The only producer of `Verified`. Every check must confirm, and there must be at least
/// one: an empty set means nothing was verified, which is not a pass.
pub fn confirm<T>(statuses: &[CheckStatus], decision: T) -> Option<Verified<T>> {
    let all = !statuses.is_empty() && statuses.iter().all(|s| *s == CheckStatus::Confirmed);
    all.then_some(Verified(decision))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_checks_is_not_a_pass() {
        assert!(confirm(&[], Decision { outcome: Outcome::Routine, rationale: String::new() }).is_none());
    }

    #[test]
    fn one_discrepancy_stops_the_decision() {
        let statuses = [CheckStatus::Confirmed, CheckStatus::Discrepancy];
        assert!(confirm(&statuses, Decision { outcome: Outcome::Routine, rationale: String::new() }).is_none());
    }

    #[test]
    fn all_confirmed_verifies() {
        let statuses = [CheckStatus::Confirmed, CheckStatus::Confirmed];
        assert!(confirm(&statuses, Decision { outcome: Outcome::Routine, rationale: String::new() }).is_some());
    }
}
