use std::sync::Arc;
use std::time::{Duration, Instant};

use axum::body::Body;
use axum::extract::State;
use axum::http::header::{AUTHORIZATION, WWW_AUTHENTICATE};
use axum::http::request::Parts;
use axum::http::{HeaderValue, StatusCode};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use jsonwebtoken::jwk::{AlgorithmParameters, JwkSet, KeyAlgorithm};
use jsonwebtoken::{Algorithm, DecodingKey, Validation, decode, decode_header};
use rmcp::handler::server::tool::Extension;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::transport::streamable_http_server::session::local::LocalSessionManager;
use rmcp::transport::streamable_http_server::{StreamableHttpServerConfig, StreamableHttpService};
use rmcp::{ErrorData, ServerHandler, tool, tool_handler, tool_router};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use tokio::net::TcpListener;
use tokio::sync::RwLock;

const MCP_PATH: &str = "/mcp";
const METADATA_PATH: &str = "/.well-known/oauth-protected-resource/mcp";
const JWKS_PATH: &str = "/protocol/openid-connect/certs";
const JWKS_LIMIT: usize = 1_048_576;
const JWKS_REFRESH: Duration = Duration::from_secs(60);

/// Settings the process reads before it listens.
pub struct Config {
    check: TokenCheck,
    bind: String,
}

impl Config {
    /// Reads `KEYCLOAK_ISSUER`, `GATEWAY_AUDIENCE`, `GATEWAY_PUBLIC_URL`, and optional `GATEWAY_BIND`.
    ///
    /// # Errors
    ///
    /// Returns an error when a required variable is missing or a URL is not http or https.
    pub fn from_env() -> Result<Self, String> {
        let issuer = http_url("KEYCLOAK_ISSUER", &required("KEYCLOAK_ISSUER")?)?;
        let audience = required("GATEWAY_AUDIENCE")?;
        let public_url = http_url("GATEWAY_PUBLIC_URL", &required("GATEWAY_PUBLIC_URL")?)?;
        Ok(Self {
            check: TokenCheck::remote(issuer, audience, public_url)?,
            bind: bind_address()?,
        })
    }
}

/// Listens for Streamable HTTP MCP calls.
///
/// # Errors
///
/// Returns an error when the socket cannot bind or the server stops.
pub async fn serve(config: Config) -> std::io::Result<()> {
    let listener = TcpListener::bind(&config.bind).await?;
    axum::serve(listener, router(config.check)).await
}

#[derive(Clone, Serialize)]
struct ResourceMetadata {
    resource: String,
    authorization_servers: Vec<String>,
    bearer_methods_supported: [&'static str; 1],
}

#[derive(Clone)]
struct Caller {
    username: String,
}

#[derive(Deserialize)]
struct IdClaims {
    sub: String,
    preferred_username: String,
}

enum AuthFail {
    Unauthorized,
    Unavailable,
}

enum VerifyFail {
    Rejected,
    UnknownKid,
}

#[derive(Clone)]
struct CachedJwks {
    keys: Arc<JwkSet>,
    fetched: Instant,
}

enum Keys {
    #[cfg(test)]
    Fixed(Arc<JwkSet>),
    Remote {
        url: String,
        client: reqwest::Client,
        cached: Arc<RwLock<Option<CachedJwks>>>,
    },
}

#[derive(Clone)]
struct TokenCheck {
    inner: Arc<CheckInner>,
}

struct CheckInner {
    issuer: String,
    audience: String,
    public_url: String,
    missing: HeaderValue,
    invalid: HeaderValue,
    document: ResourceMetadata,
    keys: Keys,
}

impl TokenCheck {
    fn remote(issuer: String, audience: String, public_url: String) -> Result<Self, String> {
        let client = reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(5))
            .build()
            .map_err(|_| "could not build the JWKS client".to_owned())?;
        let url = format!("{issuer}{JWKS_PATH}");
        Self::new(
            issuer,
            audience,
            public_url,
            Keys::Remote {
                url,
                client,
                cached: Arc::new(RwLock::new(None)),
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
            inner: Arc::new(CheckInner {
                document: ResourceMetadata {
                    resource: format!("{public_url}{MCP_PATH}"),
                    authorization_servers: vec![issuer.clone()],
                    bearer_methods_supported: ["header"],
                },
                issuer,
                audience,
                public_url,
                missing,
                invalid,
                keys,
            }),
        })
    }

    async fn authenticate(&self, header: Option<&str>) -> Result<Caller, AuthFail> {
        let Some(token) = header.and_then(bearer_token) else {
            return Err(AuthFail::Unauthorized);
        };
        let keys = self.load(false).await?;
        match verify(&self.inner.issuer, &self.inner.audience, &keys, token) {
            Ok(caller) => Ok(caller),
            Err(VerifyFail::UnknownKid) => {
                let keys = self.load(true).await?;
                verify(&self.inner.issuer, &self.inner.audience, &keys, token)
                    .map_err(|_| AuthFail::Unauthorized)
            }
            Err(VerifyFail::Rejected) => Err(AuthFail::Unauthorized),
        }
    }

