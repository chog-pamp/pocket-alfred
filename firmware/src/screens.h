#pragma once
#include <M5Unified.h>

// Pocket Alfred UI v2 — "butler clipart" logga + state-färger, modernt mörkt grid.
// Butler: hatt (med state-färgat band), ansikte, fluga — ritad med shapes (ingen bitmap-fil).
// State-färger: IDLE grå · LISTENING mint-puls · THINKING blå spin · SPEAKING gul puls.
// All rendering → M5Canvas sprite, EN pushSprite per frame, dirty-check (INGEN flicker).

enum FaceState { FACE_IDLE, FACE_LISTENING, FACE_THINKING, FACE_SPEAKING };
extern FaceState faceState;
extern int activeScreen;           // 0 = butler, 1 = grid
extern int screenGen;              // ökas vid skärmbyte → tvingar repaint

// state-accentfärg (RGB565 via color565 av RGB)
static inline uint16_t stateColor(FaceState s, float pulse = 1.0f) {
  uint8_t r = 158, g = 158, b = 158;                     // IDLE: grå
  if (s == FACE_LISTENING)  { r = 100; g = 255; b = 218; }  // mint
  if (s == FACE_THINKING)   { r = 79;  g = 195; b = 247; }  // blå
  if (s == FACE_SPEAKING)   { r = 255; g = 213; b = 79;  }  // gul
  return M5.Display.color565((uint8_t)(r * pulse), (uint8_t)(g * pulse), (uint8_t)(b * pulse));
}

struct Face {
  FaceState drawnState = FACE_IDLE;
  int drawnGen = -1;
  uint32_t lastDrawMs = 0;

  void paint(M5Canvas& c) {
    const int cx = 160, cy = 118;
    uint32_t t = millis();
    c.fillScreen(0x0A0A0C);
    uint16_t acc = stateColor(faceState);

    // pulsfaktor: listening/speaking pulserar mjukt, thinking konstant (spin-ring fixar livet)
    float pulse = 1.0f;
    if (faceState == FACE_LISTENING || faceState == FACE_SPEAKING)
      pulse = 0.75f + 0.25f * sinf(t / 260.0f);

    // thinking: roterande kometsvans-ring runt butlern
    if (faceState == FACE_THINKING) {
      float a = (t / 7) % 360 * 0.0174533f;
      for (int i = 0; i < 18; i++) {
        float ang = a - i * 0.10f;
        float rr = 92 + sinf(t / 400.0f) * 3;
        uint8_t shade = 255 - i * 13;
        c.fillCircle(cx + (int)(cosf(ang) * rr), cy + (int)(sinf(ang) * rr),
                     5 - i / 7, M5.Display.color565(shade * 0.31f, shade * 0.76f, shade));
      }
    } else {
      // puls-ring runt loggan (tunn, växer/dimmar med pulsen)
      int rr = 86 + (int)(pulse * 6);
      c.drawCircle(cx, cy, rr, stateColor(faceState, pulse * 0.45f));
      c.drawCircle(cx, cy, rr - 3, stateColor(faceState, pulse * 0.25f));
    }

    // ── hatt ──
    c.fillRect(cx - 26, cy - 82, 52, 40, 0x111114);        // krona
    c.fillRect(cx - 42, cy - 44, 84, 8, 0x111114);         // brätten
    c.fillRect(cx - 26, cy - 52, 52, 8, acc);              // hatband (state-färg)

    // ── ansikte ──
    c.fillCircle(cx, cy - 8, 34, 0xE8E8E8);                // huvud
    c.fillCircle(cx - 12, cy - 14, 3, 0x1A1A1A);           // öga v
    c.fillCircle(cx + 12, cy - 14, 3, 0x1A1A1A);           // öga h
    // mustasch
    c.fillRect(cx - 14, cy + 2, 28, 5, 0x2A2A2E);
    c.fillCircle(cx - 15, cy + 4, 4, 0x2A2A2E);
    c.fillCircle(cx + 15, cy + 4, 4, 0x2A2A2E);
    // mun: speaking → animerad; annars lugn linje
    if (faceState == FACE_SPEAKING) {
      int mw = 8 + ((t / 110) % 3) * 6;
      c.fillRect(cx - mw, cy + 12, mw * 2, 5, 0x1A1A1A);
    } else {
      c.fillRect(cx - 9, cy + 12, 18, 3, 0x1A1A1A);
    }

    // ── kravat + fluga ──
    c.fillRect(cx - 18, cy + 26, 36, 10, 0xFFFFFF);        // kravat
    c.fillTriangle(cx - 20, cy + 31, cx - 4, cy + 24, cx - 4, cy + 38, acc);  // fluga v
    c.fillTriangle(cx + 20, cy + 31, cx + 4, cy + 24, cx + 4, cy + 38, acc);  // fluga h
    c.fillCircle(cx, cy + 31, 4, acc);                     // knut
    if (faceState == FACE_SPEAKING) {                      // fluga "pratar"-puls
      uint16_t dim = stateColor(faceState, pulse);
      c.fillCircle(cx, cy + 31, 6 + (int)(pulse * 4), dim);
    }

    // status-text
    c.setTextColor(0x8A8A92, 0x0A0A0C);
    c.setTextSize(2);
    c.setTextDatum(4);    // middle_center (M5GFX: MC = 4)
    const char* label = "Alfred";
    if (faceState == FACE_LISTENING) label = "Lyssnar...";
    if (faceState == FACE_THINKING)  label = "Tankar...";
    if (faceState == FACE_SPEAKING)  label = "Svarar...";
    c.drawString(label, cx, 224);
    c.setTextDatum(0);    // top_left (M5GFX textdatum enum)
  }

