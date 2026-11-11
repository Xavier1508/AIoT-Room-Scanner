#include "ml_inference.h"

#include <ESP_TF.h>
#include <math.h>

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

#include "ml_model_data.h"
#include "ml_model_metadata.h"

namespace {
constexpr int kTensorArenaSize = 64 * 1024;
uint8_t gTensorArena[kTensorArenaSize];
const tflite::Model* gModel = nullptr;
tflite::MicroInterpreter* gInterpreter = nullptr;
TfLiteTensor* gInput = nullptr;
TfLiteTensor* gOutput = nullptr;

int8_t quantize(float value, float scale, int zeroPoint) {
  if (scale <= 0.0f) return 0;
  long q = lroundf(value / scale) + zeroPoint;
  if (q < -128) q = -128;
  if (q > 127) q = 127;
  return static_cast<int8_t>(q);
}
}  // namespace

bool MlClassifier::begin() {
  gModel = tflite::GetModel(g_model);
  if (gModel == nullptr || gModel->version() != TFLITE_SCHEMA_VERSION) {
    error_ = true;
    muteReason_ = "model_schema_mismatch";
    return false;
  }
  static tflite::MicroMutableOpResolver<9> resolver;
  resolver.AddExpandDims();
  resolver.AddConv2D();
  resolver.AddMul();
  resolver.AddAdd();
  resolver.AddReshape();
  resolver.AddMaxPool2D();
  resolver.AddSoftmax();
  resolver.AddFullyConnected();
  resolver.AddSqueeze();
  static tflite::MicroInterpreter interpreter(
      gModel, resolver, gTensorArena, kTensorArenaSize);
  gInterpreter = &interpreter;
  if (gInterpreter->AllocateTensors() != kTfLiteOk) {
    error_ = true;
    muteReason_ = "allocate_tensors_failed";
    return false;
  }
  gInput = gInterpreter->input(0);
  gOutput = gInterpreter->output(0);
  if (gInput == nullptr || gOutput == nullptr ||
      gInput->type != kTfLiteInt8 || gOutput->type != kTfLiteInt8 ||
      gInput->dims->size != 3 || gInput->dims->data[1] != kWindow ||
      gInput->dims->data[2] != kFeatures ||
      gOutput->dims->size != 2 || gOutput->dims->data[1] != ML_CLASSES) {
    error_ = true;
    muteReason_ = "model_shape_mismatch";
    return false;
  }
  arenaUsed_ = gInterpreter->arena_used_bytes();
  enabled_ = true;
  ready_ = true;
  muteReason_ = "waiting_for_window";
  return true;
}

void MlClassifier::reset() {
  next_ = 0;
  count_ = 0;
  windowReady_ = false;
  best_ = 0;
  confidence_ = 0.0f;
  lastFrameMs_ = 0;
  lastSampleMs_ = 0;
  label_ = "unknown";
  muteReason_ = "reset";
}

