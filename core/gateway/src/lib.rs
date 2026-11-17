#[path = "audit.hot.rs"]
mod audit;

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use axum::body::Body;
use axum::extract::State;
use axum::http::header::{AUTHORIZATION, WWW_AUTHENTICATE};
use axum::http::request::Parts;
use axum::http::{HeaderValue, StatusCode};
use axum::middleware::{self, Next};
use axum::response::Response;
use axum::routing::get;
use axum::{Json, Router};
use jsonwebtoken::jwk::{AlgorithmParameters, JwkSet, KeyAlgorithm};
use jsonwebtoken::{Algorithm, DecodingKey, Validation, decode, decode_header};
use rmcp::handler::server::tool::Extension;
use rmcp::model::JsonObject;
use rmcp::transport::streamable_http_server::session::local::LocalSessionManager;
use rmcp::transport::streamable_http_server::{StreamableHttpServerConfig, StreamableHttpService};
use rmcp::{ErrorData, ServerHandler, tool, tool_handler, tool_router};
use serde::{Deserialize, Serialize};
use tokio::net::TcpListener;

const MCP_PATH: &str = "/mcp";
const METADATA_PATH: &str = "/.well-known/oauth-protected-resource/mcp";
const JWKS_TTL: Duration = Duration::from_secs(300);
const JWKS_REFETCH: Duration = Duration::from_secs(30);
const JWKS_LIMIT: usize = 1_048_576;

/// Settings the process reads before it listens.
pub struct Config {
    check: TokenCheck,
    bind: String,
    database: tokio_postgres::Config,
}

impl Config {
    /// Reads `KEYCLOAK_ISSUER`, `GATEWAY_AUDIENCE`, `GATEWAY_PUBLIC_URL`, `DATABASE_URL`, optional `GATEWAY_BIND`, and optional `GATEWAY_TLS_CA`.
    ///
    /// # Errors
    ///
    /// Returns an error when a required variable is missing, the issuer is not https, the database URL is not postgres, or the CA file cannot be read.
    pub fn from_env() -> Result<Self, String> {
        let issuer = issuer_url(&required("KEYCLOAK_ISSUER")?)?;
        let audience = required("GATEWAY_AUDIENCE")?;
        let public_url = http_url("GATEWAY_PUBLIC_URL", &required("GATEWAY_PUBLIC_URL")?)?;
        let ca_pem = tls_ca()?;
        Ok(Self {
            check: TokenCheck::remote(issuer, audience, public_url, ca_pem)?,
            bind: bind_address()?,
            database: database_url(&required("DATABASE_URL")?)?,
        })
    }
}

/// Connects to Postgres, then listens for Streamable HTTP MCP calls.
///
/// # Errors
///
/// Returns an error when Postgres refuses the connection, the socket cannot bind, or the server stops.
pub async fn serve(config: Config) -> std::io::Result<()> {
    let client = audit::connect(&config.database)
        .await
        .map_err(std::io::Error::other)?;
    let listener = TcpListener::bind(&config.bind).await?;
    let audit = Audit::Postgres(Arc::new(tokio::sync::Mutex::new(client)));
    axum::serve(listener, router(config.check, audit)).await
}

#[derive(Clone, Serialize)]
struct ResourceMetadata {
    resource: String,
    authorization_servers: Vec<String>,
}

#[derive(Clone)]
struct Caller {
    subject: String,
    username: String,
}

#[derive(Deserialize)]
struct IdClaims {
    sub: String,
    preferred_username: String,
}

struct CachedKeys {
    keys: Arc<JwkSet>,
    fetched: Instant,
    forced: Option<Instant>,
}

#[cfg(test)]
struct Queue {
    sets: std::collections::VecDeque<Arc<JwkSet>>,
    fetches: usize,
}

#[derive(Clone)]
enum Origin {
    Remote {
        url: String,
        client: reqwest::Client,
    },
    #[cfg(test)]
    Queue(Arc<Mutex<Queue>>),
}

