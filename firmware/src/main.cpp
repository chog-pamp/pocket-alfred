// Pocket Alfred — M5Stack Core2 — Hermes Gadget protocol client
// Tap middle zone (bottom row) = start talk (PCM16 upload), tap again = end · left = cancel · right = new session
// Swipe = switch screen (face ↔ grid). Grid tap = text message. Replies open a card screen.
#include <M5Unified.h>
#include <WiFi.h>
#include <WiFiMulti.h>
#include "secrets.h"
#include "screens.h"
#include "speaker.h"
#include "gadget.h"

WiFiMulti wifiMulti;
Face face;
Grid grid;
M5Canvas canvas(&M5.Lcd);

FaceState faceState = FACE_IDLE;
int  gScreen = 0;              // 0=face 1=grid 2=card 3=pairing 4=prompt
int  screenGen = 0;
String gTranscript = "";
String gReply = "";
String gStatus = "";
String gPairCode = "";
String gPromptId = "";
String gPromptTitle = "";
String gPromptText = "";
bool   gAudioPlaying = false;
bool   gSpeakerInit = false;

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);
  Serial.println("\n[pocket-alfred] boot (gadget)");
  M5.Display.setRotation(0);
  M5.Lcd.setTextColor(0xFFFFFF, 0x000000);
  M5.Lcd.setTextSize(2);
  M5.Lcd.println("Pocket Alfred");
  M5.Lcd.setTextSize(1);
  WiFi.mode(WIFI_STA);
  WiFi.setMinSecurity(WIFI_AUTH_WPA2_PSK);
  WiFi.setAutoReconnect(true);
  Serial.printf("[wifi] connecting to %s ...\n", WIFI_SSID);
  wifiMulti.addAP(WIFI_SSID, WIFI_PASS);
  wifiMulti.addAP(WIFI_SSID2, WIFI_PASS2);
  while (wifiMulti.run() != WL_CONNECTED) {
    delay(300); M5.Lcd.print(".");
  }
  M5.Lcd.println("\nWiFi OK " + WiFi.localIP().toString());
  Serial.println("[pocket-alfred] wifi: " + WiFi.localIP().toString());
  canvas.setColorDepth(16);
  canvas.createSprite(320, 240);
  gadgetConnect();
  Serial.println("[pocket-alfred] gadget connect initiated");
}

// ── card / pairing / prompt painters (same canvas, one flipp) ────────────────
static void drawWrapped(M5Canvas& c, const String& text, int x, int y, int maxW, uint16_t color) {
  c.setTextColor(color, 0x0A0A0C);
  c.setTextSize(2);
  int lineH = 22;
  int cx = x, cy = y;
  int spaceW = 10;
  int start = 0;
  for (int i = 0; i <= (int)text.length(); i++) {
    if (i == (int)text.length() || text[i] == ' ' || text[i] == '\n') {
      String word = text.substring(start, i);
      start = i + 1;
      if (!word.length()) continue;
      int w = word.length() * 12;
      if (cx + w > x + maxW && cx > x) { cx = x; cy += lineH; }
      c.setCursor(cx, cy);
      c.print(word);
      cx += w + spaceW;
      if (cy > 196) return;                    // v1: no scroll, klipp
    }
  }
}

static void paintCard() {
  canvas.fillScreen(0x0A0A0C);
  if (gTranscript.length()) {
    canvas.setTextColor(0x55555C, 0x0A0A0C);
    canvas.setTextSize(1);
    canvas.setCursor(10, 8);
    canvas.print("you: " + gTranscript.substring(0, 46));
  }
  if (gStatus.length()) {
    canvas.setTextColor(0x4FC3F7, 0x0A0A0C);
    canvas.setTextSize(1);
    canvas.setCursor(10, 22);
    canvas.print(gStatus.substring(0, 50));
  }
  if (gReply.length()) {
    drawWrapped(canvas, gReply, 12, 44, 296, 0xE8E8EC);
  } else if (faceState == FACE_THINKING) {
    canvas.setTextColor(0x8A8A92, 0x0A0A0C);
    canvas.setTextSize(2);
    canvas.setCursor(12, 60);
    canvas.print("Thinking...");
  }
  canvas.setTextColor(0x3A3A42, 0x0A0A0C);
  canvas.setTextSize(1);
  canvas.setCursor(10, 224);
  canvas.printf("%d%%  ·  swipe = back", M5.Power.getBatteryLevel());
}

