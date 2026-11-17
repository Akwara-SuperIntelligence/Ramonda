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
use rmcp::model::{CallToolRequestParams, JsonObject};
use rmcp::transport::StreamableHttpClientTransport;
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
    secrets: OpenBao,
    connector: String,
}

impl Config {
    /// Reads `KEYCLOAK_ISSUER`, `GATEWAY_AUDIENCE`, `GATEWAY_PUBLIC_URL`, `DATABASE_URL`, `OPENBAO_ADDR`, `OPENBAO_TOKEN`, `ODOO_MCP_URL`, optional `GATEWAY_BIND`, and optional `GATEWAY_TLS_CA`.
    ///
    /// # Errors
    ///
    /// Returns an error when a required variable is missing, the issuer is not https, the database URL is not postgres, the `OpenBao` address or token is rejected, the connector URL is not http or https, or the CA file cannot be read.
    pub fn from_env() -> Result<Self, String> {
        let issuer = issuer_url(&required("KEYCLOAK_ISSUER")?)?;
        let audience = required("GATEWAY_AUDIENCE")?;
        let public_url = http_url("GATEWAY_PUBLIC_URL", &required("GATEWAY_PUBLIC_URL")?)?;
        let ca_pem = tls_ca()?;
        let secrets = OpenBao::new(&required("OPENBAO_ADDR")?, &required("OPENBAO_TOKEN")?)
            .map_err(|error| error.to_string())?;
        let connector = http_url("ODOO_MCP_URL", &required("ODOO_MCP_URL")?)?;
        Ok(Self {
            check: TokenCheck::remote(issuer, audience, public_url, ca_pem)?,
            bind: bind_address()?,
            database: database_url(&required("DATABASE_URL")?)?,
            secrets,
            connector,
        })
    }
}

