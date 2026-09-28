#pragma once
#include <M5Unified.h>
#include "AudioTools.h"
#include "AudioTools/AudioCodecs/CodecMP3Helix.h"
#include "screens.h"   // FaceState

// MP3 → I2S via audio-tools + libhelix (Core2: NS4150-amp på GPIO12/0/2).

I2SStream i2s;
bool speakerStarted = false;

bool initSpeaker() {
  if (speakerStarted) return true;
  auto cfg = i2s.defaultConfig(TX_MODE);
  cfg.pin_bck = 12;                // Core2 SPK-pinout: BCK GPIO12
  cfg.pin_ws = 0;                  // LRCK GPIO0
  cfg.pin_data = 2;                // DATA GPIO2
  cfg.i2s_format = I2S_STD_FORMAT;
  if (!i2s.begin(cfg)) return false;
  speakerStarted = true;
  return true;
}

// Spela en komplett MP3-buffer blockande (anropas från loop-tråden).
bool playMp3(const uint8_t* mp3, size_t len) {
  if (!mp3 || !len || !initSpeaker()) return false;
  faceState = FACE_SPEAKING;
  MemoryStream in(mp3, len);
  EncodedAudioStream dec(&in, new MP3DecoderHelix());  // decoder → i2s
  StreamCopy copier(dec, in);                          // mp3 → decoder → i2s
  dec.begin();
  while (true) {
    size_t n = copier.copy();
    if (n == 0) break;
    M5.update();                   // håll touch vid liv grovt
  }
  dec.end();
  faceState = FACE_IDLE;
  return true;
}
