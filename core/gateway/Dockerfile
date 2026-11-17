FROM rust:bookworm AS build
RUN apt-get update \
    && apt-get install -y --no-install-recommends cmake \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY rust-toolchain.toml ./
RUN rustup show
COPY core/Cargo.toml core/Cargo.lock ./
COPY core/gateway gateway
COPY core/relay relay
COPY core/outbox outbox
RUN cargo build --release --locked -p gateway

FROM debian:bookworm-slim
RUN useradd --system --uid 10001 --user-group --home-dir / --no-create-home --shell /usr/sbin/nologin gateway
COPY --from=build /src/target/release/gateway /usr/local/bin/gateway
USER gateway
EXPOSE 8080
ENTRYPOINT ["gateway"]