  // dirty-check: repaint endast vid state-byte, animation, eller skärmbyte
  void draw(M5Canvas& c) {
    uint32_t t = millis();
    bool animating = faceState != FACE_IDLE;
    if (!animating && faceState == drawnState && drawnGen == screenGen) return;
    if (animating && t - lastDrawMs < 50) return;
    lastDrawMs = t;
    paint(c);
    drawnState = faceState;
    drawnGen = screenGen;
    c.pushSprite(0, 0);
  }
};

// ── Actions (2x2 synliga, scrollbar för framtiden) ───────────────────────────
struct Action { const char* label; const char* prompt; uint32_t color; };
static const Action ACTIONS[] = {
  {"Brief",   "Ge mig en kort daglig briefing.",                                        0xBA68C8u},
  {"Mail",    "Kolla min mail och rapportera kort om n\u00e5got viktigt dykt upp.",     0x4FC3F7u},
  {"Schema",  "Vad har jag p\u00e5 schemat idag och resten av veckan? Kort please.",    0x81C784u},
  {"Nyheter", "Sammanfatta dagens nyheter kort.",                                       0xFFB74Du},
};
static const int N_ACTIONS = sizeof(ACTIONS) / sizeof(ACTIONS[0]);

struct Grid {
  int scrollRows = 0;
  int lastScroll = -1;
  int drawnGen = -1;

  void paint(M5Canvas& c) {
    c.fillScreen(0x0A0A0C);
    // header: "Alfred" + litet status-dot i state-färg
    c.setTextColor(0xE8E8E8, 0x0A0A0C);
    c.setTextSize(2);
    c.setCursor(12, 8);
    c.print("Alfred");
    c.fillCircle(296, 14, 5, stateColor(faceState));
    c.setTextColor(0x55555C, 0x0A0A0C);
    c.setTextSize(1);
    c.setCursor(78, 14);
    c.print("actions");

    const int W = 145, H = 88, GX = 10, GY = 12, TOP = 36;
    for (int i = 0; i < N_ACTIONS; i++) {
      int r = i / 2, c2 = i % 2;
      int y = TOP + (r - scrollRows) * (H + GY);
      if (y + H < TOP || y > 240) continue;
      int x = c2 * (W + GX) + (320 - 2 * W - GX) / 2;
      c.fillRoundRect(x, y, W, H, 10, 0x16161C);          // card
      c.fillRoundRect(x, y, 5, H, 2, ACTIONS[i].color);   // accent-kant vänster
      c.setTextColor(0xF0F0F0, 0x16161C);
      c.setTextSize(2);
      c.setCursor(x + 16, y + 34);
      c.print(ACTIONS[i].label);
      c.setTextColor(0x55555C, 0x16161C);
      c.setTextSize(1);
      c.setCursor(x + 16, y + 62);
      c.print("tap");
    }
  }

  void draw(M5Canvas& c) {
    if (lastScroll == scrollRows && drawnGen == screenGen) return;
    paint(c);
    lastScroll = scrollRows;
    drawnGen = screenGen;
    c.pushSprite(0, 0);
  }

  int touch(int tx, int ty, int dy) {
    if (dy > 30) { scrollRows = max(0, scrollRows - 1); return -1; }
    if (dy < -30) { int rows = (N_ACTIONS + 1) / 2; int maxRows = rows - 2;
                    if (maxRows > 0 && scrollRows < maxRows) scrollRows++;
                    return -1; }
    const int W = 145, H = 88, GX = 10, TOP = 36;
    for (int i = 0; i < N_ACTIONS; i++) {
      int r = i / 2, c2 = i % 2;
      int y = TOP + (r - scrollRows) * (H + 12);
      int x = c2 * (W + GX) + (320 - 2 * W - GX) / 2;
      if (tx >= x && tx <= x + W && ty >= y && ty <= y + H) return i;
    }
    return -1;
  }
};
