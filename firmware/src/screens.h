#pragma once
#include <M5Unified.h>

// Skärmar: glad emoji (standard) + scrollbart 2-kolumners knappgrid.
// All rendering till en M5Canvas (off-screen sprite) som flippas i ETT steg —
// ingen fillScreen-blinkning. Face.draw() ritar bara om vid FÖRÄNDRING.

enum FaceState { FACE_IDLE, FACE_LISTENING, FACE_THINKING, FACE_SPEAKING };
extern FaceState faceState;
extern int activeScreen;           // 0 = face, 1 = grid
extern int screenGen;              // ökas när skärmbytje sker → tvingar repaint

struct Face {
  float bounce = 0;
  FaceState drawnState = FACE_IDLE;   // vad som senast ritades
  int drawnGen = -1;                  // screenGen när senast ritad
  uint32_t lastDrawMs = 0;

  // rita om ansiktet på canvasen (utan flipp)
  void paint(M5Canvas& c) {
    int cx = 160, cy = 120 + (int)(bounce * -14);
    uint32_t t = millis();
    bool blink = (t / 3500) % 10 == 0 && (t % 3500) < 150;
    int mouthW = (faceState == FACE_SPEAKING) ? 18 + ((t / 90) % 3) * 10 : 34;
    c.fillScreen(faceState == FACE_IDLE ? 0x000000 : 0x001028);

    // spin-ring medans Alfred tänker (roterande båge runt huvudet)
    if (faceState == FACE_THINKING) {
      int r = 92;
      float a = (t / 8) % 360 * 0.0174533f;    // snabb rotation
      for (int i = 0; i < 16; i++) {           // svans: 16 punkter, avtagande ljusstyrka
        float ang = a - i * 0.09f;
        uint8_t shade = 255 - i * 15;
        c.fillCircle(cx + (int)(cosf(ang) * r), cy + (int)(sinf(ang) * r), 5 - i / 6,
                     M5.Display.color565(shade, shade * 0.75f, 255));
      }
    }

    c.fillCircle(cx, cy, 78, 0xFFD54F);          // huvud
    int ey = cy - 18;
    if (blink) {                                          // blinkning (alla lägen)
      c.fillRect(cx - 34, ey, 22, 5, 0x333333);
      c.fillRect(cx + 12, ey, 22, 5, 0x333333);
    } else if (faceState == FACE_LISTENING) {
      // förvånad: stora ögon + upphöjda ögonbryn
      c.fillCircle(cx - 24, ey, 14, 0x222222);
      c.fillCircle(cx + 24, ey, 14, 0x222222);
      c.fillCircle(cx - 24, ey, 5, 0xFFFFFF);
      c.fillCircle(cx + 24, ey, 5, 0xFFFFFF);
      c.fillRect(cx - 38, ey - 24, 28, 5, 0x222222);
      c.fillRect(cx + 10, ey - 24, 28, 5, 0x222222);
    } else if (faceState == FACE_THINKING) {
      c.fillRect(cx - 34, ey + 6, 22, 5, 0x333333);   // halvslutna, skeptiska
      c.fillRect(cx + 12, ey + 2, 22, 5, 0x333333);
    } else {
      c.fillCircle(cx - 24, ey, 11, 0x222222);
      c.fillCircle(cx + 24, ey, 11, 0x222222);
    }
    if (faceState == FACE_LISTENING) {
      // öppen "O"-mun — lyssnar aktivt, pulserar
      int mo = 16 + ((t / 200) % 2) * 5;
      c.fillCircle(cx, cy + 32, mo, 0x222222);
    } else {
      int mw = (faceState == FACE_SPEAKING) ? mouthW : 34;
      c.fillRect(cx - mw, cy + 26, mw * 2, 10, 0x222222);
      c.fillCircle(cx - mw, cy + 31, 10, 0x222222);
      c.fillCircle(cx + mw, cy + 31, 10, 0x222222);
    }
    if (faceState == FACE_IDLE || faceState == FACE_SPEAKING) {  // kinder
      c.fillCircle(cx - 46, cy + 14, 9, 0xFF8A80);
      c.fillCircle(cx + 46, cy + 14, 9, 0xFF8A80);
    }
    bounce *= 0.92f;
  }

