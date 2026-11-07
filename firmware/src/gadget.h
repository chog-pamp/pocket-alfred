#pragma once
#include <M5Unified.h>
#include <ArduinoJson.h>
#include <WebSocketsClient.h>
#include <WiFi.h>
#include <Preferences.h>
#include <mbedtls/sha256.h>
#include <mbedtls/md.h>
#include <mbedtls/base64.h>
#include "secrets.h"
#include "screens.h"   // FaceState

// ── Hermes Gadget protocol v1 client (hermes-gadget.v1) ──────────────────────
// Replaces the old custom WS-RPC gateway. Server: gadget plugin, ws://host:8765/gadget
// Flow: hello → challenge → auth (enroll or HMAC) → welcome → conversation.
// Heartbeat: server sends {"type":"ping"} every heartbeat_s (20); reply pong.

// states for the app layer (in main.cpp)
extern FaceState faceState;   // IDLE/LISTENING/THINKING/SPEAKING
extern String gTranscript;    // what STT heard (card screen)
extern String gReply;         // reply text (card screen)
extern String gStatus;        // live status phrase
extern int    gScreen;        // 0=face 1=grid 2=card 3=pairing
extern String gPairCode;
extern String gPromptId;      // pending yes/no question
extern String gPromptTitle;
extern String gPromptText;
extern bool   gAudioPlaying;

WebSocketsClient ws;
Preferences prefs;
static uint8_t devKey[32];
static char devId[32];                 // "hg-" + 16 hex
static bool enrolled = false;
static int  heartbeatS = 20;
static long audioSeq = 0;
static int  audioStream = 4;           // our upload stream id
static String audioId = "";
static uint32_t talkStartMs = 0;
static int  rpcMsgId = 0;

// speaker: i2s is owned by speaker.h (initSpeaker with 16 kHz mono)
bool initSpeaker();
extern bool gSpeakerInit;

// forward (implemented in main.cpp)
void gadgetDraw();       // called by main loop to paint card/pairing screens
void startTalk();
void stopTalk();
bool talking = false;

// ── helpers ──────────────────────────────────────────────────────────────────
static String b64enc(const uint8_t* src, size_t len) {
  // 32-byte input → 44 b64 chars + NUL; mbedtls includes the NUL in olen.
  // NOTE: must build the String from a real char buffer — writing through
  // String::begin() never updates the Arduino String length (sends empty).
  char buf[64];
  size_t olen = 0;
  mbedtls_base64_encode(nullptr, 0, &olen, src, len);
  if (olen == 0 || olen > sizeof(buf)) return String();
  mbedtls_base64_encode((uint8_t*)buf, sizeof(buf), &olen, src, len);
  return String(buf);
}

static String hmacAuth(const String& nonce) {
  // HMAC-SHA256(key, "hermes-gadget/v1|" + device_id + "|" + nonce), base64
  const char* ctx = "hermes-gadget/v1|";
  String msg = String(ctx) + String(devId) + "|" + nonce;
  uint8_t mac[32];
  const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_hmac(info, devKey, 32, (const uint8_t*)msg.c_str(), msg.length(), mac);
  return b64enc(mac, 32);
}

static String jsonEscape(const String& t) {
  String e; e.reserve(t.length() + 8);
  for (char c : t) {
    if (c == '"') e += "\\\"";
    else if (c == '\\') e += "\\\\";
    else if (c == '\n') e += "\\n";
    else if (c >= 32 && c != 127) e += c;
  }
  return e;
}

static void sendJson(String s) { ws.sendTXT(s); }

static void sendStateBattery() {
  int pct = M5.Power.getBatteryLevel();
  if (pct < 0 || pct > 100) return;
  char b[96];
  snprintf(b, sizeof(b), "{\"type\":\"state\",\"sensors\":{\"battery_pct\":%d}}", pct);
  sendJson(String(b));
}

// ── audio upload (hold-to-talk) ──────────────────────────────────────────────
void startTalk() {
  if (talking || gAudioPlaying) return;
  talking = true;
  faceState = FACE_LISTENING;
  audioSeq = 0;
  audioId = "a" + String(++rpcMsgId);
  talkStartMs = millis();
  char p[160];
  snprintf(p, sizeof(p),
    "{\"type\":\"audio.start\",\"id\":\"%s\",\"stream\":%d,\"rate\":16000,\"format\":\"pcm16\",\"mode\":\"hold\"}",
    audioId.c_str(), audioStream);
  sendJson(String(p));
}

void stopTalk() {
  if (!talking) return;
  talking = false;
  uint32_t dur = millis() - talkStartMs;
  M5.Mic.end();
  char p[160];
  snprintf(p, sizeof(p),
    "{\"type\":\"audio.end\",\"id\":\"%s\",\"stream\":%d,\"duration_ms\":%lu}",
    audioId.c_str(), audioStream, (unsigned long)dur);
  sendJson(String(p));
  audioStream = (audioStream + 1) & 0xFF;   // next utterance on a new stream
  faceState = FACE_THINKING;                // wait for transcript/reply
}