static void paintPairing() {
  canvas.fillScreen(0x0A0A0C);
  canvas.setTextColor(0xE8E8EC, 0x0A0A0C);
  canvas.setTextSize(2);
  canvas.setTextDatum(4);                       // middle center
  canvas.drawString("Pairing code", 160, 48);
  canvas.setTextSize(1);
  canvas.setTextColor(0x8A8A92, 0x0A0A0C);
  canvas.drawString("approve on the hermes host:", 160, 92);
  if (gPairCode.length()) {
    canvas.setTextColor(0x64FFDA, 0x0A0A0C);
    canvas.setTextSize(4);
    canvas.drawString(gPairCode, 160, 130);
  } else {
    canvas.setTextColor(0x55555C, 0x0A0A0C);
    canvas.setTextSize(2);
    canvas.drawString("connecting...", 160, 130);
  }
  canvas.setTextDatum(0);
}

static void paintPrompt() {
  canvas.fillScreen(0x1A0A0C);
  canvas.setTextColor(0xFFD54F, 0x1A0A0C);
  canvas.setTextSize(2);
  canvas.setTextDatum(4);
  canvas.drawString(gPromptTitle.substring(0, 24), 160, 36);
  canvas.setTextDatum(0);
  drawWrapped(canvas, gPromptText, 14, 80, 292, 0xE8E8EC);
  canvas.fillRect(0, 190, 160, 50, 0x3A1A1A);
  canvas.fillRect(160, 190, 160, 50, 0x1A3A22);
  canvas.setTextDatum(4);
  canvas.setTextColor(0xFF8A80, 0x3A1A1A);
  canvas.setTextSize(3);
  canvas.drawString("NO", 80, 214);
  canvas.setTextColor(0x81C784, 0x1A3A22);
  canvas.drawString("YES", 240, 214);
  canvas.setTextDatum(0);
}

void loop() {
  M5.update();
  wifiMulti.run();
  gadgetLoop();

  static int lastX = -1, lastY = -1;
  if (M5.Touch.isEnabled() && M5.Touch.getCount()) {
    auto t = M5.Touch.getDetail();
    if (t.state == m5::touch_state_t::touch_begin) {
      lastX = t.x; lastY = t.y;
      // tap-toggle recording: while talking, ANY tap ends the utterance
      if (talking) { stopTalk(); return; }
      // prompt screen: tap zones answer
      if (gScreen == 4 && gPromptId.length() && t.y > 190) {
        gadgetPromptReply(t.x >= 160);
        return;
      }
      // face screen bottom row: cancel | talk(hold) | new session
      if (gScreen == 0 && faceState == FACE_IDLE && !gAudioPlaying && t.y > 170) {
        if (t.x >= 107 && t.x < 214) { startTalk(); }
        else if (t.x < 107)          { gadgetCancel(); }
        else                         { gadgetNewSession(); }
      }
    } else if (lastX >= 0 && t.state == m5::touch_state_t::touch_end) {
      int dx = t.x - lastX, dy = t.y - lastY;
      if (!talking && abs(dx) > 60 && abs(dx) > abs(dy) && gScreen != 4) {
        if (gScreen == 0 || gScreen == 2) gScreen = 1;
        else if (gScreen == 1)            gScreen = 0;
        screenGen++;
      } else if (gScreen == 1) {
        int idx = grid.touch(t.x, t.y, dy);
        if (idx >= 0) gadgetSendText(ACTIONS[idx].prompt);
      }
      lastX = -1;
    }
  }
  if (talking) gadgetTalkChunk();

  // rendering — dirty-check per screen
  if (gScreen == 0) {
    face.draw(canvas);
  } else if (gScreen == 1) {
    grid.draw(canvas);
  } else if (gScreen == 2) {
    static int lastGen = -1;
    static String lastReply = "", lastTr = "", lastSt = "";
    if (lastGen != screenGen || lastReply != gReply || lastTr != gTranscript || lastSt != gStatus) {
      paintCard();
      lastGen = screenGen; lastReply = gReply; lastTr = gTranscript; lastSt = gStatus;
      canvas.pushSprite(0, 0);
    }
  } else if (gScreen == 3) {
    static String lastCode = "";
    if (lastCode != gPairCode) {
      paintPairing();
      lastCode = gPairCode;
      canvas.pushSprite(0, 0);
    }
  } else if (gScreen == 4) {
    static int lastGen = -1;
    if (lastGen != screenGen) {
      paintPrompt();
      lastGen = screenGen;
      canvas.pushSprite(0, 0);
    }
  }
}