#[derive(Clone)]
enum Keys {
    #[cfg(test)]
    Fixed(Arc<JwkSet>),
    Cached {
        cache: Arc<Mutex<Option<CachedKeys>>>,
        origin: Origin,
    },
}

#[derive(Clone)]
struct TokenCheck {
    issuer: String,
    audience: String,
    public_url: String,
    missing: HeaderValue,
    invalid: HeaderValue,
    document: ResourceMetadata,
    keys: Keys,
}

impl TokenCheck {
    fn remote(
        issuer: String,
        audience: String,
        public_url: String,
        ca_pem: Option<Vec<u8>>,
    ) -> Result<Self, String> {
        let mut builder = reqwest::Client::builder().timeout(Duration::from_secs(5));
        if let Some(pem) = ca_pem {
            let cert = reqwest::Certificate::from_pem(&pem)
                .map_err(|_| "GATEWAY_TLS_CA is not a PEM certificate".to_owned())?;
            builder = builder.add_root_certificate(cert);
        }
        let client = builder
            .build()
            .map_err(|_| "could not build the JWKS client".to_owned())?;
        let url = format!("{issuer}/protocol/openid-connect/certs");
        Self::new(
            issuer,
            audience,
            public_url,
            Keys::Cached {
                cache: Arc::new(Mutex::new(None)),
                origin: Origin::Remote { url, client },
            },
        )
    }

    #[cfg(test)]
    fn fixed(
        issuer: impl Into<String>,
        audience: impl Into<String>,
        public_url: impl Into<String>,
        keys: JwkSet,
    ) -> Result<Self, String> {
        Self::new(
            issuer.into(),
            audience.into(),
            public_url.into(),
            Keys::Fixed(Arc::new(keys)),
        )
    }

    #[cfg(test)]
    fn queued(queue: Arc<Mutex<Queue>>) -> Self {
        Self::new(
            "http://keycloak.example/realms/akwara".to_owned(),
            "gateway".to_owned(),
            "http://127.0.0.1:8080".to_owned(),
            Keys::Cached {
                cache: Arc::new(Mutex::new(None)),
                origin: Origin::Queue(queue),
            },
        )
        .expect("check")
    }

    fn new(
        issuer: String,
        audience: String,
        public_url: String,
        keys: Keys,
    ) -> Result<Self, String> {
        let metadata = format!("{public_url}{METADATA_PATH}");
        let missing = HeaderValue::from_str(&format!("Bearer resource_metadata=\"{metadata}\""))
            .map_err(|_| format!("{metadata} is not a header value"))?;
        let invalid = HeaderValue::from_str(&format!(
            "Bearer resource_metadata=\"{metadata}\", error=\"invalid_token\""
        ))
        .map_err(|_| format!("{metadata} is not a header value"))?;
        Ok(Self {
            document: ResourceMetadata {
                resource: format!("{public_url}{MCP_PATH}"),
                authorization_servers: vec![issuer.clone()],
            },
            issuer,
            audience,
            public_url,
            missing,
            invalid,
            keys,
        })
    }

    async fn authenticate(&self, header: Option<&str>) -> Option<Caller> {
        let token = bearer_token(header?)?;
        let header = decode_header(token).ok()?;
        if header.alg != Algorithm::RS256 {
            return None;
        }
        let kid = header.kid?;
        let keys = self.jwks(false).await?;
        if keys.find(&kid).is_some() {
            return verify(&self.issuer, &self.audience, &keys, token);
        }
        let keys = self.jwks(true).await?;
        verify(&self.issuer, &self.audience, &keys, token)
    }

    async fn jwks(&self, force: bool) -> Option<Arc<JwkSet>> {
        match &self.keys {
            #[cfg(test)]
            Keys::Fixed(keys) => Some(Arc::clone(keys)),
            Keys::Cached { cache, origin } => cached_jwks(cache, origin, force).await,
        }
    }
}