  // anropas från loop() — ritar om ENDAST när state ändrats eller en animation
  // verkligen behöver nya frames (thinking-spin, listening-puls, speaking-mun,
  // aktiva blinkningar). Idle = 1 paint/flipp per blink, annars lugnt.
  void draw(M5Canvas& c) {
    uint32_t t = millis();
    bool animating = (faceState == FACE_THINKING) || (faceState == FACE_LISTENING) ||
                     (faceState == FACE_SPEAKING);
    bool blinkActive = (t / 3500) % 10 == 0 && (t % 3500) < 200;
    bool bounceActive = bounce > 0.15f;

    if (!animating && !blinkActive && !bounceActive && faceState == drawnState &&
        drawnGen == screenGen) {
      return;                                   // inget nytt — ingen repaint
    }
    // begränsa fps endast när vi faktiskt animerar
    if (animating && t - lastDrawMs < 50) return;
    lastDrawMs = t;
    paint(c);
    drawnState = faceState;
    drawnGen = screenGen;
    c.pushSprite(0, 0);                         // EN flipp — ingen blinkning
  }
};

// ── Actions (2 kolumner, scrollbar) ──────────────────────────────────────────
struct Action { const char* label; const char* prompt; uint32_t color; };
static const Action ACTIONS[] = {
  {"Mail",   "Kolla min mail och rapportera kort om n\u00e5got viktigt dykt upp.", 0x4FC3F7u},
  {"Schema", "Vad har jag p\u00e5 schemat idag? Sammanfatta kort.",                0x81C784u},
  {"Kanban", "Vad ligger f\u00f6r nya kanban-uppgifter \u00e5t mig? Kort please.",  0xFFB74Du},
  {"Brief",  "Ge mig en kort daglig briefing.",                                    0xBA68C8u},
};
static const int N_ACTIONS = sizeof(ACTIONS) / sizeof(ACTIONS[0]);

struct Grid {
  int scrollRows = 0;              // 0-baserad första synliga rad
  int lastScroll = -1;             // för att veta när vi behöver rita om
  int drawnGen = -1;               // screenGen när senast ritad

  void paint(M5Canvas& c) {
    c.fillScreen(0x101014);
    c.setTextColor(0xAAAAAA, 0x101014);
    c.setTextSize(1);
    c.setCursor(8, 6);
    c.print("Alfred  \u2190\u2192 svep = byt sk\u00e4rm");
    const int W = 150, H = 70, GX = 10, GY = 12, TOP = 24;
    int rows = (N_ACTIONS + 1) / 2;
    for (int i = 0; i < N_ACTIONS; i++) {
      int r = i / 2, c2 = i % 2;
      int y = TOP + (r - scrollRows) * (H + GY);
      if (y + H < TOP || y > 240) continue;           // utanför skärmen
      int x = c2 * (W + GX) + (320 - 2 * W - GX) / 2;
      c.fillRoundRect(x, y, W, H, 8, ACTIONS[i].color);
      c.setTextColor(0x000000, ACTIONS[i].color);
      c.setTextSize(2);
      c.setCursor(x + 14, y + 26);
      c.print(ACTIONS[i].label);
    }
  }

  // Rita om endast när scroll ändrats, generation bytt eller första gången
  void draw(M5Canvas& c) {
    if (lastScroll == scrollRows && drawnGen == screenGen) return;
    paint(c);
    lastScroll = scrollRows;
    drawnGen = screenGen;
    c.pushSprite(0, 0);
  }

  // returnerar index för tryckt knapp, eller -1; uppdaterar scroll vid dra
  int touch(int tx, int ty, int dy) {
    if (dy > 30) { scrollRows = max(0, scrollRows - 1); return -1; }
    if (dy < -30) { int rows = (N_ACTIONS + 1) / 2; int maxRows = rows - 3;
                    if (maxRows > 0 && scrollRows < maxRows) scrollRows++;
                    return -1; }
    const int W = 150, H = 70, GX = 10, TOP = 24;
    for (int i = 0; i < N_ACTIONS; i++) {
      int r = i / 2, c2 = i % 2;
      int y = TOP + (r - scrollRows) * (H + 12);
      int x = c2 * (W + GX) + (320 - 2 * W - GX) / 2;
      if (tx >= x && tx <= x + W && ty >= y && ty <= y + H) return i;
    }
    return -1;
  }
};
