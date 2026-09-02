#!/usr/bin/env bash
# Phase 1 deliverable: "Working upload + serve, no UI needed yet. Test with curl."
#
#   BASE=https://your-app.onrender.com TOKEN=<supabase access token> ./scripts/smoke.sh
#
# TOKEN is a user access token (the `access_token` from a Supabase sign-in), not
# the service_role key. The service_role key must never leave the server.
set -euo pipefail

BASE="${BASE:-http://localhost:8000}"
SLUG="${SLUG:-smoke-$(date +%s)}"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ -z "${TOKEN:-}" ]; then
  echo "Set TOKEN to a Supabase user access token." >&2
  exit 2
fi

pass() { printf '  \033[32mok\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; exit 1; }

expect() { # expect <what> <actual> <wanted>
  if [ "$2" = "$3" ]; then pass "$1 -> $2"; else fail "$1 -> got $2, wanted $3"; fi
}

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
location() { curl -s -o /dev/null -w '%{redirect_url}' "$@"; }

echo "base: $BASE"
echo "slug: $SLUG"

echo
echo "health"
expect "GET /health" "$(code "$BASE/health")" 200

echo
echo "auth"
expect "anonymous upload" "$(code -X POST "$BASE/api/deployments")" 401
expect "garbage token" \
  "$(code -X POST -H 'Authorization: Bearer nope' "$BASE/api/deployments")" 401

echo
echo "build the zip"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# `zip` is not on every machine (Git Bash on Windows, slim containers).
if command -v zip >/dev/null 2>&1; then
  ( cd "$HERE/sample-site" && zip -q -r "$TMP/site.zip" . )
else
  python - "$HERE/sample-site" "$TMP/site.zip" <<'PYZIP'
import os, sys, zipfile
root, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for base, _, files in os.walk(root):
        for name in files:
            full = os.path.join(base, name)
            zf.write(full, os.path.relpath(full, root).replace(os.sep, "/"))
PYZIP
fi
ls -l "$TMP/site.zip" | awk '{print "  " $5 " bytes"}'

echo
echo "deploy"
RESPONSE="$(curl -s -X POST "$BASE/api/deployments" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Commit-Sha: 0000000000000000000000000000000000000001" \
  -F "slug=$SLUG" \
  -F "file=@$TMP/site.zip")"
echo "$RESPONSE" | head -c 400; echo
echo "$RESPONSE" | grep -q '"status": *"ready"' && pass "deployment ready" || fail "deployment not ready"

echo
echo "serve"
expect "GET /s/$SLUG/           " "$(code "$BASE/s/$SLUG/")" 307
expect "GET /s/$SLUG/about      " "$(code "$BASE/s/$SLUG/about")" 307
expect "GET /s/$SLUG/docs       " "$(code "$BASE/s/$SLUG/docs")" 307
expect "GET /s/$SLUG/assets/app.css" "$(code "$BASE/s/$SLUG/assets/app.css")" 307
expect "GET /s/$SLUG (no slash) " "$(code "$BASE/s/$SLUG")" 308
expect "GET /s/nope-not-a-site/ " "$(code "$BASE/s/nope-not-a-site/")" 404

echo
echo "redirect targets Supabase, not us"
TARGET="$(location "$BASE/s/$SLUG/")"
echo "  $TARGET"
case "$TARGET" in
  *"/storage/v1/object/public/"*) pass "redirects to Supabase Storage" ;;
  *) fail "redirect does not point at Supabase Storage" ;;
esac
expect "follow the redirect" "$(code -L "$BASE/s/$SLUG/")" 200

echo
echo "404.html fallback"
expect "GET /s/$SLUG/nope       " "$(code "$BASE/s/$SLUG/nope")" 307
case "$(location "$BASE/s/$SLUG/nope")" in
  *404.html) pass "falls back to 404.html" ;;
  *) fail "did not fall back to 404.html" ;;
esac

echo
echo "rejections"
printf 'this is not a zip' > "$TMP/bad.zip"
expect "not a zip           " \
  "$(code -X POST "$BASE/api/deployments" -H "Authorization: Bearer $TOKEN" \
     -F "slug=$SLUG" -F "file=@$TMP/bad.zip")" 422

( cd "$TMP" && mkdir -p nested && echo "nothing to serve" > nested/readme.txt \
  && zip -q -r noindex.zip nested )
expect "no index.html       " \
  "$(code -X POST "$BASE/api/deployments" -H "Authorization: Bearer $TOKEN" \
     -F "slug=$SLUG" -F "file=@$TMP/noindex.zip")" 422

echo
echo "history"
expect "GET /api/projects/$SLUG" \
  "$(code -H "Authorization: Bearer $TOKEN" "$BASE/api/projects/$SLUG")" 200

echo
echo "cleanup"
expect "DELETE /api/projects/$SLUG" \
  "$(code -X DELETE -H "Authorization: Bearer $TOKEN" "$BASE/api/projects/$SLUG")" 204
expect "site is gone         " "$(code "$BASE/s/$SLUG/")" 404

echo
printf '\033[32mall checks passed\033[0m\n'
