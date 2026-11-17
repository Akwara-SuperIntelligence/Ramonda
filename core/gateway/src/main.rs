use gateway::Config;

#[tokio::main]
async fn main() {
    if std::env::var("RAMONDA_STAMP").ok().as_deref() == Some("local") {
        eprintln!(
            "warning: RAMONDA_STAMP=local is the laptop stamp. Remove it from deploy/compose.yaml before any server deploy."
        );
    }
    let config = match Config::from_env() {
        Ok(config) => config,
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    };
    if let Err(error) = gateway::serve(config).await {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
