use std::sync::Arc;
use std::time::Duration;

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
use rmcp::transport::streamable_http_server::session::local::LocalSessionManager;
use rmcp::transport::streamable_http_server::{StreamableHttpServerConfig, StreamableHttpService};
use rmcp::{ErrorData, ServerHandler, tool, tool_handler, tool_router};
use serde::{Deserialize, Serialize};
use tokio::net::TcpListener;

const MCP_PATH: &str = "/mcp";
const METADATA_PATH: &str = "/.well-known/oauth-protected-resource/mcp";

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

#[derive(Clone)]
enum Keys {
    #[cfg(test)]
    Fixed(Arc<JwkSet>),
    Remote {
        url: String,
        client: reqwest::Client,
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
    fn remote(issuer: String, audience: String, public_url: String) -> Result<Self, String> {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .map_err(|_| "could not build the JWKS client".to_owned())?;
        let url = format!("{issuer}/protocol/openid-connect/certs");
        Self::new(issuer, audience, public_url, Keys::Remote { url, client })
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
        let keys = self.jwks().await?;
        verify(&self.issuer, &self.audience, &keys, token)
    }

    async fn jwks(&self) -> Option<Arc<JwkSet>> {
        match &self.keys {
            #[cfg(test)]
            Keys::Fixed(keys) => Some(Arc::clone(keys)),
            Keys::Remote { url, client } => {
                let response = client.get(url).send().await.ok()?;
                if !response.status().is_success() {
                    return None;
                }
                let bytes = response.bytes().await.ok()?;
                serde_json::from_slice(&bytes).ok().map(Arc::new)
            }
        }
    }
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
    validation.set_issuer(&[issuer]);
    validation.set_audience(&[audience]);
    validation.set_required_spec_claims(&["exp", "iss", "aud"]);
    let data = decode::<IdClaims>(token, &key, &validation).ok()?;
    if data.claims.sub.is_empty() || data.claims.preferred_username.is_empty() {
        return None;
    }
    Some(Caller {
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
struct Gateway;

#[tool_router]
impl Gateway {
    #[allow(clippy::unused_self)]
    #[tool(
        description = "Return the signed-in username. A user or tenant id in the arguments is ignored."
    )]
    fn whoami(&self, Extension(parts): Extension<Parts>) -> Result<String, ErrorData> {
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
    use std::sync::OnceLock;
    use std::time::Duration;

    use axum::body::{Body, to_bytes};
    use axum::http::header::{ACCEPT, AUTHORIZATION, CONTENT_TYPE, HOST, WWW_AUTHENTICATE};
    use axum::http::{Request, StatusCode};
    use jsonwebtoken::jwk::JwkSet;
    use jsonwebtoken::{Algorithm, EncodingKey, Header, encode};
    use rsa::RsaPrivateKey;
    use rsa::pkcs1::{EncodeRsaPrivateKey, LineEnding};
    use tower::ServiceExt;

    use super::{MCP_PATH, METADATA_PATH, TokenCheck, router};

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
            let mut jwk = jsonwebtoken::jwk::Jwk::from_encoding_key(&encoding, Algorithm::RS256)
                .expect("jwk");
            jwk.common.key_id = Some("test".to_owned());
            let set = JwkSet { keys: vec![jwk] };
            let set =
                serde_json::from_str(&serde_json::to_string(&set).expect("json")).expect("jwks");
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

    fn app() -> axum::Router {
        router(
            TokenCheck::fixed(ISSUER, AUDIENCE, PUBLIC_URL, signing_key().set.clone())
                .expect("check"),
        )
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
        tokio::time::timeout(
            Duration::from_secs(5),
            app().oneshot(builder.body(Body::from(WHOAMI)).expect("request")),
        )
        .await
        .expect("gateway hung")
        .expect("response")
    }

    #[tokio::test]
    async fn missing_token_points_at_keycloak() {
        let response = call(None).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let challenge = response.headers().get(WWW_AUTHENTICATE).expect("challenge");
        assert_eq!(
            challenge.to_str().expect("header"),
            format!("Bearer resource_metadata=\"{PUBLIC_URL}{METADATA_PATH}\"")
        );
        let response = app()
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
        let mut tampered = good.clone();
        let last = tampered.pop().expect("token");
        tampered.push(if last == 'a' { 'b' } else { 'a' });
        let cases = [
            tampered,
            token("http://evil.example/realms/akwara", AUDIENCE, "amina"),
            token(ISSUER, "someone-else", "amina"),
        ];
        for token in cases {
            assert_eq!(call(Some(&token)).await.status(), StatusCode::UNAUTHORIZED);
        }
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
