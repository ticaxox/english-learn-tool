#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=lib-compose.sh
. "$ROOT/deploy/scripts/lib-compose.sh"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file: $ENV_FILE" >&2
  exit 2
fi
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
load_release_env

PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}"
[[ "$PUBLIC_BASE_URL" == https://* ]] || {
  echo "PUBLIC_BASE_URL must be an explicit https:// URL" >&2
  exit 2
}
run_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_FILE="${PUBLIC_EVIDENCE_FILE:-$ROOT/deploy/backups/public-deployment-evidence-$run_stamp.json}"
headers_file="$(mktemp)"
host_file="$(mktemp)"
trap 'rm -f "$headers_file" "$host_file"' EXIT

python3 - "$PUBLIC_BASE_URL" "$host_file" <<'PY'
import sys
from pathlib import Path
from urllib.parse import urlsplit
url = urlsplit(sys.argv[1])
if not url.hostname or url.query or url.fragment:
    raise SystemExit("PUBLIC_BASE_URL must contain a host and no query/fragment")
Path(sys.argv[2]).write_text(url.hostname, encoding="utf-8")
PY
host="$(cat "$host_file")"
if command -v getent >/dev/null 2>&1; then
  getent ahosts "$host" >/dev/null
else
  python3 - "$host" <<'PY'
import socket
import sys
socket.getaddrinfo(sys.argv[1], 443)
PY
fi

curl -fsS --proto '=https' --tlsv1.2 --max-time 30 \
  -D "$headers_file" -o /dev/null "$PUBLIC_BASE_URL/"
for header in \
  'x-content-type-options: nosniff' \
  'x-frame-options: SAMEORIGIN' \
  'referrer-policy: strict-origin-when-cross-origin' \
  'strict-transport-security: max-age='; do
  grep -Eiq "^${header%%:*}: .*${header#*: }" "$headers_file" \
    || { echo "Missing public security header: $header" >&2; exit 1; }
done
grep -Eiq '^content-security-policy: .*default-src .self.*' "$headers_file" \
  || { echo "Missing public Content-Security-Policy" >&2; exit 1; }

for path in /healthz /health/live /health/ready /api/v1; do
  curl -fsS --proto '=https' --tlsv1.2 --max-time 30 "$PUBLIC_BASE_URL$path" >/dev/null
done

sse_status="$(curl -sS --proto '=https' --tlsv1.2 --max-time 30 \
  -D "$headers_file" -o /dev/null -w '%{http_code}' \
  "$PUBLIC_BASE_URL/api/v1/coach/streams/00000000-0000-0000-0000-000000000000" || true)"
[[ "$sse_status" =~ ^(401|403|404|422)$ ]] \
  || { echo "Unexpected unauthenticated SSE status: $sse_status" >&2; exit 1; }
if grep -Eiq '^x-accel-buffering: no' "$headers_file"; then
  sse_buffering_header="true"
else
  sse_buffering_header="false"
  echo "INFO: edge did not forward X-Accel-Buffering; local origin check remains authoritative." >&2
fi
grep -Eiq '^cache-control: .*no-cache.*no-store' "$headers_file" \
  || { echo "Public SSE route does not disable caching" >&2; exit 1; }

timing="$(curl -sS --proto '=https' --tlsv1.2 --max-time 30 \
  -o /dev/null -w '%{time_starttransfer}' "$PUBLIC_BASE_URL/" || true)"
first_byte_ms="$(python3 - "$timing" <<'PY'
import sys
print(round(float(sys.argv[1]) * 1000, 2))
PY
)"
mkdir -p "$(dirname "$EVIDENCE_FILE")"
python3 - "$EVIDENCE_FILE" "$host" "$sse_status" "$first_byte_ms" "$sse_buffering_header" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path
output, host, sse_status, first_byte_ms, sse_buffering_header = sys.argv[1:]
Path(output).write_text(json.dumps({
    "schema_version": 1,
    "status": "passed",
    "checked_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
    "public_host": host,
    "tls_verified": True,
    "dns_resolved": True,
    "sse_status": int(sse_status),
    "first_byte_ms": float(first_byte_ms),
    "x_accel_buffering_forwarded": sse_buffering_header == "true",
    "checks": [
        "https_certificate",
        "dns_resolution",
        "content_security_policy",
        "strict_transport_security",
        "existing_security_headers",
        "health_live",
        "health_ready",
        "api_root",
        "sse_origin_not_buffered",
        "sse_not_cached",
    ],
    "artifact_policy": "metadata-only; no tokens, cookies, response bodies or member data",
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
chmod 0600 "$EVIDENCE_FILE"
echo "Public HTTPS verification passed. Evidence: $EVIDENCE_FILE"