async fn cached_jwks(
    cache: &Mutex<Option<CachedKeys>>,
    origin: &Origin,
    force: bool,
) -> Option<Arc<JwkSet>> {
    if let Some(keys) = fresh(cache, force) {
        return Some(keys);
    }
    let keys = fetch_origin(origin).await?;
    let mut slot = lock(cache);
    let forced = if force {
        Some(Instant::now())
    } else {
        slot.as_ref().and_then(|hit| hit.forced)
    };
    *slot = Some(CachedKeys {
        keys: Arc::clone(&keys),
        fetched: Instant::now(),
        forced,
    });
    Some(keys)
}

fn fresh(cache: &Mutex<Option<CachedKeys>>, force: bool) -> Option<Arc<JwkSet>> {
    let slot = lock(cache);
    let hit = slot.as_ref()?;
    let use_cache = if force {
        hit.forced.is_some_and(|at| at.elapsed() < JWKS_REFETCH)
    } else {
        hit.fetched.elapsed() < JWKS_TTL
    };
    use_cache.then(|| Arc::clone(&hit.keys))
}

async fn fetch_origin(origin: &Origin) -> Option<Arc<JwkSet>> {
    match origin {
        Origin::Remote { url, client } => {
            let mut response = client.get(url).send().await.ok()?;
            if !response.status().is_success() {
                return None;
            }
            if response
                .content_length()
                .is_some_and(|len| len > u64::try_from(JWKS_LIMIT).unwrap_or(u64::MAX))
            {
                return None;
            }
            let mut body = Vec::new();
            loop {
                match response.chunk().await {
                    Ok(Some(chunk)) => {
                        if !extend_limited(&mut body, &chunk) {
                            return None;
                        }
                    }
                    Ok(None) => break,
                    Err(_) => return None,
                }
            }
            serde_json::from_slice(&body).ok().map(Arc::new)
        }
        #[cfg(test)]
        Origin::Queue(queue) => {
            let mut queue = lock(queue);
            queue.fetches += 1;
            queue.sets.pop_front()
        }
    }
}

fn extend_limited(body: &mut Vec<u8>, chunk: &[u8]) -> bool {
    if body.len().saturating_add(chunk.len()) > JWKS_LIMIT {
        return false;
    }
    body.extend_from_slice(chunk);
    true
}

fn lock<T>(mutex: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}

fn verify(issuer: &str, audience: &str, keys: &JwkSet, token: &str) -> Option<Caller> {
    let header = decode_header(token).ok()?;
    if header.alg != Algorithm::RS256 {
        return None;
    }
    let jwk = keys.find(header.kid.as_deref()?)?;
    if jwk
        .common
        .key_algorithm
        .is_some_and(|alg| alg != KeyAlgorithm::RS256)
        || !matches!(jwk.algorithm, AlgorithmParameters::RSA(_))
    {
        return None;
    }
    let key = DecodingKey::from_jwk(jwk).ok()?;
    let mut validation = Validation::new(Algorithm::RS256);
    validation.validate_nbf = true;
    validation.set_issuer(&[issuer]);
    validation.set_audience(&[audience]);
    validation.set_required_spec_claims(&["exp", "iss", "aud"]);
    let data = decode::<IdClaims>(token, &key, &validation).ok()?;
    if data.claims.sub.is_empty() || data.claims.preferred_username.is_empty() {
        return None;
    }
    Some(Caller {
        subject: data.claims.sub,
        username: data.claims.preferred_username,
    })
}

fn bearer_token(header: &str) -> Option<&str> {
    let (scheme, rest) = header.split_once(' ')?;
    if !scheme.eq_ignore_ascii_case("bearer") {
        return None;
    }
    let token = rest.trim();
    if token.is_empty() || token.chars().any(char::is_whitespace) {
        return None;
    }
    Some(token)
}

