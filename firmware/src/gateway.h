#pragma once
#include <M5Unified.h>
#include <ArduinoJson.h>
#include <WebSocketsClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <mbedtls/base64.h>
#include "secrets.h"
#include "screens.h"   // FaceState

// Framåtdeklarerade (definieras i main.cpp / speaker.h)
void captureStart();
void captureAbort();
bool playMp3(const uint8_t* mp3, size_t len);

extern String sessionId;
extern String replyAcc;
extern long RPC_ID_SESSION_CREATE;
extern FaceState faceState;

WebSocketsClient ws;
int rpcId = 0;

// base64 → Arduino-String (oleng olen inkluderar NUL)
static String b64(const uint8_t* src, size_t len) {
  size_t olen = 0;
  mbedtls_base64_encode(nullptr, 0, &olen, src, len);
  String out; out.reserve(olen);
  mbedtls_base64_encode((uint8_t*)out.begin(), olen, &olen, src, len);
  out[olen - 1] = 0;    // strip trailing NUL
  return out;
}

// ── wake.feed: strömma mic-PCM till serverns wake-detektor (client-capture) ───
void wakeFeed(const int16_t* pcm, size_t samples) {
  String frame = "{\"pcm_b64\":\"";
  frame += b64((const uint8_t*)pcm, samples * 2);
  frame += "\",\"sample_rate\":16000}";
  String s = "{\"jsonrpc\":\"2.0\",\"id\":0,\"method\":\"wake.feed\",\"params\":";
  s += frame;
  s += "}";
  ws.sendTXT(s);
}

// JSON-escape för transcript/svarstext (behåller UTF-8 som är)
String jsonEscape(const String& text) {
  String esc;
  esc.reserve(text.length() + 16);
  for (char c : text) {
    if (c == '"') esc += "\\\"";
    else if (c == '\\') esc += "\\\\";
    else if (c >= 32 && c != 127) esc += c;
  }
  return esc;
}

// RPC med params som färdigserialiserad JSON-sträng
void rpc(const char* method, const char* paramsJson) {
  String s = "{\"jsonrpc\":\"2.0\",\"id\":";
  s += ++rpcId;
  s += ",\"method\":\"";
  s += method;
  s += "\",\"params\":";
  s += paramsJson;
  s += "}";
  ws.sendTXT(s);
}

void rpcPing() {
  char p[24]; snprintf(p, sizeof(p), "{\"n\":%d}", rpcId);
  rpc("ping", p);
}

// ── transcribe ───────────────────────────────────────────────────────────────
String transcribePcm(const int16_t* pcm, size_t samples) {
  size_t wavBytes = 44 + samples * 2;
  uint8_t* buf = (uint8_t*)malloc(wavBytes);
  if (!buf) return "";
  uint32_t dataLen = samples * 2;
  memcpy(buf, "RIFF", 4); uint32_t riff = 36 + dataLen; memcpy(buf + 4, &riff, 4);
  memcpy(buf + 8, "WAVE", 4);
  memcpy(buf + 12, "fmt ", 4); uint32_t fmtLen = 16; memcpy(buf + 16, &fmtLen, 4);
  uint16_t fmt = 1, ch = 1; memcpy(buf + 20, &fmt, 2); memcpy(buf + 22, &ch, 2);
  uint32_t sr = 16000; memcpy(buf + 24, &sr, 4);
  uint32_t br = 32000; memcpy(buf + 28, &br, 4);
  uint16_t ba = 2, bits = 16; memcpy(buf + 32, &ba, 2); memcpy(buf + 34, &bits, 2);
  memcpy(buf + 36, "data", 4); memcpy(buf + 40, &dataLen, 4);
  memcpy(buf + 44, pcm, dataLen);

  String b64audio = b64(buf, wavBytes);
  free(buf);

#ifdef GATEWAY_TLS
  WiFiClientSecure client; client.setInsecure();
  HTTPClient http;
  String url0 = String("https://") + GATEWAY_HOST + "/api/audio/transcribe";
  http.begin(client, url0);
#else
  WiFiClient client;
  HTTPClient http;
  String url0 = String("http://") + GATEWAY_HOST + ":" + GATEWAY_PORT_STR + "/api/audio/transcribe";
  http.begin(client, url0);
#endif
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Hermes-Session-Token", GATEWAY_TOKEN);
  http.setTimeout(20000);
  String body = "{\"data_url\":\"data:audio/wav;base64," + b64audio +
                "\",\"mime_type\":\"audio/wav\"}";
  int code = http.POST(body);
  String transcript = "";
  if (code == 200) {
    JsonDocument d;
    deserializeJson(d, http.getString());
    transcript = String((const char*)(d["transcript"] | ""));
  }
  http.end();
  return transcript;
}

