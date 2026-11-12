#pragma once

#include <Arduino.h>
#include "hlk_protocol.h"

// HLK-LD2410C 1D-CNN classifier (empty/human) running on TFLite Micro.
// The rule-based HLK presence/buzzer path remains the safety fallback; this
// module only publishes a classifier result for the dashboard.
class MlClassifier {
 public:
  bool begin();
  void reset();
  void update(uint32_t now, const HlkReading& reading, bool hlkValid,
              bool sensorsRunning, bool busy);
  String statusJson() const;
  bool ready() const { return ready_; }
  bool windowReady() const { return windowReady_; }
  const String& label() const { return label_; }
  float confidence() const { return confidence_; }
  uint32_t inferences() const { return inferences_; }

 private:
  static constexpr uint8_t kWindow = 32;
  static constexpr uint8_t kFeatures = 6;
  bool ready_ = false;
  bool enabled_ = false;
  bool windowReady_ = false;
  bool error_ = false;
  uint8_t next_ = 0;
  uint8_t count_ = 0;
  uint8_t best_ = 0;
  float confidence_ = 0.0f;
  float features_[kWindow][kFeatures] = {};
  uint32_t lastFrameMs_ = 0;
  uint32_t lastSampleMs_ = 0;
  uint32_t lastInferenceMs_ = 0;
  uint32_t inferences_ = 0;
  uint32_t latencyMs_ = 0;
  uint32_t arenaUsed_ = 0;
  String label_ = "unknown";
  String muteReason_ = "init";
};