/// Connects to Postgres, then listens for Streamable HTTP MCP calls.
///
/// # Errors
///
/// Returns an error when Postgres refuses the connection, the socket cannot bind, or the server stops.
pub async fn serve(config: Config) -> std::io::Result<()> {
    let audit = Audit::Postgres(
        PostgresAudit::open(config.database)
            .await
            .map_err(std::io::Error::other)?,
    );
    let listener = TcpListener::bind(&config.bind).await?;
    axum::serve(
        listener,
        router(config.check, audit, config.secrets, config.connector),
    )
    .await
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

fn router(check: TokenCheck, audit: Audit, secrets: OpenBao, connector: String) -> Router {
    let mcp = StreamableHttpService::new(
        move || {
            Ok(Gateway {
                audit: audit.clone(),
                secrets: secrets.clone(),
                connector: connector.clone(),
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

struct PostgresAudit {
    config: tokio_postgres::Config,
    client: tokio::sync::Mutex<tokio_postgres::Client>,
}

impl PostgresAudit {
    async fn open(config: tokio_postgres::Config) -> Result<Arc<Self>, tokio_postgres::Error> {
        let client = audit::connect(&config).await?;
        Ok(Arc::new(Self {
            config,
            client: tokio::sync::Mutex::new(client),
        }))
    }

    async fn insert(&self, entry: audit::Entry) -> Result<(), audit::Failure> {
        let mut client = self.client.lock().await;
        if client.is_closed() {
            let fresh = audit::connect(&self.config).await?;
            *client = fresh;
        }
        audit::insert(&mut client, entry).await
    }
}

#[derive(Clone)]
enum Audit {
    Postgres(Arc<PostgresAudit>),
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
            Self::Postgres(postgres) => postgres.insert(entry).await,
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
    secrets: OpenBao,
    connector: String,
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

    #[tool(
        description = "Read point-of-sale lines for one branch and date range. A user id in the arguments is ignored."
    )]
    async fn odoo_pos_sales(
        &self,
        Extension(parts): Extension<Parts>,
        arguments: JsonObject,
    ) -> Result<String, ErrorData> {
        self.odoo_read(&parts, &arguments, "odoo_pos_sales", "pos_sales", "qty")
            .await
    }

    #[tool(
        description = "Read bakery delivery lines for one branch and date range. A user id in the arguments is ignored."
    )]
    async fn odoo_bakery_deliveries(
        &self,
        Extension(parts): Extension<Parts>,
        arguments: JsonObject,
    ) -> Result<String, ErrorData> {
        self.odoo_read(
            &parts,
            &arguments,
            "odoo_bakery_deliveries",
            "bakery_deliveries",
            "qty_delivered",
        )
        .await
    }

    async fn odoo_read(
        &self,
        parts: &Parts,
        arguments: &JsonObject,
        action: &str,
        tool: &str,
        qty_field: &str,
    ) -> Result<String, ErrorData> {
        let caller = parts
            .extensions
            .get::<Caller>()
            .ok_or_else(|| ErrorData::internal_error("missing caller", None))?;
        let Some(window) = read_window(arguments) else {
            self.audit
                .record(action, caller, rejected())
                .await
                .map_err(|_| ErrorData::internal_error("audit write failed", None))?;
            return Err(ErrorData::invalid_params(
                "branch, start, and end are required",
                None,
            ));
        };
        self.audit
            .record(action, caller, window.arguments())
            .await
            .map_err(|_| ErrorData::internal_error("audit write failed", None))?;
        let username = &caller.username;
        let path = format!("odoo/{username}");
        let odoo = self
            .secrets
            .read_odoo(&path)
            .await
            .map_err(|error| ErrorData::internal_error(error.to_string(), None))?;
        let body = self
            .connector_rows(
                tool,
                &window,
                odoo.login.expose(),
                odoo.password.expose(),
                Duration::from_secs(30),
            )
            .await?;
        let rows = project_rows(&body, qty_field)
            .ok_or_else(|| ErrorData::internal_error("odoo read failed", None))?;
        serde_json::to_string(&rows)
            .map_err(|_| ErrorData::internal_error("odoo read failed", None))
    }

    async fn connector_rows(
        &self,
        tool: &str,
        window: &Window,
        login: &str,
        credential: &str,
        deadline: Duration,
    ) -> Result<serde_json::Value, ErrorData> {
        let failed = || ErrorData::internal_error("odoo read failed", None);
        let fetch = async {
            let transport = StreamableHttpClientTransport::from_uri(self.connector.clone());
            let client = rmcp::serve_client((), transport)
                .await
                .map_err(|_| failed())?;
            let arguments = serde_json::json!({
                "branch": &window.branch,
                "start": &window.start,
                "end": &window.end,
                "login": login,
                "credential": credential,
            });
            let Some(arguments) = arguments.as_object().cloned() else {
                return Err(failed());
            };
            let result = client
                .call_tool(CallToolRequestParams::new(tool.to_owned()).with_arguments(arguments))
                .await
                .map_err(|_| failed())?;
            if result.is_error == Some(true) {
                return Err(failed());
            }
            result.structured_content.ok_or_else(failed)
        };
        match tokio::time::timeout(deadline, fetch).await {
            Ok(result) => result,
            Err(_) => Err(failed()),
        }
    }
}

struct Window {
    branch: String,
    start: String,
    end: String,
}

impl Window {
    fn arguments(&self) -> JsonObject {
        serde_json::json!({
            "branch": &self.branch,
            "start": &self.start,
            "end": &self.end,
        })
        .as_object()
        .cloned()
        .expect("window")
    }
}

fn read_window(arguments: &JsonObject) -> Option<Window> {
    let branch = arguments.get("branch")?.as_str()?;
    let start = arguments.get("start")?.as_str()?;
    let end = arguments.get("end")?.as_str()?;
    if branch.is_empty() || branch.len() > 128 || branch.chars().any(char::is_control) {
        return None;
    }
    let start = chrono::NaiveDate::parse_from_str(start, "%Y-%m-%d").ok()?;
    let end = chrono::NaiveDate::parse_from_str(end, "%Y-%m-%d").ok()?;
    Some(Window {
        branch: branch.to_owned(),
        start: start.to_string(),
        end: end.to_string(),
    })
}

fn rejected() -> JsonObject {
    serde_json::json!({"rejected": true})
        .as_object()
        .cloned()
        .expect("rejected")
}

fn project_rows(value: &serde_json::Value, qty_field: &str) -> Option<Vec<serde_json::Value>> {
    let list = value.get("result")?.as_array()?;
    list.iter()
        .map(|row| {
            let row = row.as_object()?;
            let date = row.get("date")?.as_str()?;
            let product = row.get("product")?.as_str()?;
            let qty = row.get(qty_field)?.as_f64()?;
            Some(serde_json::json!({
                "date": date,
                "product": product,
                qty_field: qty,
            }))
        })
        .collect()
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

const SECRET_LIMIT: usize = 65_536;

/// `OpenBao` key/value v2 reader. The value from [`OpenBao::read`] is not kept on this client.
#[derive(Clone)]
pub struct OpenBao {
    base: String,
    token: String,
    client: reqwest::Client,
}

/// One field of one named secret. Formatting it does not reveal the value.
pub struct Secret(String);

#[derive(Debug)]
struct OdooSecret {
    login: Secret,
    password: Secret,
}

/// Why a secret read did not return a value. The text is fixed and has no response body.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SecretError {
    Rejected,
    Unavailable,
    Denied,
    Missing,
    Malformed,
}

impl OpenBao {
    /// Builds a client for `base_url` (for example `http://127.0.0.1:8200`).
    ///
    /// # Errors
    ///
    /// Returns [`SecretError::Rejected`] when the address is not a bare http or https origin or
    /// the token cannot be sent as a header.
    /// Returns [`SecretError::Unavailable`] when the HTTP client cannot be built.
    #[must_use = "the client is the only way to read a secret"]
    pub fn new(base_url: &str, token: &str) -> Result<Self, SecretError> {
        let base = base_url.trim().trim_end_matches('/');
        if !valid_openbao_base(base) || !valid_token(token) {
            return Err(SecretError::Rejected);
        }
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(5))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|_| SecretError::Unavailable)?;
        Ok(Self {
            base: base.to_owned(),
            token: token.to_owned(),
            client,
        })
    }

    /// Reads one field of the named key/value v2 secret.
    ///
    /// # Errors
    ///
    /// Returns [`SecretError::Rejected`] when `name` is not `/`-separated segments of ASCII
    /// letters, digits, `-`, or `_`, when `field` is not one such segment, or when either is
    /// too long.
    /// Returns [`SecretError::Denied`], [`SecretError::Missing`], [`SecretError::Malformed`], or
    /// [`SecretError::Unavailable`] for the store's answer.
    pub async fn read(&self, name: &str, field: &str) -> Result<Secret, SecretError> {
        if !valid_field(field) {
            return Err(SecretError::Rejected);
        }
        field_secret(&self.fetch(name).await?, field)
    }

    async fn read_odoo(&self, name: &str) -> Result<OdooSecret, SecretError> {
        let value = self.fetch(name).await?;
        Ok(OdooSecret {
            login: field_secret(&value, "login")?,
            password: field_secret(&value, "password")?,
        })
    }

    async fn fetch(&self, name: &str) -> Result<serde_json::Value, SecretError> {
        if !valid_secret_name(name) {
            return Err(SecretError::Rejected);
        }
        let url = format!("{}/v1/secret/data/{name}", self.base);
        let response = self
            .client
            .get(url)
            .header("X-Vault-Token", &self.token)
            .send()
            .await
            .map_err(|_| SecretError::Unavailable)?;
        match response.status().as_u16() {
            401 | 403 => return Err(SecretError::Denied),
            404 => return Err(SecretError::Missing),
            200 => {}
            _ => return Err(SecretError::Unavailable),
        }
        let body = limited_body(response, SECRET_LIMIT).await?;
        serde_json::from_slice(&body).map_err(|_| SecretError::Malformed)
    }
}