fn router(check: TokenCheck, audit: Audit) -> Router {
    let mcp = StreamableHttpService::new(
        move || {
            Ok(Gateway {
                audit: audit.clone(),
            })
        },
        Arc::new(LocalSessionManager::default()),
        StreamableHttpServerConfig::default()
            .with_legacy_session_mode(false)
            .with_json_response(true)
            .with_allowed_hosts(allowed_hosts(&check.public_url)),
    );
    let document = check.document.clone();
    let protected = Router::new()
        .nest_service(MCP_PATH, mcp)
        .layer(middleware::from_fn_with_state(check, require_token));
    Router::new()
        .route(
            METADATA_PATH,
            get(move || {
                let document = document.clone();
                async move { Json(document) }
            }),
        )
        .merge(protected)
}

fn allowed_hosts(public_url: &str) -> Vec<String> {
    let mut hosts = vec![
        "127.0.0.1".to_owned(),
        "localhost".to_owned(),
        "::1".to_owned(),
    ];
    if let Ok(uri) = public_url.parse::<axum::http::Uri>()
        && let Some(authority) = uri.authority()
        && !hosts.iter().any(|host| host == authority.as_str())
    {
        hosts.push(authority.as_str().to_owned());
    }
    hosts
}

async fn require_token(
    State(check): State<TokenCheck>,
    mut request: axum::extract::Request,
    next: Next,
) -> Response {
    let presented = request.headers().contains_key(AUTHORIZATION);
    let header = request
        .headers()
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok());
    if let Some(caller) = check.authenticate(header).await {
        request.extensions_mut().insert(caller);
        return next.run(request).await;
    }
    let mut response = Response::new(Body::empty());
    *response.status_mut() = StatusCode::UNAUTHORIZED;
    let challenge = if presented {
        &check.invalid
    } else {
        &check.missing
    };
    response
        .headers_mut()
        .insert(WWW_AUTHENTICATE, challenge.clone());
    response
}

#[derive(Clone)]
enum Audit {
    Postgres(Arc<tokio::sync::Mutex<tokio_postgres::Client>>),
    #[cfg(test)]
    Memory(Arc<Mutex<Vec<audit::Row>>>),
    #[cfg(test)]
    Failing,
}

impl Audit {
    async fn record(
        &self,
        action: &str,
        caller: &Caller,
        arguments: JsonObject,
    ) -> Result<(), audit::Failure> {
        let entry = audit::Entry {
            action: action.to_owned(),
            actor_subject: caller.subject.clone(),
            actor_username: caller.username.clone(),
            arguments,
            recorded_at: audit::now(),
        };
        match self {
            Self::Postgres(client) => audit::insert(&mut *client.lock().await, entry).await,
            #[cfg(test)]
            Self::Memory(rows) => {
                let mut rows = lock(rows);
                let row = entry.link(rows.last().map_or(audit::GENESIS, |row| &row.hash))?;
                rows.push(row);
                Ok(())
            }
            #[cfg(test)]
            Self::Failing => Err("insert failed".into()),
        }
    }
}

#[derive(Clone)]
struct Gateway {
    audit: Audit,
}

#[tool_router]
impl Gateway {
    #[tool(
        description = "Return the signed-in username. A user or tenant id in the arguments is ignored."
    )]
    async fn whoami(
        &self,
        Extension(parts): Extension<Parts>,
        arguments: JsonObject,
    ) -> Result<String, ErrorData> {
        let caller = parts
            .extensions
            .get::<Caller>()
            .ok_or_else(|| ErrorData::internal_error("missing caller", None))?;
        self.audit
            .record("whoami", caller, arguments)
            .await
            .map_err(|_| ErrorData::internal_error("audit write failed", None))?;
        Ok(caller.username.clone())
    }
}

#[allow(clippy::unused_async_trait_impl)]
#[tool_handler]
impl ServerHandler for Gateway {}

fn required(name: &str) -> Result<String, String> {
    match std::env::var(name) {
        Ok(value) if !value.trim().is_empty() => Ok(value),
        _ => Err(format!("{name} is required")),
    }
}

