#include "actuators.h"
#include "pins.h"
#include <esp_arduino_version.h>

#if ESP_ARDUINO_VERSION_MAJOR != 2
#error "Servo LEDC implementation is pinned to Arduino-ESP32 2.x; review for 3.x."
#endif

void ServoController::begin() {
  digitalWrite(pins::servo, LOW); pinMode(pins::servo, OUTPUT); active_ = false;
}
void ServoController::pulse(uint16_t us) {
  pulseUs_ = us;
  ledcWrite(0, (uint32_t(us) * 65535u + 10000u) / 20000u);
}
bool ServoController::start(uint32_t now) {
  if (ledcSetup(0, 50, 16) == 0) return false;
  // Load neutral duty BEFORE routing the peripheral onto the pin.
  pulse(1500); ledcAttachPin(pins::servo, 0);
  active_ = true; index_ = 0; at_ = now; return true;
}
void ServoController::tick(uint32_t now) {
  static const uint16_t pulses[] = {1500, 1450, 1500, 1550, 1500};
  if (!active_ || uint32_t(now - at_) < 700) return;
  if (++index_ >= sizeof(pulses) / sizeof(pulses[0])) { stop(); return; }
  pulse(pulses[index_]); at_ = now;
}
void ServoController::stop() {
  if (active_) { ledcDetachPin(pins::servo); ledcWrite(0, 0); }
  digitalWrite(pins::servo, LOW); pinMode(pins::servo, OUTPUT);
  active_ = false; pulseUs_ = 0;
}
