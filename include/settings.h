#pragma once

#include <Arduino.h>
#include <stdint.h>

struct DeviceSettings {
  uint32_t magic = 0;
  uint32_t schema = 1;
  char ssid[33] = {};
  char wifiPassword[64] = {};
  char webPassword[65] = {};
};

struct PoseSettings {
  bool stepperReferenceValid = false;
  int32_t stepperReferenceHalfSteps = 0;
  bool servoParkPulseValid = false;
  uint16_t servoParkPulseUs = 2000;
};

class SettingsStore {
 public:
  bool load();
  bool loadPose(PoseSettings& pose);
  bool saveStepperReference(int32_t halfSteps);
  bool saveServoParkPulse(uint16_t pulseUs);
  bool provision(char* line);  // Modifies/wipes input; never logs credentials.
  bool configured() const { return configured_; }
  const DeviceSettings& value() const { return value_; }
 private:
  bool configured_ = false;
  DeviceSettings value_;
};