fn field_secret(value: &serde_json::Value, field: &str) -> Result<Secret, SecretError> {
    value
        .get("data")
        .and_then(|data| data.get("data"))
        .and_then(|data| data.get(field))
        .and_then(serde_json::Value::as_str)
        .map(|text| Secret(text.to_owned()))
        .ok_or(SecretError::Malformed)
}

impl Secret {
    /// The secret value.
    #[must_use]
    pub fn expose(&self) -> &str {
        &self.0
    }
}

impl std::fmt::Debug for OpenBao {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("OpenBao")
            .field("base", &self.base)
            .finish_non_exhaustive()
    }
}

impl std::fmt::Debug for Secret {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.debug_tuple("Secret").finish_non_exhaustive()
    }
}

impl std::fmt::Display for Secret {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("Secret")
    }
}

impl std::fmt::Display for SecretError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::Rejected => "secret request rejected",
            Self::Unavailable => "secret store unavailable",
            Self::Denied => "secret read denied",
            Self::Missing => "secret missing",
            Self::Malformed => "secret response malformed",
        })
    }
}

impl std::error::Error for SecretError {}

fn valid_openbao_base(base: &str) -> bool {
    let Some(rest) = base
        .strip_prefix("https://")
        .or_else(|| base.strip_prefix("http://"))
    else {
        return false;
    };
    !rest.is_empty()
        && !rest.contains('/')
        && !rest.contains('?')
        && !rest.contains('#')
        && !rest.contains('@')
        && rest.bytes().all(|byte| byte.is_ascii_graphic())
}

fn valid_token(token: &str) -> bool {
    let bytes = token.as_bytes();
    !bytes.is_empty()
        && bytes.len() <= 512
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_graphic() && *byte != b'"' && *byte != b'\\')
}

