#pragma once
#include <M5Unified.h>

// Mikrofonbuffring med enkel amplitud-VAD.
// 100 ms-chunk = 1600 samples @ 16 kHz. Buffrar upp till ~10 s i PSRAM.
struct Capture {
  static constexpr int RATE = 16000;
  static constexpr int CHUNK = 1600;        // 100 ms
  static constexpr int MAX_CHUNKS = 100;    // 10 s hårt tak

  int16_t* pcm = nullptr;          // MAX_CHUNKS * CHUNK samples (PSRAM)
  size_t   frames = 0;
  int      silenceRun = 0;
  bool     heardSpeech = false;
  bool     active = false;

  void begin() {
    frames = 0; silenceRun = 0; heardSpeech = false;
    if (!pcm) pcm = (int16_t*)heap_caps_malloc(MAX_CHUNKS * CHUNK * 2, MALLOC_CAP_SPIRAM);
    M5.Mic.begin();
    M5.Mic.setSampleRate(RATE);
  }
  void end() { M5.Mic.end(); }

  // true = uttalande klart (tystnad efter tal ELLER hårt tak); false = fortsätt
  bool chunk() {
    if (!pcm) return true;
    int16_t buf[CHUNK];
    M5.Mic.record(buf, CHUNK, RATE);
    int32_t acc = 0;
    for (int i = 0; i < CHUNK; i += 8) acc += abs(buf[i]);
    int level = acc / 200;
    if (level > 90) { heardSpeech = true; silenceRun = 0; }
    else if (heardSpeech && ++silenceRun >= 12) return true;  // 1.2 s tystnad
    if (frames < MAX_CHUNKS) memcpy(pcm + frames * CHUNK, buf, sizeof(buf));
    frames++;
    return frames >= MAX_CHUNKS;
  }

  size_t totalSamples() const { return frames * CHUNK; }
};
