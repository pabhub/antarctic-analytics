#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${AEMET_API_KEY:-}" ]]; then
  echo "ERROR: set AEMET_API_KEY"
  exit 1
fi

BASE="https://opendata.aemet.es/opendata/api"
ENDPOINT="$BASE/antartida/datos/fechaini/2024-01-01T00:00:00UTC/fechafin/2024-01-01T01:00:00UTC/estacion/89064"

echo "== Single request headers =="
curl -sS -D /tmp/aemet_headers.txt -o /tmp/aemet_body.json "$ENDPOINT?api_key=$AEMET_API_KEY" || true
sed -n '1,40p' /tmp/aemet_headers.txt || true

echo
echo "== Burst test (20 requests) =="
for i in $(seq 1 20); do
  code=$(curl -sS -o /dev/null -w '%{http_code}' "$ENDPOINT?api_key=$AEMET_API_KEY" || echo "000")
  echo "$code"
done | sort | uniq -c

echo
echo "== Rate-limit related headers (if any) =="
rg -i 'rate|retry-after|limit|quota' /tmp/aemet_headers.txt || true

