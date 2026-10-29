#!/usr/bin/env bash
# Fires 400 unauthenticated GETs at $APP_URL/api/todos and prints a status-code histogram.
# WAF limit: 300 requests / 5 min / IP on /api/. WAF evaluates the rate with a delay of
# ~30-60 s, so expect 401s first, then 403/429 once the block kicks in.
# WARNING: afterwards your IP stays rate-limited on /api/ for up to ~5 minutes.
set -euo pipefail
APP_URL="${APP_URL:-$(terraform -chdir="$(dirname "$0")/../infra" output -raw app_url)}"
APP_URL="${APP_URL%/}"
N="${N:-400}"
echo "Sending $N GETs to $APP_URL/api/todos"
seq "$N" | xargs -P 8 -I{} curl -s -m 10 -o /dev/null -w '%{http_code}\n' "$APP_URL/api/todos" \
  | sort | uniq -c | awk '{printf "HTTP %s: %s\n", $2, $1}'
