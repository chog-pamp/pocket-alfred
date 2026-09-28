# Pocket Alfred — wire-dokumentation (verifierad 2026-09-23/24)

Allt nedan är **verifierat** mot en körande `hermes serve` (alfred-profil, :9215) via
`tools/probe_rpc.py` / `/tmp/speak_probe.py`, eller läst i källkoden
(`~/.hermes/hermes-agent/`).

## WS `/api/ws` (JSON-RPC)

- Nylinje-avgränsad JSON-RPC 2.0, dubbelriktad. Auth loopback: `?token=` i URL
  (constant-time mot `_SESSION_TOKEN` = `HERMES_DASHBOARD_SESSION_TOKEN` env).
  Via Caddy (TLS) samma query-param.
- Första eventet vid anslutning: `event {type:"gateway.ready", payload:{skin:...}}`
  (a events är wrappade i en `event`-kuvert: `{"method":"event","params":{"type":...,"payload":...}}`).
- `client.capabilities {server_requests:false}` → svarar med server_requests-lista.

### Sessioner

- `session.list {limit:1}` → `{result:{sessions:[{id, title, preview, ...}]}}`
  (`id` = fullt lagrat id, t.ex. `20260923_221541_db9cd0`).
- `session.create {title:"pocket-alfred"}` → `{result:{session_id:"4234957e" (kort id),
  stored_session_id:"20260923_233330_dad19e"}}`. Använd `session_id` i alla
  efterföljande anrop.

### Wake word (client capture)

- `wake.start {surface:"gui", client_capture:true, session_id}` →
  `{started:true, phrase:"hey hermes", provider:"openwakeword", owner_surface:"gui",
  capture:"client", sample_rate:16000, frame_length:1280}`.
- PCM-feed: `wake.feed {pcm_b64: base64(int16 mono LE 16kHz), sample_rate:16000}`.
  Frame = 1280 samples (80 ms), max 64 kB per RPC. Coalesca 2–3 frames per feed.
- Event vid träff: `event {type:"wake.detected", payload:{phrase, profile, start_new_session}}`.
- Efter detected pausar detectorn själv; `wake.resume` återarmar.
- `wake.status {surface:"gui"}` → `listening` m.m.

### Prompt-turn

- `prompt.submit {session_id, text, surface:"voice-live"}` → `{status:"streaming"}`.
- Deltas: `event {type:"message.delta", payload:{text:"..."}}` — ackumulera.
- Slut: `event {type:"message.complete", payload:{text: <hela svaret>}}`
  (NOT YET VERIFIERAD i probe-loggen — verifiera deltas runt explicit; se TODO).
- `surface:"voice-live"` sätter en per-turn-note → modellen svarar i speakable prose.

## TTS — `/api/audio/speak-stream` (WS)

Verifierat: `edge` (tts.provider) har **ingen chunked API** → servern skickar
`{"type":"fallback"}` direkt. **Firmware ska använda Väg B:**

- `POST /api/audio/speak {text}` (header `X-Hermes-Session-Token`) →
  `{ok:true, data_url:"data:audio/mpeg;base64,...", mime_type:"audio/mpeg"}`
  → dekodera base64 → MP3DecoderHelix → I2S.

(Läge: om TTS-provider senare byts till openai/gemini/elevenlabs/xai leverar
speak-stream: client→`{"text":"..."}` + `{"done":true}`; server→
`{"type":"start",sample_rate,channels:1}` + binära PCM-frames + `{"type":"end"}`.
Kod för båda vägarna finns i `firmware/src/speaker.h`.)

## REST STT — `/api/audio/transcribe`

`POST {data_url:"data:audio/wav;base64,...", mime_type:"audio/wav"}` →
`{ok:true, transcript:"..."}` (header `X-Hermes-Session-Token`). 16 kHz int16 mono WAV.

## TODO / öppet

- Verifiera `message.delta`/`message.complete`-events explicit i probe-loop (senaste
  körningen hann inte skriva ut dem innan timeout).
- DNS `pocket.kranium.me` saknas i Cloudflare — leo sätter A/CNAME-proxied till
  kranium.me-servern. Caddy-blocket är reloadat.
- Google-token (`google_token.json`) revoked sedan 18 sep → Mail-knappen blockerad
  tills leo re-authar (`google-venv` + setup.py i google-workspace-skillet).
