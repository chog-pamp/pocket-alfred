// Pocket Alfred — M5Stack Core2
// Kör: wake.detected → capture → transcribe → prompt.submit → TTS-svar.
// Svep vänster/höger: byt skärm (emoji ↔ grid). Knapptap → förbestämd prompt.
#include <M5Unified.h>
#include <WiFi.h>
#include <WiFiMulti.h>
#include "secrets.h"
#include "screens.h"     // FaceState + Face + Grid + ACTIONS (inga deps på gateway)
#include "capture.h"
#include "speaker.h"
#include "gateway.h"

WiFiMulti wifiMulti;
Face face;
Grid grid;
Capture capture;

FaceState faceState = FACE_IDLE;
int activeScreen = 0;
String replyAcc = "";
String sessionId = "";
long RPC_ID_SESSION_CREATE = 0;

void captureStart() { capture.begin(); }
void captureAbort() { capture.end(); }

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);
  Serial.println("\n[pocket-alfred] boot");
  M5.Display.setRotation(0);
  M5.Lcd.setTextColor(0xFFFFFF, 0x000000);
  M5.Lcd.setTextSize(2);
  M5.Lcd.println("Pocket Alfred");
  M5.Lcd.setTextSize(1);
  WiFi.mode(WIFI_STA);
  WiFi.setMinSecurity(WIFI_AUTH_WPA2_PSK);  // tillåt WPA2 (PMF-capable ok)
  WiFi.setAutoReconnect(true);
  Serial.printf("[wifi] connecting to %s ...\n", WIFI_SSID);
  wifiMulti.addAP(WIFI_SSID, WIFI_PASS);
  wifiMulti.addAP(WIFI_SSID2, WIFI_PASS2);
  while (wifiMulti.run() != WL_CONNECTED) {
    delay(300); M5.Lcd.print(".");
    static uint32_t lastLog = 0;
    if (millis() - lastLog > 3000) {
      lastLog = millis();
      Serial.printf("[wifi] status=%d\n", WiFi.status());
      int n = WiFi.scanNetworks();
      for (int i = 0; i < n && i < 6; i++)
        Serial.printf("  seen: %s ch%d %ddBm %s\n", WiFi.SSID(i).c_str(),
                      WiFi.channel(i), WiFi.RSSI(i),
                      WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "open" : "sec");
    }
  }
  M5.Lcd.println("\nWiFi OK " + WiFi.localIP().toString());
  Serial.println("[pocket-alfred] wifi connected: " + WiFi.localIP().toString());
  gatewayConnect();
  Serial.println("[pocket-alfred] gateway connect initiated");
}

void loop() {
  M5.update();
  wifiMulti.run();
  gatewayLoop();

  // touch: svep = skärmbyte; tap = knapp (endast på grid-skärmen)
  static int lastY = -1, lastX = -1;
  if (M5.Touch.isEnabled() && M5.Touch.getCount()) {
    auto t = M5.Touch.getDetail();
    if (t.state == m5::touch_state_t::touch_begin) { lastX = t.x; lastY = t.y; }
    else if (lastX >= 0 && t.state == m5::touch_state_t::touch_end) {
      int dx = t.x - lastX, dy = t.y - lastY;
      if (abs(dx) > 60 && abs(dx) > abs(dy)) {
        activeScreen = 1 - activeScreen;
        if (activeScreen) grid.draw(); else face.draw();
      } else if (activeScreen == 1) {
        int idx = grid.touch(t.x, t.y, dy);
        if (idx >= 0) { face.bounce = 1.0f; activeScreen = 0; sendPrompt(ACTIONS[idx].prompt); }
      }
      lastX = -1;
    }
  }

  static uint32_t lastDraw = 0;
  if (millis() - lastDraw > 66) {                  // ~15 fps
    lastDraw = millis();
    if (activeScreen == 0) face.draw();
  }
  if (faceState == FACE_LISTENING) {
    if (capture.chunk()) {
      String text = transcribePcm(capture.pcm, capture.totalSamples());
      capture.end();
      if (text.length() == 0) {
        capture.begin();                           // ingen tal — lyssna vidare
      } else {
        sendPrompt(text);
      }
    }
  } else if (sessionId.length()) {
    // idle: feeda mic till serverns wake-detektor (sherpa client-capture)
    static int16_t wbuf[1600];
    M5.Mic.begin();
    M5.Mic.setSampleRate(16000);
    M5.Mic.record(wbuf, 1600, 16000);
    wakeFeed(wbuf, 1600);
    M5.Mic.end();
  }
  static uint32_t lastPing = 0;
  if (millis() - lastPing > 15000) { lastPing = millis(); rpcPing(); }
  // self-heal: om vi tappat session (server reap) — skapa om + wake.start
  static uint32_t lastHeal = 0;
  if (millis() - lastHeal > 20000) {
    lastHeal = millis();
    if (ws.isConnected() && sessionId.length() == 0) gatewayReady();
  }
}
