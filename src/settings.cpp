#include "settings.h"
#include <Preferences.h>
#include <string.h>
#include "config.h"

namespace {
constexpr uint32_t magic = 0x41494f54;
constexpr uint8_t poseServoSchema = 4;  // 0.3.0 records the corrected user-confirmed 800 us zero.
void wipe(void* pointer, size_t size) {
  volatile uint8_t* p = static_cast<volatile uint8_t*>(pointer);
  while (size--) *p++ = 0;
}
int nibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}
bool decode(const char* text, char* out, size_t capacity) {
  size_t n = strlen(text);
  if ((n & 1) || n / 2 >= capacity) return false;
  for (size_t i = 0; i < n; i += 2) {
    int hi = nibble(text[i]), lo = nibble(text[i+1]);
    if (hi < 0 || lo < 0 || (hi == 0 && lo == 0)) return false;
    out[i/2] = char((hi << 4) | lo);
  }
  out[n/2] = 0;
  return true;
}
bool valid(const DeviceSettings& s) {
  if (s.magic != magic || s.schema != 1 ||
      !memchr(s.ssid, 0, sizeof(s.ssid)) ||
      !memchr(s.wifiPassword, 0, sizeof(s.wifiPassword)) ||
      !memchr(s.webPassword, 0, sizeof(s.webPassword))) return false;
  size_t ssid = strlen(s.ssid), wifi = strlen(s.wifiPassword), web = strlen(s.webPassword);
  if (ssid == 0 || ssid > 32 || (wifi != 0 && (wifi < 8 || wifi > 63)) ||
      web < 16 || web > 64 || strcmp(s.wifiPassword, s.webPassword) == 0) return false;
  for (size_t i = 0; i < web; ++i) {
    if (uint8_t(s.webPassword[i]) < 33 || uint8_t(s.webPassword[i]) > 126) return false;
  }
  return true;
}
}

bool SettingsStore::load() {
  configured_ = false;
  Preferences preferences;
  if (!preferences.begin("aiot-bringup", true)) return false;
  bool ok = preferences.getBytesLength("config") == sizeof(value_) &&
            preferences.getBytes("config", &value_, sizeof(value_)) == sizeof(value_);
  preferences.end();
  configured_ = ok && valid(value_);
  if (!configured_) wipe(&value_, sizeof(value_));
  return configured_;
}

bool SettingsStore::loadPose(PoseSettings& pose) {
  pose = PoseSettings{};
  Preferences preferences;
  if (!preferences.begin("aiot-pose", true)) return false;
  if (preferences.getUChar("schema", 0) != 1) {
    preferences.end(); return false;
  }
  if (preferences.isKey("step_ref")) {
    const int32_t value = preferences.getInt("step_ref", 0);
    if (value >= -config::longRelativeStepLimit && value <= config::longRelativeStepLimit) {
      pose.stepperReferenceHalfSteps = value; pose.stepperReferenceValid = true;
    }
  }
  if (preferences.getUChar("servo_rev", 0) == poseServoSchema && preferences.isKey("servo_us")) {
    const uint16_t value = preferences.getUShort("servo_us", config::servoParkPulseUs);
    if (value >= config::servoMinPulseUs && value <= config::servoMaxPulseUs) {
      pose.servoParkPulseUs = value; pose.servoParkPulseValid = true;
    }
  }
  preferences.end();
  return pose.stepperReferenceValid || pose.servoParkPulseValid;
}

bool SettingsStore::saveStepperReference(int32_t halfSteps) {
  if (halfSteps < -config::longRelativeStepLimit || halfSteps > config::longRelativeStepLimit) return false;
  Preferences preferences;
  if (!preferences.begin("aiot-pose", false)) return false;
  const bool ok = preferences.putUChar("schema", 1) == 1 &&
                  preferences.putInt("step_ref", halfSteps) == sizeof(halfSteps);
  preferences.end();
  return ok;
}

bool SettingsStore::saveServoParkPulse(uint16_t pulseUs) {
  if (pulseUs < config::servoMinPulseUs || pulseUs > config::servoMaxPulseUs) return false;
  Preferences preferences;
  if (!preferences.begin("aiot-pose", false)) return false;
  const bool ok = preferences.putUChar("schema", 1) == 1 &&
                  preferences.putUChar("servo_rev", poseServoSchema) == 1 &&
                  preferences.putUShort("servo_us", pulseUs) == sizeof(pulseUs);
  preferences.end();
  return ok;
}

bool SettingsStore::provision(char* line) {
  // A single NVS blob update, preserving the previous config on parse failure.
  DeviceSettings candidate;
  candidate.magic = magic;
  char* parts[4] = {};
  parts[0] = line;
  unsigned count = 1;
  for (char* p = line; *p; ++p) {
    if (*p == '\t') {
      if (count == 4) { wipe(&candidate, sizeof(candidate)); return false; }
      *p = 0; parts[count++] = p + 1;
    }
  }
  bool ok = count == 4 && strcmp(parts[0], "provision") == 0 &&
      decode(parts[1], candidate.ssid, sizeof(candidate.ssid)) &&
      decode(parts[2], candidate.wifiPassword, sizeof(candidate.wifiPassword)) &&
      decode(parts[3], candidate.webPassword, sizeof(candidate.webPassword)) && valid(candidate);
  if (ok) {
    Preferences preferences;
    ok = preferences.begin("aiot-bringup", false);
    if (ok) {
      ok = preferences.putBytes("config", &candidate, sizeof(candidate)) == sizeof(candidate);
      preferences.end();
    }
  }
  if (ok) { value_ = candidate; configured_ = true; }
  wipe(&candidate, sizeof(candidate));
  return ok;
}
