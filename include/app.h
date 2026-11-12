#pragma once

#include <Arduino.h>
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include "actuators.h"
#include "config.h"
#include "commands.h"
#include "console.h"
#include "hlk_protocol.h"
#include "ml_inference.h"
#include "network.h"
#include "safety.h"
#include "settings.h"
#include "sensors.h"

String jsonQuote(const String& value);

struct CommandRequest {
  Command command;
  uint32_t id;
  uint32_t queuedAt;
};

class App {
 public:
  void begin();
  void tick();
  String execute(Command command);
  String serialLine(char* line);
  String statusJson();
  bool enqueue(Command command, uint32_t& id);
  void requestStop();
  bool beginOta();
  void finishOta(bool success, const char* detail);
  bool otaActive() const { return otaActive_.load(); }
 private:
  void stopAll();
  void publish(uint32_t now);
  void event(const char* text);
  void clearQueue();
  bool beginPose(uint32_t now);
  void syncPoseMode(uint32_t now);
  void releaseStepper();
  void releaseServo();
  void maybeHlkAlert(uint32_t now);
  void updateMlGate();
  Console console_;
  SettingsStore settings_;
  Network network_;
  SafetyState safety_;
  BuzzerController buzzer_;
  StepperController stepper_;
  ServoController servo_;
  SensorController sensors_;
  MlClassifier ml_;
  HardwareSerial hlkSerial_{1};
  HlkParser hlk_;
  bool hlkEnabled_ = false, wifiWasConnected_ = false;
  bool stepperHolding_ = false, servoHolding_ = false, stepperMovePending_ = false;
  bool scanMode_ = false, hlkAlertEnabled_ = false, mlAlertEnabled_ = false;
  bool stepperReferencePersisted_ = false;
  bool servoBasePersisted_ = false;
  bool hlkAlertActive_ = false;
  uint8_t hlkAlertConfirm_ = 0;
  uint32_t hlkAlertNextMs_ = 0, hlkAlertCount_ = 0, lastMotionMs_ = 0;
  uint32_t hlkAlertLastFrameMs_ = 0;
  uint16_t hlkAlertLastDistanceCm_ = 0, hlkAlertIntervalMs_ = 0;
  uint8_t hlkAlertLastEnergy_ = 0;
  String hlkAlertMuteReason_ = "idle";
  bool mlAlertActive_ = false;
  uint16_t mlAlertRawCm_ = 0;
  uint16_t mlAlertIntervalMs_ = 0;
  float mlAlertDistanceCm_ = 0.0f;
  uint8_t mlAlertZone_ = 0;
  uint16_t hlkDistanceHistory_[3] = {};
  uint8_t hlkDistanceCount_ = 0;
  uint8_t hlkDistanceIndex_ = 0;
  uint32_t hlkDistanceLastFrameMs_ = 0;
  uint32_t hlkAlertLastMlInferences_ = 0;
  float hlkDistanceFiltered_ = 0.0f;
  bool mlGate_ = false;
  uint8_t mlGateConfirm_ = 0, mlGateRelease_ = 0;
  String mlAlertMuteReason_ = "disabled";
  String poseReferenceSource_ = "migration_default_1024";
  String servoBaseSource_ = "default_800";
  uint16_t servoBaseUs_ = config::servoParkPulseUs;
  uint16_t servoTargetUs_ = config::servoParkPulseUs;
  uint32_t hlkBytes_ = 0, lastPublish_ = 0, maxLoopUs_ = 0;
  uint32_t bootReason_ = 0, lastCommandId_ = 0;
  String lastResult_ = "{}", snapshot_ = "{}";
  String events_[8];
  unsigned eventIndex_ = 0;
  QueueHandle_t commands_ = nullptr;
  SemaphoreHandle_t snapshotMutex_ = nullptr;
  std::atomic<uint32_t> nextId_{1}, rebootAt_{0};
  std::atomic<bool> stopRequested_{false}, otaActive_{false}, otaSafe_{false};
  std::atomic<bool> otaFinished_{false}, otaSucceeded_{false};
};
