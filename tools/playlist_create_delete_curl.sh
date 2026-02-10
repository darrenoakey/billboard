#!/usr/bin/env bash
set -euo pipefail

BASE_URL="https://api.music.apple.com/v1"
PLAYLIST_NAME="${PLAYLIST_NAME:-blah}"

: "${APPLE_MUSIC_DEV_TOKEN:?Set APPLE_MUSIC_DEV_TOKEN in your environment}"
: "${APPLE_MUSIC_USER_TOKEN:?Set APPLE_MUSIC_USER_TOKEN in your environment}"

create_body="$(mktemp)"
delete_body="$(mktemp)"

trap 'rm -f "$create_body" "$delete_body"' EXIT

create_status="$(curl -sS --compressed -o "$create_body" -w "%{http_code}" \
  -X POST "${BASE_URL}/me/library/playlists" \
  -H "Authorization: Bearer ${APPLE_MUSIC_DEV_TOKEN}" \
  -H "Music-User-Token: ${APPLE_MUSIC_USER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"attributes\":{\"name\":\"${PLAYLIST_NAME}\"}}")"

echo "Create status: ${create_status}"
cat "$create_body"
echo

playlist_id="$(python3 - "$create_body" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
playlist_id = data["data"][0]["id"]
print(playlist_id)
PY
)"

echo "Playlist ID: ${playlist_id}"

delete_status="$(curl -sS --compressed -o "$delete_body" -w "%{http_code}" \
  -X DELETE "${BASE_URL}/me/library/playlists/${playlist_id}" \
  -H "Authorization: Bearer ${APPLE_MUSIC_DEV_TOKEN}" \
  -H "Music-User-Token: ${APPLE_MUSIC_USER_TOKEN}" \
  -H "Content-Type: application/json")"

echo "Delete status: ${delete_status}"
cat "$delete_body"
echo