void MlClassifier::update(uint32_t now, const HlkReading& reading,
                          bool hlkValid, bool sensorsRunning, bool busy) {
  if (!ready_) {
    muteReason_ = error_ ? "not_ready" : "disabled";
    return;
  }
  if (!sensorsRunning) {
    reset();
    muteReason_ = "sensors_off";
    return;
  }
  if (busy) {
    reset();
    muteReason_ = "scan_or_motion";
    return;
  }
  if (!hlkValid || !reading.received) {
    reset();
    muteReason_ = "no_valid_hlk";
    return;
  }
  if (reading.timestampMs == lastFrameMs_) return;
  lastFrameMs_ = reading.timestampMs;
  // Match the 5 Hz dataset collection cadence even if the HLK emits faster.
  if (lastSampleMs_ && uint32_t(now - lastSampleMs_) < 180) return;
  lastSampleMs_ = now;

  const float distance = static_cast<float>(
      reading.stationaryCm ? reading.stationaryCm : reading.movingCm);
  const float energy = static_cast<float>(
      reading.movingEnergy > reading.stationaryEnergy
          ? reading.movingEnergy : reading.stationaryEnergy);
  const float target = static_cast<float>(reading.target);
  const float moving = static_cast<float>(reading.movingEnergy);
  const float stationary = static_cast<float>(reading.stationaryEnergy);
  features_[next_][0] = distance;
  features_[next_][1] = energy;
  features_[next_][2] = target;
  features_[next_][3] = moving;
  features_[next_][4] = stationary;
  features_[next_][5] = 0.0f;
  next_ = static_cast<uint8_t>((next_ + 1) % kWindow);
  if (count_ < kWindow) ++count_;
  windowReady_ = count_ >= kWindow;
  if (!windowReady_) {
    muteReason_ = "filling_window";
    return;
  }

  const float inputScale = gInput->params.scale;
  const int inputZero = gInput->params.zero_point;
  const uint8_t oldest = static_cast<uint8_t>((next_ + kWindow - count_) % kWindow);
  for (uint8_t frame = 0; frame < kWindow; ++frame) {
    const uint8_t source = static_cast<uint8_t>((oldest + frame) % kWindow);
    const uint8_t previous = frame == 0
        ? source
        : static_cast<uint8_t>((oldest + frame - 1) % kWindow);
    for (uint8_t feature = 0; feature < kFeatures; ++feature) {
      // Training resets delta_distance at the first frame of every window.
      const float value = feature == 5
          ? (frame == 0 ? 0.0f
                        : features_[source][0] - features_[previous][0])
          : features_[source][feature];
      const float normalized = (value - ML_MEAN[feature]) / ML_STD[feature];
      gInput->data.int8[frame * kFeatures + feature] =
          quantize(normalized, inputScale, inputZero);
    }
  }

  const uint32_t start = millis();
  if (gInterpreter->Invoke() != kTfLiteOk) {
    muteReason_ = "invoke_failed";
    return;
  }
  latencyMs_ = millis() - start;
  ++inferences_;
  lastInferenceMs_ = now;
  const float outputScale = gOutput->params.scale;
  const int outputZero = gOutput->params.zero_point;
  best_ = 0;
  float bestProbability = -1.0f;
  for (int index = 0; index < ML_CLASSES; ++index) {
    const float probability =
        (gOutput->data.int8[index] - outputZero) * outputScale;
    if (probability > bestProbability) {
      bestProbability = probability;
      best_ = static_cast<uint8_t>(index);
    }
  }
  confidence_ = bestProbability > 0.0f ? bestProbability : 0.0f;
  if (confidence_ > 1.0f) confidence_ = 1.0f;
  label_ = ML_LABELS[best_];
  muteReason_ = "ok";
}

String MlClassifier::statusJson() const {
  String s;
  s.reserve(420);
  s = String("{\"enabled\":") + (enabled_ ? "true" : "false") +
      ",\"ready\":" + (ready_ ? "true" : "false") +
      ",\"error\":" + (error_ ? "true" : "false") +
      ",\"model_version\":\"" + ML_MODEL_VERSION + "\"" +
      ",\"window\":" + static_cast<int>(kWindow) +
      ",\"features\":" + static_cast<int>(kFeatures) +
      ",\"classes\":" + static_cast<int>(ML_CLASSES) +
      ",\"window_ready\":" + (windowReady_ ? "true" : "false") +
      ",\"class\":\"" + label_ + "\"" +
      ",\"confidence\":" + String(confidence_, 3) +
      ",\"latency_ms\":" + latencyMs_ +
      ",\"inferences\":" + inferences_ +
      ",\"last_inference_ms\":" + lastInferenceMs_ +
      ",\"arena_used_bytes\":" + arenaUsed_ +
      ",\"mute_reason\":\"" + muteReason_ + "\"}";
  return s;
}
