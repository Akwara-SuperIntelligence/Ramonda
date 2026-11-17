use postgres_types::Json;
use serde::Serialize;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use tokio_postgres::{Client, NoTls};

pub(crate) const GENESIS: &str = "0000000000000000000000000000000000000000000000000000000000000000";
const HEX: &[u8; 16] = b"0123456789abcdef";

pub(crate) type Failure = Box<dyn std::error::Error + Send + Sync>;

#[derive(Clone, Debug, PartialEq, Serialize)]
pub(crate) struct Entry {
    pub(crate) action: String,
    pub(crate) actor_subject: String,
    pub(crate) actor_username: String,
    pub(crate) arguments: Map<String, Value>,
    pub(crate) recorded_at: String,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Row {
    pub(crate) entry: Entry,
    pub(crate) previous_hash: String,
    pub(crate) hash: String,
}

impl Entry {
    pub(crate) fn link(self, previous_hash: &str) -> serde_json::Result<Row> {
        let hash = digest(previous_hash, &self.payload()?);
        Ok(Row {
            entry: self,
            previous_hash: previous_hash.to_owned(),
            hash,
        })
    }

    fn payload(&self) -> serde_json::Result<String> {
        serde_json::to_string(&serde_json::to_value(self)?)
    }
}

fn digest(previous_hash: &str, payload: &str) -> String {
    Sha256::new()
        .chain_update(previous_hash)
        .chain_update(payload)
        .finalize()
        .iter()
        .flat_map(|byte| [HEX[usize::from(byte >> 4)], HEX[usize::from(byte & 0x0f)]])
        .map(char::from)
        .collect()
}

pub(crate) fn now() -> String {
    chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Nanos, true)
}

pub(crate) async fn connect(
    config: &tokio_postgres::Config,
) -> Result<Client, tokio_postgres::Error> {
    let (client, connection) = config.connect(NoTls).await?;
    tokio::spawn(connection);
    Ok(client)
}

pub(crate) async fn insert(client: &mut Client, entry: Entry) -> Result<(), Failure> {
    let transaction = client.transaction().await?;
    transaction
        .batch_execute("SELECT pg_advisory_xact_lock(714060)")
        .await?;
    let tail = transaction
        .query_one(
            "SELECT (SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1), $1::jsonb",
            &[&Json(&entry.arguments)],
        )
        .await?;
    let previous: Option<String> = tail.try_get(0)?;
    let Json(arguments) = tail.try_get(1)?;
    let row = Entry { arguments, ..entry }.link(previous.as_deref().unwrap_or(GENESIS))?;
    transaction
        .execute(
            "INSERT INTO audit_log \
             (recorded_at, actor_subject, actor_username, action, arguments, previous_hash, hash) \
             VALUES ($1, $2, $3, $4, $5, $6, $7)",
            &[
                &row.entry.recorded_at,
                &row.entry.actor_subject,
                &row.entry.actor_username,
                &row.entry.action,
                &Json(&row.entry.arguments),
                &row.previous_hash,
                &row.hash,
            ],
        )
        .await?;
    Ok(transaction.commit().await?)
}

#[cfg(test)]
pub(crate) fn verify(rows: &[Row]) -> Result<(), usize> {
    let mut previous = GENESIS;
    for (index, row) in rows.iter().enumerate() {
        if row.entry.clone().link(previous).ok().as_ref() != Some(row) {
            return Err(index);
        }
        previous = &row.hash;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{Entry, GENESIS, Row, verify};

    const FIRST: &str = "dc31db64976a7032a269167fa2e95fe00a11067ed0959dec63213c2074bfdf06";
    const SECOND: &str = "0dca4c020679143765e04b90f28d2265631fb16ea2d97d8dfc10319d3219348f";

    fn entry(recorded_at: &str) -> Entry {
        Entry {
            action: "whoami".to_owned(),
            actor_subject: "subject-1".to_owned(),
            actor_username: "amina".to_owned(),
            arguments: serde_json::from_str(r#"{"user_id":"brian","tenant_id":"other"}"#)
                .expect("arguments"),
            recorded_at: recorded_at.to_owned(),
        }
    }

    fn chain() -> [Row; 2] {
        let first = entry("2026-11-17T08:59:00.000000000Z")
            .link(GENESIS)
            .expect("first");
        let second = entry("2026-11-17T08:59:01.000000000Z")
            .link(&first.hash)
            .expect("second");
        [first, second]
    }

    #[test]
    fn payload_and_hashes_match_the_pinned_vector() {
        assert_eq!(
            entry("2026-11-17T08:59:00.000000000Z")
                .payload()
                .expect("payload"),
            r#"{"action":"whoami","actor_subject":"subject-1","actor_username":"amina","arguments":{"tenant_id":"other","user_id":"brian"},"recorded_at":"2026-11-17T08:59:00.000000000Z"}"#
        );
        let [first, second] = chain();
        assert_eq!(
            (first.previous_hash.as_str(), first.hash.as_str()),
            (GENESIS, FIRST)
        );
        assert_eq!(
            (second.previous_hash.as_str(), second.hash.as_str()),
            (FIRST, SECOND)
        );
    }

    #[test]
    fn verify_catches_an_edit_or_a_dropped_head_but_not_a_dropped_tail() {
        let rows = chain();
        assert_eq!(verify(&rows), Ok(()));
        assert_eq!(verify(&[]), Ok(()));
        let mut edited = rows.clone();
        edited[0].entry.actor_username = "brian".to_owned();
        assert_eq!(verify(&edited), Err(0));
        assert_eq!(verify(&rows[1..]), Err(0));
        assert_eq!(verify(&rows[..1]), Ok(()));
    }
}
