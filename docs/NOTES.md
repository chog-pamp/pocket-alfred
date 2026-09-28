# Pocket Alfred — server-stack notes

*Uppdaterad 2026-09-23 (server-stack-bootstrap).*

## Nyckelfakta

- **Repo:** `/home/leo/homelab/pocket-alfred/` (git, commit per task)
- **pm2-app:** `pocket-alfred-serve` (ecosystem.config.js i `server/`)
- **Port:** `127.0.0.1:9215`, exponeras via Caddy på `https://pocket.kranium.me`
- **Session-token:** `/home/leo/homelab/pocket-alfred/server/session-token.txt` (48 hex, chmod 600, gitignored). Pinas i serve-processen via env `HERMES_DASHBOARD_SESSION_TOKEN`.

## Profilkonfig (alfred)

- Config satt via `hermes -p alfred config set` (ALDRIG hand-editerad config.yaml):
  - `wake_word.enabled: true`
  - `wake_word.capture: client`
  - `tts.provider: edge`
  - `tts.edge.voice: sv-SE-MattiasNeural`
  - `stt.provider: openai` *(satt med --force; hermes varnade för att nyckeln inte är en "recognized config key" — validerat att den faktiskt hamnar i config.yaml och är läsbar via config get, men detta är en mjuk varning från CLI:n, inte ett stopp)*

## Secrets som kopierades

- `STT_OPENAI_BASE_URL` + `VOICE_TOOLS_OPENAI_KEY` från `/home/leo/.hermes/.env` → `/home/leo/.hermes/profiles/alfred/.env` (chmod 600, idempotent via `tools/copy_stt_secrets.sh`).
- **Inga EMAIL_-secrets kopierades.** Mail går inte via EMAIL_-env (de är utkommenterade i roten). Mail-knappen på enheten använder istället `google_api.py`-kedjan (`~/.hermes/google-venv/bin/python3 ~/.hermes/skills/productivity/google-workspace/scripts/google_api.py gmail search ...`).

## Google-token-blockerare (Mail-knappen)

- Token i `~/.hermes/google_token.json` är **revoked** sedan 2026-09-18 (`invalid_grant`). Leo behöver re-auth:a.
- Tills det är fixat kan Mail-knappen inte läsa inkorgen.
- Referenskod för samma GAPI-kedja: `/home/leo/homelab/daily-brief/brief.py`.

## Wire-detajer (från probes)

*(fylls i av probe-körningarna nedan)*

## Känd bugg: `providers.freerouter.api_base` ignoreras → modellen startar inte

**Symptom:** `prompt.submit` på alfred-serve svarar `status:"streaming"` men agenten
dör med event `type:"error"`: *"Hermes could not start the assistant for this session.
Details: Unknown provider 'freerouter'."*

**Root cause:** Alfreds `config.yaml` har en `providers:`-sektion med nyckeln
`freerouter` vars enda URL-fält heter `api_base`:

```yaml
providers:
  freerouter:
    api_base: https://router.kranium.me/v1
    api_key: freellmapi-...
```

`hermes_cli/providers.py::_pick_provider_base_url` (rad 131) accepterar bara
`base_url` / `url` / `api` som URL-fält — **`api_base` är INTE en känd alias** i
`providers:`-sektionen (bara camelCase-alias finns: `baseUrl` → `base_url`).
Det gör att `_normalize_custom_provider_entry()` returnerar `None` (ingen URL
hittad), dvs. provider-namnet `freerouter` matchar en alias-lista i
`_match_new_style_provider()` men entry:t droppas på `if not base_url: continue`
(`runtime_provider_custom.py:_match_new_style_provider`). Följden är att:
1. `_get_named_custom_provider('freerouter')` → `None`
2. `_resolves_to_custom('freerouter')` → `False` (freerouter är ingen alias för `custom`)
3. `resolve_provider('freerouter')` → `AuthError: Unknown provider 'freerouter'`
   (freerouter finns inte i PROVIDER_REGISTRY, models.dev eller plugin-profiler)
4. → `"Hermes could not start the assistant for this session. Details: Unknown provider 'freerouter'."`
   per turn i tui_gateway (i stället för något faktiskt modell-svar).

Samma config-mönster funkar i andra profiler (`olle`, root) där värdet ligger
under `custom_providers:` (legacy-lista) eller där `model.provider` är satt till
`custom` med `model.base_url` (då tar `_local_endpoint_bypass`/`_resolve_direct_alias_runtime`-rungen
över, oberoende av namnet). Det är alltså bara kombon
`model.provider: freerouter` + `providers.<name>.api_base` som är trasig.

**Fix (välj en):**
- Byt namn på nyckeln i alfreds config.yaml från `api_base:` till `base_url:` (se
  `tools/fix_freerouter_provider.sh` — gör detta idempotent), eller
- kör `hermes -p alfred config set providers.freerouter.base_url https://router.kranium.me/v1`
  (via config-set, aldrig hand-editera config.yaml).

**Not:** efter fixen behöver `pm2 restart pocket-alfred-serve` köras så att
serve-processen laddar om config.