// call from loop while talking: feed 100 ms mic chunks
void gadgetTalkChunk() {
  static int16_t abuf[1600];
  M5.Mic.record(abuf, 1600, 16000);
  uint8_t hdr[4] = {0x01, (uint8_t)audioStream, 0, 0};
  hdr[2] = (audioSeq >> 8) & 0xFF;          // u16 LE: low byte first
  hdr[2] = audioSeq & 0xFF;
  hdr[3] = (audioSeq >> 8) & 0xFF;
  audioSeq++;
  String frame;
  frame.reserve(4 + 3200);
  frame.concat((const char*)hdr, 4);
  frame.concat((const char*)abuf, 3200);
  ws.sendBIN((uint8_t*)frame.begin(), frame.length());
}

// ── binary frames from server (channel 1 = speaker PCM16) ────────────────────
static void handleBinary(uint8_t* payload, size_t len) {
  if (len < 4) return;
  uint8_t channel = payload[0];
  size_t plen = len - 4;
  uint8_t* p = payload + 4;
  if (channel == 0x01 && gAudioPlaying && plen) {
    if (!gSpeakerInit) { gSpeakerInit = initSpeaker(); }
    if (gSpeakerInit) {
      i2s.write((uint8_t*)p, plen);         // server paces frames in real time
    }
  }
  // channel 2 (images) and 4 (faces): not drawn in this firmware version
}

// ── text messages from server ────────────────────────────────────────────────
static void handleText(uint8_t* payload, size_t len) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) return;
  const char* type = doc["type"] | "";

  if (!strcmp(type, "challenge")) {
    String nonce = (const char*)(doc["nonce"] | "");
    if (enrolled) {
      sendJson("{\"type\":\"auth\",\"mac\":\"" + hmacAuth(nonce) + "\"}");
    } else {
      sendJson("{\"type\":\"auth\",\"key\":\"" + b64enc(devKey, 32) + "\"}");
    }
  } else if (!strcmp(type, "welcome")) {
    heartbeatS = doc["heartbeat_s"] | 20;
    enrolled = true;                          // key accepted; HMAC from now on
    prefs.begin("gadget", false);
    prefs.putBytes("key", devKey, 32);
    prefs.putString("id", String(devId));
    prefs.putBool("enrolled", true);
    prefs.end();
    gPairCode = "";
    bool paired = doc["paired"] | false;
    Serial.printf("[gadget] welcome paired=%d hb=%d\n", paired, heartbeatS);
    if (paired) { gScreen = 0; sendStateBattery(); }
  } else if (!strcmp(type, "ping")) {
    char p[64];
    snprintf(p, sizeof(p), "{\"type\":\"pong\",\"ts\":%lld}", (long long)(millis()));
    sendJson(String(p));
  } else if (!strcmp(type, "pairing")) {
    gPairCode = (const char*)(doc["code"] | "");
    gScreen = 3;
    Serial.println("[gadget] pairing code: " + gPairCode);
  } else if (!strcmp(type, "paired")) {
    gPairCode = "";
    gScreen = 0;
  } else if (!strcmp(type, "unpaired")) {
    gPairCode = "";
    gScreen = 3;
  } else if (!strcmp(type, "turn.start")) {
    gTranscript = ""; gReply = ""; gStatus = "";
    faceState = FACE_THINKING;
    if (gScreen == 2) { /* keep card open */ }
  } else if (!strcmp(type, "transcript")) {
    gTranscript = (const char*)(doc["text"] | "");
    gScreen = 2;
  } else if (!strcmp(type, "status")) {
    gStatus = (const char*)(doc["text"] | "");
  } else if (!strcmp(type, "reply.delta")) {
    gReply = (const char*)(doc["text"] | "");
    gScreen = 2;
  } else if (!strcmp(type, "reply")) {
    gReply = (const char*)(doc["text"] | "");
    gScreen = 2;
  } else if (!strcmp(type, "turn.end")) {
    gStatus = "";
    if (faceState == FACE_THINKING) faceState = FACE_IDLE;
  } else if (!strcmp(type, "audio.start")) {
    gAudioPlaying = true;
    faceState = FACE_SPEAKING;
    gScreen = 2;
  } else if (!strcmp(type, "audio.end")) {
    gAudioPlaying = false;
    faceState = FACE_IDLE;
  } else if (!strcmp(type, "audio.abort")) {
    gAudioPlaying = false;
    faceState = FACE_IDLE;
  } else if (!strcmp(type, "notice")) {
    gStatus = (const char*)(doc["text"] | "");
  } else if (!strcmp(type, "display")) {
    // agent card: show as reply text
    gTranscript = (const char*)(doc["title"] | "");
    gReply = (const char*)(doc["body"] | "");
    gScreen = 2;
  } else if (!strcmp(type, "prompt")) {
    gPromptId = (const char*)(doc["id"] | "");
    gPromptTitle = (const char*)(doc["title"] | "");
    gPromptText = (const char*)(doc["text"] | "");
    gScreen = 4;
  } else if (!strcmp(type, "prompt.close")) {
    gPromptId = "";
    gScreen = 0;
  } else if (!strcmp(type, "error")) {
    Serial.printf("[gadget] error %s: %s\n", (const char*)(doc["code"] | ""),
                  (const char*)(doc["message"] | ""));
  }
}

