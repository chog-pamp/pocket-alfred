# Firmware — Pocket Alfred

## Struktur
- `src/main.cpp` — setup/loop, touch-svep, state-maskin IDLE→LISTENING→THINKING→SPEAKING
- `src/gateway.h` — WS JSON-RPC (`session.create`, `wake.start`, `wake.feed`,
  `prompt.submit`), REST `transcribe` + `speak`
- `src/capture.h` — mic-buffring 16 kHz, amplitud-VAD (1.2 s tystnad → klar)
- `src/speaker.h` — MP3 → I2S via audio-tools (CodecMP3Helix)
- `src/screens.h` — glad emoji (blink/studs/mun) + 2-kolumners scrollbar grid
- `include/secrets.h.example` — kopiera till `include/secrets.h`, fyll i

## Flash (Windows, COM21)

```powershell
pip install platformio
cd pocket-alfred\firmware
copy include\secrets.h.example include\secrets.h
# redigera include\secrets.h: WiFi Herning-hem + hotspot + GATEWAY_TOKEN
pio run -t upload --upload-port COM21
pio device monitor --upload-port COM21
```

## Räckvidd
- Skärm 1: glad emoji; animerar vid wake/tal.
- Skärm 2: grid (Mail/Schema/Kanban/Brief) — trycker man en knapp skickas
  prompten som voice-live-turn, svaret tas upp via högtalaren.

## Nuvarande luckor (kända)
- `wake.feed`-anropet finns i gateway.h men feed-loopen i main.cpp är flaggad
  som TODO — se `docs/wire.md` TODO-listan.
- `M5.Touch.getDetail().state`-konstanter måste verifieras mot M5Unified-API:t.
- I2S-pinout (BCK=12/WS=0/DATA=2) ska verifieras mot Core2:s verkliga wiring.
- `message.delta`/`message.complete`-events är inte än verifierade i probe.
