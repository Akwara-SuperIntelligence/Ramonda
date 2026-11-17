#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/out"}
if [ -f "$out/ca.crt" ]; then
  exit 0
fi
mkdir -p "$out"
# shortcut: mounted dev keys are mode 644 because the image uids are not the host user; a non-local deploy mounts secrets as the service user
ext=$(mktemp)
trap 'rm -f "$ext"' EXIT

run() {
  if ! "$@" 2>"$out/openssl.err"; then
    cat "$out/openssl.err" >&2
    exit 1
  fi
}

run openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$out/ca.key"
run openssl req -new -x509 -key "$out/ca.key" -out "$out/ca.crt" -days 825 \
  -subj "/CN=Ramonda Dev CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"

sign() {
  name=$1
  subject=$2
  eku=$3
  san=$4
  run openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$out/$name.key"
  run openssl req -new -key "$out/$name.key" -out "$out/$name.csr" -subj "$subject"
  printf 'subjectAltName=%s\nextendedKeyUsage=%s\nkeyUsage=critical,digitalSignature\n' "$san" "$eku" > "$ext"
  run openssl x509 -req -in "$out/$name.csr" -CA "$out/ca.crt" -CAkey "$out/ca.key" \
    -CAserial "$out/ca.srl" -CAcreateserial \
    -out "$out/$name.crt" -days 825 -extfile "$ext"
  rm -f "$out/$name.csr"
}

sign keycloak "/CN=keycloak" serverAuth "DNS:keycloak,DNS:localhost,IP:127.0.0.1"
sign odoo-connector "/CN=odoo-connector" serverAuth "DNS:odoo-connector,DNS:localhost,IP:127.0.0.1"
sign gateway "/CN=gateway" clientAuth "DNS:gateway"
rm -f "$out/openssl.err"
chmod 644 "$out/keycloak.key" "$out/odoo-connector.key" "$out/gateway.key"
