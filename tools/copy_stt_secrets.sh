#!/bin/bash
# Task 1: copy STT secrets from the Hermes root .env into the alfred profile .env (idempotent)
set -euo pipefail
DST=/home/leo/.hermes/profiles/alfred/.env
cp "$DST" /tmp/alfred.env
for key in STT_OPENAI_BASE_URL VOICE_TOOLS_OPENAI_KEY; do
  if ! grep -qE "^${key}=" "$DST"; then
    grep -E "^${key}=" /home/leo/.hermes/.env >> /tmp/alfred.env
  fi
done
cp /tmp/alfred.env "$DST"
chmod 600 "$DST"
rm -f /tmp/alfred.env
echo "count: $(grep -cE '^(STT_OPENAI_BASE_URL|VOICE_TOOLS_OPENAI_KEY)=' "$DST")"
ls -la "$DST"
