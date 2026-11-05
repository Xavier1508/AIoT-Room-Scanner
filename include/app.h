#pragma once

#include <Arduino.h>
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include "actuators.h"
#include "commands.h"
#include "console.h"
#include "hlk_protocol.h"
#include "network.h"
#include "safety.h"
#include "settings.h"

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
  Console console_;
  SettingsStore settings_;
  Network network_;
  SafetyState safety_;
  BuzzerController buzzer_;
  StepperController stepper_;
  ServoController servo_;
  HardwareSerial hlkSerial_{1};
  HlkParser hlk_;
  bool hlkEnabled_ = false, wifiWasConnected_ = false;
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
