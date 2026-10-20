#!/bin/sh
# Copies every key in ~/sg-content/.env into this repo's encrypted GitHub Actions secrets, so the cloud workflows can run.
# Values are piped straight to `gh secret set`; nothing is printed or logged. Run once, and again whenever a token changes:
#     sh ~/sg-content/scripts/github_secrets.sh
set -e
REPO="SGULIA20/sg-content"
ENV="$HOME/sg-content/.env"
n=0
while IFS='=' read -r key value; do
  case "$key" in ''|\#*) continue;; esac
  printf '%s' "$value" | gh secret set "$key" -R "$REPO" >/dev/null
  n=$((n+1))
done < "$ENV"
echo "$n secrets set on $REPO:"
gh secret list -R "$REPO" | awk '{print "  " $1}'
