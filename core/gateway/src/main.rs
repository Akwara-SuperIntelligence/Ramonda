use gateway::Config;

#[tokio::main]
async fn main() {
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