static void onWsEvent(WStype_t type, uint8_t* payload, size_t len) {
  switch (type) {
    case WStype_CONNECTED: {
      Serial.println("[gadget] ws connected");
      // hello
      int pct = M5.Power.getBatteryLevel();
      char hello[640];
      snprintf(hello, sizeof(hello),
        "{\"type\":\"hello\",\"proto\":1,\"device_id\":\"%s\",\"name\":\"Pocket Alfred\","
        "\"board\":\"m5stack-core2\",\"firmware\":\"1.0.0-gadget\","
        "\"caps\":{\"display\":{\"width\":320,\"height\":240,\"color\":true,\"charset\":\"latin1\","
        "\"text_cols\":26,\"text_rows\":8,\"image\":{\"width\":320,\"height\":196,\"format\":\"rgb565\"}},"
        "\"mic\":{\"rate\":16000,\"format\":\"pcm16\"},"
        "\"speaker\":{\"rate\":16000,\"format\":\"pcm16\",\"buffer_ms\":2048},"
        "\"inputs\":[\"talk\",\"cancel\"],\"talk_mode\":\"hold\"},"
        "\"sensors\":{\"battery_pct\":%d}}",
        devId, pct);
      sendJson(String(hello));
      break;
    }
    case WStype_TEXT:   handleText(payload, len); break;
    case WStype_BIN:    handleBinary(payload, len); break;
    case WStype_DISCONNECTED:
      Serial.println("[gadget] disconnected");
      talking = false;
      gAudioPlaying = false;
      break;
    default: break;
  }
}

// ── lifecycle ────────────────────────────────────────────────────────────────
void gadgetConnect() {
  prefs.begin("gadget", true);
  bool have = prefs.isKey("key") && prefs.isKey("id");
  if (have) {
    prefs.getBytes("key", devKey, 32);
    String id = prefs.getString("id");
    strlcpy(devId, id.c_str(), sizeof(devId));
    enrolled = prefs.getBool("enrolled", false);
  }
  prefs.end();
  if (!have) {
    for (int i = 0; i < 32; i++) devKey[i] = (uint8_t)esp_random();
    uint8_t hash[32];
    mbedtls_sha256(devKey, 32, hash, 0);
    static const char* hex = "0123456789abcdef";
    devId[0] = 'h'; devId[1] = 'g'; devId[2] = '-';
    for (int i = 0; i < 8; i++) {
      devId[3 + i * 2]     = hex[hash[i] >> 4];
      devId[3 + i * 2 + 1] = hex[hash[i] & 0xF];
    }
    devId[19] = 0;
    Serial.printf("[gadget] new device id %s\n", devId);
  }

  ws.begin(GADGET_HOST, GADGET_PORT, "/gadget", "hermes-gadget.v1");
  ws.onEvent(onWsEvent);
  ws.setReconnectInterval(5000);
  ws.enableHeartbeat(15000, 5000, 2);
}

void gadgetLoop() {
  ws.loop();
  // battery state every 60 s (also acts as app-level keepalive)
  static uint32_t lastBat = 0;
  if (millis() - lastBat > 60000) {
    lastBat = millis();
    if (ws.isConnected()) sendStateBattery();
  }
}

// text message (actions grid)
void gadgetSendText(const String& text) {
  char id[16]; snprintf(id, sizeof(id), "t%d", ++rpcMsgId);
  String s = "{\"type\":\"text\",\"id\":\"" + String(id) + "\",\"text\":\"" +
             jsonEscape(text) + "\"}";
  sendJson(s);
  gReply = ""; gTranscript = "";
  faceState = FACE_THINKING;
}

void gadgetCancel()   { sendJson("{\"type\":\"cancel\"}"); }
void gadgetNewSession(){ sendJson("{\"type\":\"session.new\"}"); }
void gadgetPromptReply(bool yes) {
  if (!gPromptId.length()) return;
  char p[128];
  snprintf(p, sizeof(p), "{\"type\":\"prompt.reply\",\"id\":\"%s\",\"answer\":\"%s\"}",
           gPromptId.c_str(), yes ? "yes" : "no");
  sendJson(String(p));
  gPromptId = "";
  gScreen = 0;
}