fn bind_address() -> Result<String, String> {
    match std::env::var("GATEWAY_BIND") {
        Ok(value) if !value.trim().is_empty() => Ok(value),
        Ok(_) => Err("GATEWAY_BIND is empty".to_owned()),
        Err(_) => Ok("0.0.0.0:8080".to_owned()),
    }
}

fn issuer_url(raw: &str) -> Result<String, String> {
    let url = http_url("KEYCLOAK_ISSUER", raw)?;
    if !url.starts_with("https://") {
        return Err("KEYCLOAK_ISSUER must be https".to_owned());
    }
    Ok(url)
}

fn database_url(raw: &str) -> Result<tokio_postgres::Config, String> {
    let url = raw.trim();
    let message = "DATABASE_URL must be a postgres:// or postgresql:// URL".to_owned();
    if !url.starts_with("postgres://") && !url.starts_with("postgresql://") {
        return Err(message);
    }
    url.parse().map_err(|_| message)
}

fn tls_ca() -> Result<Option<Vec<u8>>, String> {
    match std::env::var("GATEWAY_TLS_CA") {
        Ok(path) if !path.trim().is_empty() => std::fs::read(path.trim())
            .map(Some)
            .map_err(|_| format!("could not read {}", path.trim())),
        Ok(_) => Err("GATEWAY_TLS_CA is empty".to_owned()),
        Err(_) => Ok(None),
    }
}

