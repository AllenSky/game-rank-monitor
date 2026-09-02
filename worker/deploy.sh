#!/usr/bin/env bash
# Publishes the Worker and loads its two secrets from ../config.json.
# Run `wrangler login` first -- that step needs a browser and cannot be scripted.
set -euo pipefail
cd "$(dirname "$0")"
WRANGLER="./node_modules/.bin/wrangler"
[ -x "$WRANGLER" ] || WRANGLER="npx --yes wrangler"

if ! $WRANGLER whoami >/dev/null 2>&1; then
  echo "Not authenticated. Run:  cd $(pwd) && $WRANGLER login"
  exit 1
fi

read_cfg() { python3 -c "import json,sys;print(json.load(open('../config.json'))['slack']['$1'])"; }

for pair in "SLACK_SIGNING_SECRET:signing_secret" "SLACK_WEBHOOK_URL:webhook_url"; do
  name="${pair%%:*}"; key="${pair##*:}"
  value="$(read_cfg "$key")"
  if [ -z "$value" ]; then
    echo "config.json has no slack.$key -- skipping $name"
    continue
  fi
  printf '%s' "$value" | $WRANGLER secret put "$name"
  echo "  set $name"
done

$WRANGLER deploy

cat <<'EOF'

Last step: copy the printed workers.dev URL into config.json as web.worker_url,
then rebuild and redeploy the dashboard so the Share button knows where to post:

  python3 -m topgames export --outdir site
  git add -A && git commit -m "Point the dashboard at the Worker" && git push

And set the same URL as the /top100 Request URL in your Slack app,
remembering the /slack/command path.
EOF
