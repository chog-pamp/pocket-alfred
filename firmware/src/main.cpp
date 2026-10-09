// Pocket Alfred — M5Stack Core2
// States: wake.detected → LISTENING → transcribe → prompt.submit → THINKING → TTS → SPEAKING.
// Manuell väg (tills wake-träning): MITTEN-knappen (skärmens mittersta tredjedel)
// startar/stannar inspelning → gpt-4o-mini transkriberar → prompt.
// Svep vänster/höger: butler ↔ grid. Grid-tap → förbestämd prompt.
#include <M5Unified.h>
#include <WiFi.h>
#include <WiFiMulti.h>
#include "secrets.h"
#include "screens.h"     // FaceState + Face + Grid + ACTIONS
#include "capture.h"
#include "speaker.h"
#include "gateway.h"

WiFiMulti wifiMulti;
Face face;
Grid grid;
Capture capture;
M5Canvas canvas(&M5.Lcd);

FaceState faceState = FACE_IDLE;
int activeScreen = 0;
int screenGen = 0;
String replyAcc = "";
String sessionId = "";
long RPC_ID_SESSION_CREATE = 0;

bool manualRecording = false;    // mittenknapp-läge: hård-styrda inspelningar

void captureStart() { capture.begin(); manualRecording = false; }
void captureAbort() { capture.end(); manualRecording = false; }

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
  WiFi.setMinSecurity(WIFI_AUTH_WPA2_PSK);
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
  canvas.setColorDepth(16);
  canvas.createSprite(320, 240);
  gatewayConnect();
  Serial.println("[pocket-alfred] gateway connect initiated");
}

// mitten-tap: starta inspelning (mellan-zonen på skärmen)
void manualRecordStart() {
  if (manualRecording || faceState == FACE_THINKING || faceState == FACE_SPEAKING) return;
  faceState = FACE_LISTENING;
  capture.begin();
  manualRecording = true;
  Serial.println("[btn] manual recording started");
}

// mitten-tap igen (eller 10 s tak): stoppa → transkribera → prompt
void manualRecordStop() {
  if (!manualRecording) return;
  manualRecording = false;
  capture.end();
  Serial.printf("[btn] recording stopped, samples=%d\n", (int)capture.totalSamples());
  String text = transcribePcm(capture.pcm, capture.totalSamples());
  Serial.println("[btn] transcript: " + text);
  if (text.length() == 0) {
    faceState = FACE_IDLE;
  } else {
    sendPrompt(text);
  }
}

void loop() {
  M5.update();
  wifiMulti.run();
  gatewayLoop();

  // ── touch ──
  static int lastY = -1, lastX = -1;
  if (M5.Touch.isEnabled() && M5.Touch.getCount()) {
    auto t = M5.Touch.getDetail();
    if (t.state == m5::touch_state_t::touch_begin) { lastX = t.x; lastY = t.y; }
    else if (lastX >= 0 && t.state == m5::touch_state_t::touch_end) {
      int dx = t.x - lastX, dy = t.y - lastY;
      if (abs(dx) > 60 && abs(dx) > abs(dy)) {
        if (!manualRecording) {                 // svep låst under inspelning
          activeScreen = 1 - activeScreen;
          screenGen++;
        }
      } else if (activeScreen == 0 && t.y > 70 && t.y < 170 && t.x > 107 && t.x < 214) {
        // mitten-zonen: butlers ansikte → REC-toggle (fungerar på båda skärmarna via zonen? nej — endast skärm 0)
        if (!manualRecording) manualRecordStart(); else manualRecordStop();
      } else if (activeScreen == 1) {
        int idx = grid.touch(t.x, t.y, dy);
        if (idx >= 0) { activeScreen = 0; sendPrompt(ACTIONS[idx].prompt); }
      }
      lastX = -1;
    }
  }

  // hård tidsgräns: 10 s inspelning max → auto-stopp
  if (manualRecording && capture.frames >= Capture::MAX_CHUNKS) manualRecordStop();

  // rendering
  if (activeScreen == 0) {
    face.draw(canvas);
  } else {
    grid.draw(canvas);
  }

  // ── mic-hantering ──
  if (manualRecording) {
    if (capture.chunk()) {                    // VAD-stoppt eller tak
      manualRecording = false;
      capture.end();
      String text = transcribePcm(capture.pcm, capture.totalSamples());
      Serial.println("[rec] transcript: " + text);
      if (text.length()) sendPrompt(text); else faceState = FACE_IDLE;
    }
  } else if (faceState == FACE_LISTENING && !manualRecording) {
    // wake-detekterad lyssning: VAD-loopen (som tidigare)
    if (capture.chunk()) {
      String text = transcribePcm(capture.pcm, capture.totalSamples());
      capture.end();
      if (text.length() == 0) capture.begin();   // ingen tal — lyssna vidare
      else sendPrompt(text);
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
  static uint32_t lastHeal = 0;
  if (millis() - lastHeal > 20000) {
    lastHeal = millis();
    if (ws.isConnected() && sessionId.length() == 0) gatewayReady();
  }
}