    async fn load(&self, refresh: bool) -> Result<Arc<JwkSet>, AuthFail> {
        match &self.inner.keys {
            #[cfg(test)]
            Keys::Fixed(keys) => Ok(Arc::clone(keys)),
            Keys::Remote {
                url,
                client,
                cached,
            } => {
                if let Some(hit) = cached.read().await.clone()
                    && (!refresh || hit.fetched.elapsed() < JWKS_REFRESH)
                {
                    return Ok(hit.keys);
                }
                let keys = fetch_jwks(client, url).await?;
                *cached.write().await = Some(CachedJwks {
                    keys: Arc::clone(&keys),
                    fetched: Instant::now(),
                });
                Ok(keys)
            }
        }
    }
}

async fn fetch_jwks(client: &reqwest::Client, url: &str) -> Result<Arc<JwkSet>, AuthFail> {
    let response = client
        .get(url)
        .send()
        .await
        .map_err(|_| AuthFail::Unavailable)?;
    if !response.status().is_success() {
        return Err(AuthFail::Unavailable);
    }
    let bytes = response.bytes().await.map_err(|_| AuthFail::Unavailable)?;
    if bytes.len() > JWKS_LIMIT {
        return Err(AuthFail::Unavailable);
    }
    serde_json::from_slice(&bytes)
        .map(Arc::new)
        .map_err(|_| AuthFail::Unavailable)
}