// ── speak (Väg B): POST → data_url → råa MP3-bytes ───────────────────────────
uint8_t* fetchSpeakMp3(const String& text, size_t* outLen) {
#ifdef GATEWAY_TLS
  WiFiClientSecure client; client.setInsecure();
  String url1 = String("https://") + GATEWAY_HOST + "/api/audio/speak";
  http.begin(client, url1);
#else
  WiFiClient client;
  HTTPClient http;
  String url1 = String("http://") + GATEWAY_HOST + ":" + GATEWAY_PORT_STR + "/api/audio/speak";
  http.begin(client, url1);
#endif
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Hermes-Session-Token", GATEWAY_TOKEN);
  http.setTimeout(30000);
  String body = "{\"text\":\"" + jsonEscape(text) + "\"}";
  int code = http.POST(body);
  uint8_t* mp3 = nullptr; *outLen = 0;
  if (code == 200) {
    String resp = http.getString();
    JsonDocument d;
    if (deserializeJson(d, resp) == DeserializationError::Ok) {
      const char* du = d["data_url"] | "";
      const char* comma = strchr(du, ',');
      if (comma && strstr(du, ";base64,")) {
        size_t blen = strlen(comma + 1);
        uint8_t* raw = (uint8_t*)malloc(blen);
        size_t olen = 0;
        if (raw && mbedtls_base64_decode(raw, blen, &olen,
                                         (const uint8_t*)comma + 1, blen) == 0) {
          mp3 = raw; *outLen = olen;
        } else free(raw);
      }
    }
  }
  http.end();
  return mp3;
}

// ── WS events ────────────────────────────────────────────────────────────────
void gatewayReady();                    // fwd-deklaration (def nedanför)
void onWsEvent(WStype_t type, uint8_t* payload, size_t len) {
  Serial.printf("[ws] event type=%d len=%d\n", (int)type, (int)len);
  if (type == WStype_CONNECTED) { gatewayReady(); return; }   // skapa session → wake.start
  if (type == WStype_DISCONNECTED) { Serial.println("[ws] disconnected"); return; }
  if (type != WStype_TEXT) return;
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) return;

  if (doc["method"].is<const char*>()) {
    const char* m = doc["method"];
    JsonDocument ev = doc["params"];
    String evType = (strcmp(m, "event") == 0)
        ? String((const char*)(ev["type"] | "")) : String(m);
    if (evType == "wake.detected") {
      faceState = FACE_LISTENING;
      captureStart();
    } else if (evType == "message.delta") {
      replyAcc += (const char*)(ev["text"] | "");
    } else if (evType == "message.complete") {
      String full = (const char*)(ev["text"] | "");
      if (full.length() < replyAcc.length()) full = replyAcc;
      replyAcc = "";
      if (full.length()) {
        size_t n = 0;
        uint8_t* mp3 = fetchSpeakMp3(full, &n);
        if (mp3) { playMp3(mp3, n); free(mp3); }
        String p = "{\"surface\":\"gui\",\"client_capture\":true,\"session_id\":\"" +
                   sessionId + "\"}";
        rpc("wake.start", p.c_str());
      }
    }
  } else if (doc["id"].is<long>()) {
    long id = doc["id"];
    if (id == RPC_ID_SESSION_CREATE) {
      sessionId = (const char*)(doc["result"]["session_id"] | "");
      String p = "{\"surface\":\"gui\",\"client_capture\":true,\"session_id\":\"" +
                 sessionId + "\"}";
      rpc("wake.start", p.c_str());
    }
  }
}

void gatewayConnect() {
  String url = String("/api/ws?token=") + GATEWAY_TOKEN;
#ifdef GATEWAY_TLS
  ws.beginSSL(GATEWAY_HOST, GATEWAY_PORT, url.c_str());
#else
  ws.begin(GATEWAY_HOST, GATEWAY_PORT, url.c_str());   // LAN-direct: plain ws
#endif
  ws.onEvent(onWsEvent);
  ws.setReconnectInterval(5000);
  // död TCP (WiFi-dropp) detekteras: ping utan pong → lib disconnect+reconnect
  ws.enableHeartbeat(10000, 5000, 2);
}

void gatewayLoop() { ws.loop(); }

void gatewayReady() {
  sessionId = "";
  RPC_ID_SESSION_CREATE = rpcId + 1;
  rpc("session.create", "{\"title\":\"pocket-alfred\"}");
}

// JSON-escape (behövs av sendPrompt/fetchSpeakMp3) — deklaration, def finns ovan
void sendPrompt(const String& text) {
  faceState = FACE_THINKING;
  captureAbort();
  String esc = jsonEscape(text);
  String p = "{\"session_id\":\"" + sessionId + "\",\"text\":\"" + esc +
             "\",\"surface\":\"voice-live\"}";
  rpc("prompt.submit", p.c_str());
}