fn valid_secret_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 256
        && !name.starts_with('/')
        && !name.ends_with('/')
        && name.split('/').all(|part| {
            !part.is_empty()
                && part != "."
                && part != ".."
                && part
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
        })
}

fn valid_field(field: &str) -> bool {
    !field.is_empty()
        && field.len() <= 128
        && field
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-')
}

async fn limited_body(
    mut response: reqwest::Response,
    limit: usize,
) -> Result<Vec<u8>, SecretError> {
    if response
        .content_length()
        .is_some_and(|len| len > u64::try_from(limit).unwrap_or(u64::MAX))
    {
        return Err(SecretError::Malformed);
    }
    let mut body = Vec::new();
    loop {
        match response.chunk().await {
            Ok(Some(chunk)) => {
                if body.len().saturating_add(chunk.len()) > limit {
                    return Err(SecretError::Malformed);
                }
                body.extend_from_slice(&chunk);
            }
            Ok(None) => return Ok(body),
            Err(_) => return Err(SecretError::Unavailable),
        }
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
    use rmcp::model::{CallToolResult, JsonObject};
    use rmcp::{ServerHandler, tool, tool_handler, tool_router};
    use rsa::RsaPrivateKey;
    use rsa::pkcs1::{EncodeRsaPrivateKey, LineEnding};
    use tower::ServiceExt;

    use super::{
        Audit, Caller, JWKS_LIMIT, LocalSessionManager, MCP_PATH, METADATA_PATH, OpenBao,
        PostgresAudit, Queue, SecretError, StreamableHttpServerConfig, StreamableHttpService,
        TokenCheck, audit, database_url, extend_limited, issuer_url, lock, router,
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
        odoo_app("http://127.0.0.1:9", "http://127.0.0.1:9/mcp", audit)
    }

    fn odoo_app(bao: &str, connector: &str, audit: Audit) -> axum::Router {
        router(
            TokenCheck::fixed(ISSUER, AUDIENCE, PUBLIC_URL, signing_key().set.clone())
                .expect("check"),
            audit,
            OpenBao::new(bao, "local-token").expect("bao"),
            connector.to_owned(),
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

    async fn postgres(config: &tokio_postgres::Config) -> tokio_postgres::Client {
        audit::connect(config).await.expect("postgres")
    }

    fn app_role(owner: &tokio_postgres::Config) -> tokio_postgres::Config {
        let mut config = owner.clone();
        config.user("ramonda_app");
        config.password("ramonda_app");
        config
    }

    async fn app_cannot_change(app: &tokio_postgres::Client) {
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
    }

    async fn writer(config: &tokio_postgres::Config) -> Audit {
        Audit::Postgres(PostgresAudit::open(config.clone()).await.expect("writer"))
    }

    async fn closed_client(config: &tokio_postgres::Config) -> tokio_postgres::Client {
        let (closed, connection) = config.connect(tokio_postgres::NoTls).await.expect("pair");
        tokio::spawn(async move {
            let _ = connection.await;
        })
        .abort();
        let deadline = tokio::time::Instant::now() + Duration::from_secs(2);
        while !closed.is_closed() {
            assert!(tokio::time::Instant::now() < deadline, "client stayed open");
            tokio::task::yield_now().await;
        }
        closed
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
        let owner_config = owner_url
            .parse::<tokio_postgres::Config>()
            .expect("owner url");
        let app_config = app_role(&owner_config);
        let owner = postgres(&owner_config).await;
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

        let audit = writer(&app_config).await;
        let response = call(audit.clone(), Some(&token(ISSUER, AUDIENCE, "amina"))).await;
        assert_eq!(
            json(response).await["result"]["content"][0]["text"],
            "amina"
        );
        let rows = stored(&owner).await;
        assert_amina_recorded(&rows);

        app_cannot_change(&postgres(&app_config).await).await;
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
        let writers = [audit.clone(), writer(&app_config).await];
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

        let Audit::Postgres(postgres_audit) = &audit else {
            panic!("writer");
        };
        *postgres_audit.client.lock().await = closed_client(&app_config).await;
        audit
            .record("whoami", &caller, JsonObject::new())
            .await
            .expect("reconnect");
        let rows = stored(&owner).await;
        assert_eq!(rows.len(), 9);
        assert_eq!(audit::verify(&rows), Ok(()));
    }

    fn http_response(status: u16, body: &str) -> Vec<u8> {
        format!(
            "HTTP/1.1 {status} X\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
            body.len()
        )
        .into_bytes()
    }

    fn serve(responses: Vec<Vec<u8>>) -> u16 {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("addr").port();
        std::thread::spawn(move || {
            for response in responses {
                let (mut sock, _) = listener.accept().expect("accept");
                let mut buf = [0_u8; 4096];
                let _ = std::io::Read::read(&mut sock, &mut buf);
                let _ = std::io::Write::write_all(&mut sock, &response);
            }
        });
        port
    }

    fn serve_recorded(response: Vec<u8>) -> (u16, Arc<Mutex<Vec<u8>>>) {
        let seen = Arc::new(Mutex::new(Vec::new()));
        let record = Arc::clone(&seen);
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("addr").port();
        std::thread::spawn(move || {
            let (mut sock, _) = listener.accept().expect("accept");
            let mut buf = [0_u8; 4096];
            let n = std::io::Read::read(&mut sock, &mut buf).unwrap_or(0);
            record.lock().expect("record").extend_from_slice(&buf[..n]);
            let _ = std::io::Write::write_all(&mut sock, &response);
        });
        (port, seen)
    }

    fn rendered_error(error: SecretError) -> String {
        format!("{error} {error:?}")
    }

    #[tokio::test]
    async fn read_returns_the_field_and_hides_it() {
        let secret = "probe-secret-9f3c2a";
        let token = "token-do-not-leak-77ab";
        let leaked = format!(r#"{{"errors":["{secret} {token}"]}}"#);
        let good = format!(r#"{{"data":{{"data":{{"password":"{secret}"}}}}}}"#);
        let changed = format!(r#"{{"data":{{"data":{{"password":"{secret}-next"}}}}}}"#);
        let port = serve(vec![
            http_response(500, &leaked),
            http_response(200, &good),
            http_response(200, &changed),
            http_response(
                200,
                &format!(r#"{{"data":{{"data":{{"login":"{secret}"}}}}}}"#),
            ),
        ]);
        let bao = OpenBao::new(&format!("http://127.0.0.1:{port}"), token).expect("client");
        let error = bao
            .read("odoo/amina", "password")
            .await
            .expect_err("status");
        assert_eq!(error, SecretError::Unavailable);
        assert!(!rendered_error(error).contains(secret));
        assert!(!rendered_error(error).contains(token));
        let first = bao.read("odoo/amina", "password").await.expect("read");
        assert_eq!(first.expose(), secret);
        assert!(!format!("{first} {first:?} {bao:?}").contains(secret));
        assert!(!format!("{bao:?}").contains(token));
        let second = bao.read("odoo/amina", "password").await.expect("reread");
        assert_eq!(second.expose(), format!("{secret}-next"));
        let missing_field = bao.read("odoo/amina", "password").await.expect_err("field");
        assert_eq!(missing_field, SecretError::Malformed);
        assert!(!rendered_error(missing_field).contains(secret));
    }

    #[tokio::test]
    async fn one_read_returns_both_odoo_fields() {
        let login = "probe-login-9f3c2a";
        let password = "probe-password-9f3c2a";
        let both =
            format!(r#"{{"data":{{"data":{{"login":"{login}","password":"{password}"}}}}}}"#);
        let (port, seen) = serve_recorded(http_response(200, &both));
        let bao = OpenBao::new(
            &format!("http://127.0.0.1:{port}"),
            "token-do-not-leak-77ab",
        )
        .expect("client");
        let got = bao.read_odoo("odoo/amina").await.expect("both");
        assert_eq!(got.login.expose(), login);
        assert_eq!(got.password.expose(), password);
        let rendered = format!(
            "{} {:?} {} {:?}",
            got.login, got.login, got.password, got.password
        );
        assert!(!rendered.contains(login));
        assert!(!rendered.contains(password));
        assert_one_get(&seen, "odoo/amina");

        let missing_password = format!(r#"{{"data":{{"data":{{"login":"{login}"}}}}}}"#);
        assert_missing_odoo_field(&missing_password, login).await;
        let missing_login = format!(r#"{{"data":{{"data":{{"password":"{password}"}}}}}}"#);
        assert_missing_odoo_field(&missing_login, password).await;

        let closed = OpenBao::new("http://127.0.0.1:9", "local-token").expect("client");
        assert_eq!(
            closed
                .read_odoo("odoo/../amina")
                .await
                .expect_err("rejected"),
            SecretError::Rejected
        );
    }

    async fn assert_missing_odoo_field(body: &str, present: &str) {
        let (port, seen) = serve_recorded(http_response(200, body));
        let bao = OpenBao::new(&format!("http://127.0.0.1:{port}"), "local-token").expect("client");
        let error = bao.read_odoo("odoo/amina").await.expect_err("field");
        assert_eq!(error, SecretError::Malformed);
        assert!(!rendered_error(error).contains(present));
        assert_one_get(&seen, "odoo/amina");
    }

    fn assert_one_get(seen: &Mutex<Vec<u8>>, name: &str) {
        let request = String::from_utf8(seen.lock().expect("record").clone()).expect("utf8");
        let gets = request.matches("GET ").count();
        let path = request.starts_with(&format!("GET /v1/secret/data/{name} "));
        assert_eq!(gets, 1);
        assert!(path);
    }

    #[tokio::test]
    async fn rejected_names_do_not_call_openbao() {
        let bao = OpenBao::new("http://127.0.0.1:9", "local-token").expect("client");
        let doubled = ["odoo", "", "amina"].join("/");
        for (name, field) in [
            ("../sys/policy", "password"),
            ("odoo/../amina", "password"),
            (doubled.as_str(), "password"),
            ("odoo/amina", "pass/word"),
            ("", "password"),
            ("odoo/amina\r\nX-Other: 1", "password"),
        ] {
            assert_eq!(
                bao.read(name, field).await.expect_err("rejected"),
                SecretError::Rejected
            );
        }
        assert!(OpenBao::new("http://127.0.0.1:8200", "bad token").is_err());
        assert!(OpenBao::new("file:///tmp/openbao", "token").is_err());
    }

    #[tokio::test]
    #[ignore = "needs compose OpenBao with the demo Odoo logins"]
    async fn reads_known_secret_from_openbao() {
        let base =
            std::env::var("OPENBAO_ADDR").unwrap_or_else(|_| "http://127.0.0.1:8200".to_owned());
        let token = std::env::var("OPENBAO_TOKEN").expect("OPENBAO_TOKEN");
        let bao = OpenBao::new(&base, &token).expect("client");
        let probe = "probe-openbao-9f3c2a";
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(5))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .expect("client");
        let planted = client
            .post(format!("{base}/v1/secret/data/ramonda/probe"))
            .header("X-Vault-Token", &token)
            .header("Content-Type", "application/json")
            .body(format!(r#"{{"data":{{"value":"{probe}"}}}}"#))
            .send()
            .await
            .expect("plant");
        assert!(planted.status().is_success());
        let got = bao.read("ramonda/probe", "value").await.expect("probe");
        assert!(got.expose() == probe, "probe mismatch");
        assert!(!format!("{got} {got:?}").contains(probe));
        let missing = bao
            .read("ramonda/missing", "value")
            .await
            .expect_err("missing");
        assert_eq!(missing, SecretError::Missing);
        assert!(!rendered_error(missing).contains(probe));
        let logins = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../deploy/odoo/logins.json"
        ))
        .expect("logins");
        let rows: Vec<serde_json::Value> = serde_json::from_str(&logins).expect("json");
        assert!(rows.len() >= 2);
        for row in rows {
            let login = row["login"].as_str().expect("login");
            let password = row["password"].as_str().expect("password");
            let stored = bao
                .read(&format!("odoo/{login}"), "password")
                .await
                .expect("seeded");
            assert!(stored.expose() == password, "seeded password mismatch");
            let login_field = bao
                .read(&format!("odoo/{login}"), "login")
                .await
                .expect("login field");
            assert!(login_field.expose() == login, "seeded login mismatch");
            let hidden = bao
                .read(&format!("odoo/{login}"), "absent")
                .await
                .expect_err("absent field");
            assert_eq!(hidden, SecretError::Malformed);
            let rendered = format!("{stored} {stored:?} {hidden} {hidden:?} {bao:?}");
            assert!(!rendered.contains(password));
        }
    }

    #[derive(Clone)]
    struct Probe {
        calls: Arc<Mutex<Vec<JsonObject>>>,
    }

    #[tool_router]
    impl Probe {
        #[tool(description = "Record one sales read.")]
        fn pos_sales(&self, arguments: JsonObject) -> CallToolResult {
            lock(&self.calls).push(arguments);
            CallToolResult::structured(serde_json::json!({
                "result": [{
                    "date": "2026-09-22",
                    "product": "Butter croissant",
                    "qty": 74
                }]
            }))
        }

        #[tool(description = "Record one delivery read.")]
        fn bakery_deliveries(&self, arguments: JsonObject) -> CallToolResult {
            lock(&self.calls).push(arguments);
            CallToolResult::structured(serde_json::json!({
                "result": [{
                    "date": "2026-09-22",
                    "product": "Butter croissant",
                    "qty_delivered": 80
                }]
            }))
        }
    }

    #[allow(clippy::unused_async_trait_impl)]
    #[tool_handler]
    impl ServerHandler for Probe {}

    async fn spawn_probe(calls: Arc<Mutex<Vec<JsonObject>>>) -> String {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .expect("bind");
        let port = listener.local_addr().expect("addr").port();
        let service = StreamableHttpService::new(
            move || {
                Ok(Probe {
                    calls: Arc::clone(&calls),
                })
            },
            Arc::new(LocalSessionManager::default()),
            StreamableHttpServerConfig::default()
                .with_legacy_session_mode(false)
                .with_json_response(true),
        );
        let app = axum::Router::new().nest_service("/mcp", service);
        tokio::spawn(async move {
            axum::serve(listener, app).await.expect("probe");
        });
        let deadline = tokio::time::Instant::now() + Duration::from_secs(2);
        loop {
            if tokio::net::TcpStream::connect(("127.0.0.1", port))
                .await
                .is_ok()
            {
                break;
            }
            assert!(
                tokio::time::Instant::now() < deadline,
                "probe did not listen"
            );
            tokio::task::yield_now().await;
        }
        format!("http://127.0.0.1:{port}/mcp")
    }

    fn odoo_body(name: &str, start: &str, secret: &str) -> String {
        format!(
            r#"{{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{{"name":"{name}","arguments":{{"branch":"Westlands","start":"{start}","end":"2026-11-16","user_id":"brian","credential":"{secret}"}}}}}}"#
        )
    }

    async fn post(app: axum::Router, token: &str, body: &str) -> axum::response::Response {
        tokio::time::timeout(
            Duration::from_secs(15),
            app.oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp")
                    .header(HOST, "127.0.0.1")
                    .header(CONTENT_TYPE, "application/json")
                    .header(ACCEPT, "application/json, text/event-stream")
                    .header(AUTHORIZATION, format!("Bearer {token}"))
                    .body(Body::from(body.to_owned()))
                    .expect("request"),
            ),
        )
        .await
        .expect("gateway hung")
        .expect("response")
    }

    fn assert_hidden(body: &str, secret: &str, needle: &str) {
        assert!(body.contains(needle), "missing {needle}");
        assert!(!body.contains(secret), "response leaked the credential");
    }

    fn assert_window(arguments: &JsonObject) {
        assert_eq!(
            serde_json::Value::Object(arguments.clone()),
            serde_json::json!({
                "branch": "Westlands",
                "start": "2026-09-22",
                "end": "2026-11-16"
            })
        );
    }

    async fn tool_text(
        app: axum::Router,
        token: &str,
        name: &str,
        start: &str,
        secret: &str,
    ) -> serde_json::Value {
        json(post(app, token, &odoo_body(name, start, secret)).await).await
    }

    fn assert_rows(payload: &serde_json::Value, secret: &str, expected: &serde_json::Value) {
        let text = payload["result"]["content"][0]["text"]
            .as_str()
            .expect("text");
        assert_hidden(text, secret, "Butter croissant");
        assert_eq!(
            &serde_json::from_str::<serde_json::Value>(text).expect("rows"),
            expected
        );
    }

    fn assert_recorded(calls: &Mutex<Vec<JsonObject>>, secret: &str, count: usize) {
        let recorded = lock(calls);
        assert_eq!(recorded.len(), count);
        for arguments in recorded.iter().skip(recorded.len().saturating_sub(2)) {
            assert_eq!(
                arguments.get("login").and_then(|value| value.as_str()),
                Some("amina")
            );
            assert!(arguments.get("user_id").is_none(), "forwarded user_id");
            let credential = arguments
                .get("credential")
                .and_then(|value| value.as_str())
                .unwrap_or("");
            assert!(credential == secret, "credential mismatch");
        }
    }

    fn assert_chain(rows: &Mutex<Vec<audit::Row>>, actions: &[&str]) {
        let stored = lock(rows);
        assert_eq!(stored.len(), actions.len());
        assert_eq!(audit::verify(&stored), Ok(()));
        for (row, action) in stored.iter().zip(actions) {
            assert_eq!(row.entry.action, *action);
            assert_eq!(row.entry.actor_subject, "subject-1");
            assert_eq!(row.entry.actor_username, "amina");
            assert_window(&row.entry.arguments);
        }
    }

    #[tokio::test]
    async fn odoo_tools_use_the_token_user_and_audit_the_read() {
        let secret = "probe-secret-9f3c2a";
        let calls = Arc::new(Mutex::new(Vec::new()));
        let connector = spawn_probe(Arc::clone(&calls)).await;
        let both = format!(r#"{{"data":{{"data":{{"login":"amina","password":"{secret}"}}}}}}"#);
        let bao = serve(vec![
            http_response(500, &format!(r#"{{"errors":["{secret}"]}}"#)),
            http_response(200, &both),
            http_response(200, &both),
        ]);
        let rows = Arc::default();
        let app = odoo_app(
            &format!("http://127.0.0.1:{bao}"),
            &connector,
            Audit::Memory(Arc::clone(&rows)),
        );
        let signed_in = token(ISSUER, AUDIENCE, "amina");
        let denied = tool_text(
            app.clone(),
            &signed_in,
            "odoo_pos_sales",
            "2026-09-22",
            secret,
        )
        .await;
        assert_hidden(&denied.to_string(), secret, "secret store unavailable");
        assert!(lock(&calls).is_empty(), "connector ran without a secret");
        let sales = tool_text(
            app.clone(),
            &signed_in,
            "odoo_pos_sales",
            "2026-09-22",
            secret,
        )
        .await;
        assert_rows(
            &sales,
            secret,
            &serde_json::json!([{
                "date": "2026-09-22",
                "product": "Butter croissant",
                "qty": 74.0
            }]),
        );
        let deliveries = tool_text(
            app.clone(),
            &signed_in,
            "odoo_bakery_deliveries",
            "2026-09-22",
            secret,
        )
        .await;
        assert_rows(
            &deliveries,
            secret,
            &serde_json::json!([{
                "date": "2026-09-22",
                "product": "Butter croissant",
                "qty_delivered": 80.0
            }]),
        );
        assert_recorded(&calls, secret, 2);
        assert_chain(
            &rows,
            &["odoo_pos_sales", "odoo_pos_sales", "odoo_bakery_deliveries"],
        );
        assert_rejections(app, &connector, &signed_in, secret, &calls, &rows).await;
    }

    async fn assert_rejections(
        app: axum::Router,
        connector: &str,
        signed_in: &str,
        secret: &str,
        calls: &Mutex<Vec<JsonObject>>,
        rows: &Mutex<Vec<audit::Row>>,
    ) {
        let rejected = tool_text(app, signed_in, "odoo_pos_sales", "not-a-date", secret).await;
        let rejected_body = rejected.to_string();
        assert_hidden(
            &rejected_body,
            secret,
            "branch, start, and end are required",
        );
        assert!(!rejected_body.contains("not-a-date"), "echoed the argument");
        assert_eq!(lock(calls).len(), 2, "connector ran on a bad date");
        {
            let stored = lock(rows);
            assert_eq!(stored.len(), 4);
            assert_eq!(audit::verify(&stored), Ok(()));
            assert_eq!(
                serde_json::Value::Object(stored[3].entry.arguments.clone()),
                serde_json::json!({"rejected": true})
            );
        }
        let failed = tool_text(
            odoo_app("http://127.0.0.1:9", connector, Audit::Failing),
            signed_in,
            "odoo_pos_sales",
            "2026-09-22",
            secret,
        )
        .await;
        let failed_body = failed.to_string();
        assert_hidden(&failed_body, secret, "audit write failed");
        assert!(!failed_body.contains("amina"), "error named the caller");
        assert_eq!(lock(calls).len(), 2, "connector ran without an audit row");
    }

    #[tokio::test]
    async fn connector_call_stops_when_the_peer_never_answers() {
        let secret = "probe-secret-9f3c2a";
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .expect("bind");
        let port = listener.local_addr().expect("addr").port();
        tokio::spawn(async move {
            let mut open = Vec::new();
            while let Ok((stream, _)) = listener.accept().await {
                open.push(stream);
            }
        });
        let gateway = super::Gateway {
            audit: Audit::Failing,
            secrets: OpenBao::new("http://127.0.0.1:9", "local-token").expect("bao"),
            connector: format!("http://127.0.0.1:{port}/mcp"),
        };
        let window = super::Window {
            branch: "Westlands".to_owned(),
            start: "2026-09-22".to_owned(),
            end: "2026-11-16".to_owned(),
        };
        let deadline = Duration::from_millis(200);
        let started = tokio::time::Instant::now();
        let error = tokio::time::timeout(
            Duration::from_secs(2),
            gateway.connector_rows("pos_sales", &window, "amina", secret, deadline),
        )
        .await
        .expect("deadline did not fire")
        .expect_err("hung");
        assert!(
            started.elapsed() >= deadline,
            "returned before the deadline"
        );
        let rendered = format!("{error}");
        assert!(
            rendered.contains("odoo read failed"),
            "missing deadline error"
        );
        assert!(!rendered.contains(secret), "response leaked the credential");
    }
}