fn verify(issuer: &str, audience: &str, keys: &JwkSet, token: &str) -> Result<Caller, VerifyFail> {
    let header = decode_header(token).map_err(|_| VerifyFail::Rejected)?;
    if header.alg != Algorithm::RS256 {
        return Err(VerifyFail::Rejected);
    }
    let Some(kid) = header.kid else {
        return Err(VerifyFail::Rejected);
    };
    let Some(jwk) = keys.find(&kid) else {
        return Err(VerifyFail::UnknownKid);
    };
    if jwk
        .common
        .key_algorithm
        .is_some_and(|alg| alg != KeyAlgorithm::RS256)
    {
        return Err(VerifyFail::Rejected);
    }
    if !matches!(jwk.algorithm, AlgorithmParameters::RSA(_)) {
        return Err(VerifyFail::Rejected);
    }
    let key = DecodingKey::from_jwk(jwk).map_err(|_| VerifyFail::Rejected)?;
    let mut validation = Validation::new(Algorithm::RS256);
    validation.set_issuer(&[issuer]);
    validation.set_audience(&[audience]);
    validation.set_required_spec_claims(&["exp", "iss", "aud"]);
    let data = decode::<IdClaims>(token, &key, &validation).map_err(|_| VerifyFail::Rejected)?;
    if data.claims.sub.is_empty() || data.claims.preferred_username.is_empty() {
        return Err(VerifyFail::Rejected);
    }
    Ok(Caller {
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

fn router(check: TokenCheck) -> Router {
    let mcp = StreamableHttpService::new(
        || Ok(Gateway),
        Arc::new(LocalSessionManager::default()),
        StreamableHttpServerConfig::default()
            .with_legacy_session_mode(false)
            .with_json_response(true)
            .with_allowed_hosts(allowed_hosts(&check.inner.public_url)),
    );
    let document = check.inner.document.clone();
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
    match check.authenticate(header).await {
        Ok(caller) => {
            request.extensions_mut().insert(caller);
            next.run(request).await
        }
        Err(AuthFail::Unauthorized) => unauthorized(&check, presented),
        Err(AuthFail::Unavailable) => StatusCode::SERVICE_UNAVAILABLE.into_response(),
    }
}

fn unauthorized(check: &TokenCheck, presented: bool) -> Response {
    let mut response = Response::new(Body::empty());
    *response.status_mut() = StatusCode::UNAUTHORIZED;
    let challenge = if presented {
        &check.inner.invalid
    } else {
        &check.inner.missing
    };
    response
        .headers_mut()
        .insert(WWW_AUTHENTICATE, challenge.clone());
    response
}

#[derive(Clone)]
struct Gateway;

#[derive(Deserialize, JsonSchema)]
struct WhoamiArgs {
    #[serde(default)]
    user_id: Option<String>,
    #[serde(default)]
    tenant_id: Option<String>,
}

#[tool_router]
impl Gateway {
    #[allow(clippy::unused_self)]
    #[tool(description = "Return the signed-in username. user_id and tenant_id are ignored.")]
    fn whoami(
        &self,
        Parameters(args): Parameters<WhoamiArgs>,
        Extension(parts): Extension<Parts>,
    ) -> Result<String, ErrorData> {
        let WhoamiArgs { user_id, tenant_id } = args;
        let _ = (user_id, tenant_id);
        parts
            .extensions
            .get::<Caller>()
            .map(|caller| caller.username.clone())
            .ok_or_else(|| ErrorData::internal_error("missing caller", None))
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

fn http_url(name: &str, raw: &str) -> Result<String, String> {
    let url = raw.trim().trim_end_matches('/');
    if url
        .chars()
        .any(|c| c.is_ascii_control() || c == '"' || c == '\\')
    {
        return Err(format!("{name} must be an http or https URL"));
    }
    let Ok(parsed) = url.parse::<axum::http::Uri>() else {
        return Err(format!("{name} must be an http or https URL"));
    };
    let scheme = parsed.scheme_str().unwrap_or("");
    if (scheme != "http" && scheme != "https") || parsed.authority().is_none() {
        return Err(format!("{name} must be an http or https URL"));
    }
    Ok(url.to_owned())
}

#[cfg(test)]
mod tests {
    use std::sync::OnceLock;
    use std::time::Duration;

    use axum::body::{Body, to_bytes};
    use axum::http::header::{ACCEPT, AUTHORIZATION, CONTENT_TYPE, HOST, WWW_AUTHENTICATE};
    use axum::http::{Request, StatusCode};
    use base64::Engine;
    use base64::engine::general_purpose::URL_SAFE_NO_PAD;
    use jsonwebtoken::jwk::JwkSet;
    use jsonwebtoken::{Algorithm, EncodingKey, Header, encode};
    use rsa::RsaPrivateKey;
    use rsa::pkcs1::{EncodeRsaPrivateKey, LineEnding};
    use rsa::traits::PublicKeyParts;
    use tower::ServiceExt;

    use super::{METADATA_PATH, TokenCheck, router};

    const ISSUER: &str = "http://keycloak.example/realms/akwara";
    const AUDIENCE: &str = "ramonda-gateway";
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
            let jwks = serde_json::json!({
                "keys": [{
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "kid": "test",
                    "n": URL_SAFE_NO_PAD.encode(key.n().to_bytes_be()),
                    "e": URL_SAFE_NO_PAD.encode(key.e().to_bytes_be()),
                }]
            });
            let set = serde_json::from_value(jwks).expect("jwks");
            SigningKey { set, encoding }
        })
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

    fn tamper(token: &str) -> String {
        let mut token = token.to_owned();
        let last = token.pop().expect("token");
        token.push(if last == 'a' { 'b' } else { 'a' });
        token
    }

    fn app() -> axum::Router {
        let check = TokenCheck::fixed(ISSUER, AUDIENCE, PUBLIC_URL, signing_key().set.clone())
            .expect("check");
        router(check)
    }

    fn metadata_url() -> String {
        format!("{PUBLIC_URL}{METADATA_PATH}")
    }

    async fn call(token: Option<&str>) -> axum::response::Response {
        let mut builder = Request::builder()
            .method("POST")
            .uri("/mcp")
            .header(HOST, "127.0.0.1")
            .header(CONTENT_TYPE, "application/json")
            .header(ACCEPT, "application/json, text/event-stream");
        if let Some(token) = token {
            builder = builder.header(AUTHORIZATION, format!("Bearer {token}"));
        }
        let request = builder.body(Body::from(WHOAMI)).expect("request");
        tokio::time::timeout(Duration::from_secs(5), app().oneshot(request))
            .await
            .expect("gateway hung")
            .expect("response")
    }

    fn challenge(response: &axum::response::Response) -> &str {
        response
            .headers()
            .get(WWW_AUTHENTICATE)
            .expect("WWW-Authenticate")
            .to_str()
            .expect("header")
    }

    #[tokio::test]
    async fn missing_token_points_at_metadata() {
        let response = call(None).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(
            challenge(&response),
            format!("Bearer resource_metadata=\"{}\"", metadata_url())
        );
    }

    #[tokio::test]
    async fn metadata_names_keycloak() {
        let response = app()
            .oneshot(
                Request::builder()
                    .uri(METADATA_PATH)
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::OK);
        let bytes = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("body");
        let document: serde_json::Value = serde_json::from_slice(&bytes).expect("json");
        assert_eq!(document["authorization_servers"][0], ISSUER);
        assert_eq!(document["resource"], format!("{PUBLIC_URL}/mcp"));
    }

    #[tokio::test]
    async fn bad_signature_is_rejected() {
        let response = call(Some(&tamper(&token(ISSUER, AUDIENCE, "amina")))).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert!(challenge(&response).contains(&metadata_url()));
    }

    #[tokio::test]
    async fn bad_issuer_is_rejected() {
        let response = call(Some(&token(
            "http://evil.example/realms/akwara",
            AUDIENCE,
            "amina",
        )))
        .await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert!(challenge(&response).contains(&metadata_url()));
    }

    #[tokio::test]
    async fn bad_audience_is_rejected() {
        let response = call(Some(&token(ISSUER, "someone-else", "amina"))).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert!(challenge(&response).contains(&metadata_url()));
    }

    #[tokio::test]
    async fn whoami_uses_the_token_not_the_argument() {
        let response = call(Some(&token(ISSUER, AUDIENCE, "amina"))).await;
        assert_eq!(response.status(), StatusCode::OK);
        let bytes = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("body");
        let payload: serde_json::Value = serde_json::from_slice(&bytes).unwrap_or_else(|error| {
            panic!("{error}: {}", String::from_utf8_lossy(&bytes));
        });
        assert_eq!(payload["result"]["content"][0]["text"], "amina");
    }
}
