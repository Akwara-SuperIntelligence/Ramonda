# shortcut: tag tracks rust-toolchain.toml, bump both together
FROM rust:1.100.0-bookworm AS build
RUN apt-get update \
    && apt-get install -y --no-install-recommends cmake \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY gateway gateway
COPY relay relay
COPY outbox outbox
RUN cargo build --release --locked -p gateway

FROM debian:bookworm-slim
RUN useradd --system --uid 10001 --user-group --home-dir / --no-create-home --shell /usr/sbin/nologin gateway
COPY --from=build /src/target/release/gateway /usr/local/bin/gateway
USER gateway
EXPOSE 8080
ENTRYPOINT ["gateway"]