fn http_url(name: &str, raw: &str) -> Result<String, String> {
    let url = raw.trim().trim_end_matches('/');
    let message = format!("{name} must be an http or https URL");
    let Ok(parsed) = url.parse::<axum::http::Uri>() else {
        return Err(message);
    };
    let scheme = parsed.scheme_str().unwrap_or("");
    if url
        .chars()
        .any(|c| c.is_ascii_control() || c == '"' || c == '\\')
        || (scheme != "http" && scheme != "https")
        || parsed.authority().is_none()
    {
        return Err(message);
    }
    Ok(url.to_owned())
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex, OnceLock};
    use std::time::Duration;

    use axum::body::{Body, to_bytes};
    use axum::http::header::{ACCEPT, AUTHORIZATION, CONTENT_TYPE, HOST, WWW_AUTHENTICATE};
    use axum::http::{Request, StatusCode};
    use jsonwebtoken::jwk::JwkSet;
    use jsonwebtoken::{Algorithm, EncodingKey, Header, encode};
    use postgres_types::Json;
    use rmcp::model::JsonObject;
    use rsa::RsaPrivateKey;
    use rsa::pkcs1::{EncodeRsaPrivateKey, LineEnding};
    use tower::ServiceExt;

    use super::{
        Audit, Caller, JWKS_LIMIT, MCP_PATH, METADATA_PATH, Queue, TokenCheck, audit, database_url,
        extend_limited, issuer_url, lock, router,
    };

    const ISSUER: &str = "http://keycloak.example/realms/akwara";
    const AUDIENCE: &str = "gateway";
    const PUBLIC_URL: &str = "http://127.0.0.1:8080";
    const WHOAMI: &str = r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"whoami","arguments":{"user_id":"brian","tenant_id":"other"}}}"#;

    struct SigningKey {
        set: JwkSet,
        encoding: EncodingKey,
    }

    fn signing_key() -> &'static SigningKey {
        static KEY: OnceLock<SigningKey> = OnceLock::new();
        KEY.get_or_init(|| {
            let mut rng = rand::thread_rng();
            let key = RsaPrivateKey::new(&mut rng, 2048).expect("rsa key");
            let pem = key.to_pkcs1_pem(LineEnding::LF).expect("pem");
            let encoding = EncodingKey::from_rsa_pem(pem.as_bytes()).expect("encoding key");
            let mut jwk = jsonwebtoken::jwk::Jwk::from_encoding_key(&encoding, Algorithm::RS256)
                .expect("jwk");
            jwk.common.key_id = Some("test".to_owned());
            let set = JwkSet { keys: vec![jwk] };
            let set =
                serde_json::from_str(&serde_json::to_string(&set).expect("json")).expect("jwks");
            SigningKey { set, encoding }
        })
    }

    fn not_before() -> String {
        let now = jsonwebtoken::get_current_timestamp();
        let key = signing_key();
        let mut header = Header::new(Algorithm::RS256);
        header.kid = Some("test".to_owned());
        encode(
            &header,
            &serde_json::json!({
                "iss": ISSUER,
                "aud": AUDIENCE,
                "sub": "subject-1",
                "preferred_username": "amina",
                "exp": now + 7200,
                "nbf": now + 3600,
            }),
            &key.encoding,
        )
        .expect("token")
    }

    fn token(issuer: &str, audience: &str, username: &str) -> String {
        let key = signing_key();
        let mut header = Header::new(Algorithm::RS256);
        header.kid = Some("test".to_owned());
        encode(
            &header,
            &serde_json::json!({
                "iss": issuer,
                "aud": audience,
                "sub": "subject-1",
                "preferred_username": username,
                "exp": jsonwebtoken::get_current_timestamp() + 3600,
            }),
            &key.encoding,
        )
        .expect("token")
    }

    fn app(audit: Audit) -> axum::Router {
        router(
            TokenCheck::fixed(ISSUER, AUDIENCE, PUBLIC_URL, signing_key().set.clone())
                .expect("check"),
            audit,
        )
    }

    fn memory() -> Audit {
        Audit::Memory(Arc::default())
    }

    async fn call(audit: Audit, token: Option<&str>) -> axum::response::Response {
        let mut builder = Request::builder()
            .method("POST")
            .uri("/mcp")
            .header(HOST, "127.0.0.1")
            .header(CONTENT_TYPE, "application/json")
            .header(ACCEPT, "application/json, text/event-stream");
        if let Some(token) = token {
            builder = builder.header(AUTHORIZATION, format!("Bearer {token}"));
        }
        tokio::time::timeout(
            Duration::from_secs(5),
            app(audit).oneshot(builder.body(Body::from(WHOAMI)).expect("request")),
        )
        .await
        .expect("gateway hung")
        .expect("response")
    }

    async fn json(response: axum::response::Response) -> serde_json::Value {
        assert_eq!(response.status(), StatusCode::OK);
        let bytes = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("body");
        serde_json::from_slice(&bytes).unwrap_or_else(|error| {
            panic!("{error}: {}", String::from_utf8_lossy(&bytes));
        })
    }

    fn assert_amina_recorded(rows: &[audit::Row]) {
        assert_eq!(rows.len(), 1);
        let entry = &rows[0].entry;
        assert_eq!(entry.action, "whoami");
        assert_eq!(entry.actor_subject, "subject-1");
        assert_eq!(entry.actor_username, "amina");
        assert_eq!(
            serde_json::Value::Object(entry.arguments.clone()),
            serde_json::json!({"user_id": "brian", "tenant_id": "other"})
        );
        assert_eq!(audit::verify(rows), Ok(()));
    }

    #[test]
    fn jwks_body_over_one_megabyte_is_rejected() {
        let mut body = vec![0_u8; JWKS_LIMIT];
        assert!(!extend_limited(&mut body, b"x"));
        let mut body = Vec::new();
        assert!(extend_limited(&mut body, b"{}"));
    }

    #[test]
    fn http_issuer_is_rejected() {
        assert!(issuer_url("http://127.0.0.1:8443/realms/akwara").is_err());
        assert!(issuer_url("https://keycloak.example/realms/akwara").is_ok());
    }

    #[test]
    fn non_postgres_database_url_is_rejected() {
        assert!(database_url("mysql://ramonda_app@postgres/ramonda").is_err());
        assert!(database_url("host=postgres user=ramonda_app").is_err());
        assert!(database_url("postgres://ramonda_app:ramonda_app@postgres:5432/ramonda").is_ok());
        assert!(database_url("postgresql://ramonda_app@postgres/ramonda").is_ok());
    }

    #[tokio::test]
    async fn missing_token_points_at_keycloak() {
        let response = call(memory(), None).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let challenge = response.headers().get(WWW_AUTHENTICATE).expect("challenge");
        assert_eq!(
            challenge.to_str().expect("header"),
            format!("Bearer resource_metadata=\"{PUBLIC_URL}{METADATA_PATH}\"")
        );
        let response = app(memory())
            .oneshot(
                Request::builder()
                    .uri(METADATA_PATH)
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");
        let bytes = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("body");
        let document: serde_json::Value = serde_json::from_slice(&bytes).expect("json");
        assert_eq!(document["authorization_servers"][0], ISSUER);
        assert_eq!(document["resource"], format!("{PUBLIC_URL}{MCP_PATH}"));
    }

    #[tokio::test]
    async fn bad_signature_issuer_and_audience_are_rejected() {
        let good = token(ISSUER, AUDIENCE, "amina");
        let mut chars: Vec<char> = good.chars().collect();
        let index = chars.len() - 2;
        chars[index] = if chars[index] == 'a' { 'b' } else { 'a' };
        let tampered: String = chars.into_iter().collect();
        let cases = [
            tampered,
            token("http://evil.example/realms/akwara", AUDIENCE, "amina"),
            token(ISSUER, "someone-else", "amina"),
            not_before(),
        ];
        for token in cases {
            assert_eq!(
                call(memory(), Some(&token)).await.status(),
                StatusCode::UNAUTHORIZED
            );
        }
    }

    #[tokio::test]
    async fn unknown_kid_refetches_once() {
        let queue = Arc::new(Mutex::new(Queue {
            sets: std::collections::VecDeque::from([
                Arc::new(JwkSet { keys: vec![] }),
                Arc::new(signing_key().set.clone()),
            ]),
            fetches: 0,
        }));
        let check = TokenCheck::queued(Arc::clone(&queue));
        let caller = check
            .authenticate(Some(&format!(
                "Bearer {}",
                token(ISSUER, AUDIENCE, "amina")
            )))
            .await
            .expect("refetch");
        assert_eq!(caller.username, "amina");
        assert_eq!(lock(&queue).fetches, 2);
        let mut header = Header::new(Algorithm::RS256);
        header.kid = Some("missing".to_owned());
        let missing = encode(
            &header,
            &serde_json::json!({
                "iss": ISSUER,
                "aud": AUDIENCE,
                "sub": "subject-1",
                "preferred_username": "amina",
                "exp": jsonwebtoken::get_current_timestamp() + 3600,
            }),
            &signing_key().encoding,
        )
        .expect("token");
        assert!(
            check
                .authenticate(Some(&format!("Bearer {missing}")))
                .await
                .is_none()
        );
        assert_eq!(lock(&queue).fetches, 2);
    }

    #[tokio::test]
    async fn whoami_uses_the_token_not_the_argument() {
        let rows = Arc::default();
        let response = call(
            Audit::Memory(Arc::clone(&rows)),
            Some(&token(ISSUER, AUDIENCE, "amina")),
        )
        .await;
        assert_eq!(
            json(response).await["result"]["content"][0]["text"],
            "amina"
        );
        assert_amina_recorded(&lock(&rows));
    }

    #[tokio::test]
    async fn whoami_fails_without_the_username_when_the_audit_insert_fails() {
        let response = call(Audit::Failing, Some(&token(ISSUER, AUDIENCE, "amina"))).await;
        let payload = json(response).await;
        assert_eq!(payload["error"]["code"], -32603);
        assert!(!payload.to_string().contains("amina"), "{payload}");
    }

    async fn postgres(url: &str) -> tokio_postgres::Client {
        audit::connect(&url.parse().expect("url"))
            .await
            .expect("postgres")
    }

    fn writer(client: tokio_postgres::Client) -> Audit {
        Audit::Postgres(Arc::new(tokio::sync::Mutex::new(client)))
    }

    async fn stored(owner: &tokio_postgres::Client) -> Vec<audit::Row> {
        owner
            .query(
                "SELECT recorded_at, actor_subject, actor_username, action, arguments, \
                 previous_hash, hash FROM audit_log ORDER BY id",
                &[],
            )
            .await
            .expect("rows")
            .iter()
            .map(|row| audit::Row {
                entry: audit::Entry {
                    recorded_at: row.get(0),
                    actor_subject: row.get(1),
                    actor_username: row.get(2),
                    action: row.get(3),
                    arguments: row.get::<_, Json<JsonObject>>(4).0,
                },
                previous_hash: row.get(5),
                hash: row.get(6),
            })
            .collect()
    }

    #[tokio::test]
    #[ignore = "set RAMONDA_TEST_DATABASE_URL to the owner role"]
    async fn postgres_log_is_append_only_and_chained() {
        let owner_url =
            std::env::var("RAMONDA_TEST_DATABASE_URL").expect("RAMONDA_TEST_DATABASE_URL");
        let app_url = "postgres://ramonda_app:ramonda_app@127.0.0.1:5432/ramonda";
        let owner = postgres(&owner_url).await;
        let migration = std::fs::read_to_string(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../deploy/postgres/001_audit_log.sql"),
        )
        .expect("migration");
        owner.batch_execute(&migration).await.expect("migrate");
        owner
            .batch_execute("TRUNCATE audit_log")
            .await
            .expect("truncate");

        let audit = writer(postgres(app_url).await);
        let response = call(audit.clone(), Some(&token(ISSUER, AUDIENCE, "amina"))).await;
        assert_eq!(
            json(response).await["result"]["content"][0]["text"],
            "amina"
        );
        let rows = stored(&owner).await;
        assert_amina_recorded(&rows);

        let app = postgres(app_url).await;
        app.batch_execute("SELECT count(*) FROM audit_log")
            .await
            .expect("app role selects");
        for statement in [
            "UPDATE audit_log SET actor_username = 'brian'",
            "DELETE FROM audit_log",
            "TRUNCATE audit_log",
        ] {
            let error = app.batch_execute(statement).await.expect_err(statement);
            assert_eq!(
                error.code().map(tokio_postgres::error::SqlState::code),
                Some("42501"),
                "{error}"
            );
        }
        assert_eq!(stored(&owner).await, rows);

        owner
            .batch_execute("UPDATE audit_log SET actor_username = 'brian'")
            .await
            .expect("owner update");
        assert_eq!(audit::verify(&stored(&owner).await), Err(0));

        owner
            .batch_execute("TRUNCATE audit_log")
            .await
            .expect("truncate");
        let caller = Caller {
            subject: "subject-1".to_owned(),
            username: "amina".to_owned(),
        };
        for _ in 0..2 {
            audit
                .record("whoami", &caller, JsonObject::new())
                .await
                .expect("record");
        }
        owner
            .batch_execute("DELETE FROM audit_log WHERE id = (SELECT min(id) FROM audit_log)")
            .await
            .expect("owner delete");
        let rows = stored(&owner).await;
        assert_eq!(rows.len(), 1);
        assert_eq!(audit::verify(&rows), Err(0));

        owner
            .batch_execute("TRUNCATE audit_log")
            .await
            .expect("truncate");
        let writers = [audit, writer(postgres(app_url).await)];
        let tasks: Vec<_> = (0..8)
            .map(|index| {
                let audit = writers[index % 2].clone();
                let caller = caller.clone();
                tokio::spawn(async move {
                    audit
                        .record("whoami", &caller, JsonObject::new())
                        .await
                        .map_err(|error| error.to_string())
                })
            })
            .collect();
        for task in tasks {
            task.await.expect("join").expect("record");
        }
        let rows = stored(&owner).await;
        assert_eq!(rows.len(), 8);
        assert_eq!(audit::verify(&rows), Ok(()));
    }
}
