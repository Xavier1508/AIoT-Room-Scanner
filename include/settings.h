#pragma once

#include <Arduino.h>

struct DeviceSettings {
  uint32_t magic = 0;
  uint32_t schema = 1;
  char ssid[33] = {};
  char wifiPassword[64] = {};
  char webPassword[65] = {};
};

class SettingsStore {
 public:
  bool load();
  bool provision(char* line);  // Modifies/wipes input; never logs credentials.
  bool configured() const { return configured_; }
  const DeviceSettings& value() const { return value_; }
 private:
  bool configured_ = false;
  DeviceSettings value_;
};
