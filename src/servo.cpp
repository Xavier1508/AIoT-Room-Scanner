#include "actuators.h"
#include "pins.h"
#include <esp_arduino_version.h>

#if ESP_ARDUINO_VERSION_MAJOR != 2
#error "Servo LEDC implementation is pinned to Arduino-ESP32 2.x; review for 3.x."
#endif

// ESP32-S3 LEDC in the pinned Arduino/IDF package supports at most 14 bits.
// Requesting 16 bits makes ledcSetup() fail before any servo pulse is routed.
constexpr uint8_t servoResolutionBits = 14;
constexpr uint32_t servoDutyMax = (1u << servoResolutionBits) - 1u;

void ServoController::begin() {
  digitalWrite(pins::servo, LOW); pinMode(pins::servo, OUTPUT); active_ = false; attached_ = false;
}
void ServoController::pulse(uint16_t us) {
  pulseUs_ = us;
  ledcWrite(0, (uint32_t(us) * servoDutyMax + 10000u) / 20000u);
}
bool ServoController::start(uint32_t now, bool longTest) {
  if (ledcSetup(0, 50, servoResolutionBits) == 0) return false;
  // Load neutral duty BEFORE routing the peripheral onto the pin.
  pulse(1500); ledcAttachPin(pins::servo, 0);
  active_ = true; attached_ = true; longTest_ = longTest; sequence_ = 0; index_ = 0; at_ = now; return true;
}
bool ServoController::startNudge(uint32_t now, bool positive) {
  if (ledcSetup(0, 50, servoResolutionBits) == 0) return false;
  pulse(1500); ledcAttachPin(pins::servo, 0);
  active_ = true; attached_ = true; longTest_ = false; sequence_ = positive ? 1 : 2; index_ = 0; at_ = now; return true;
}
bool ServoController::holdAt(uint32_t, uint16_t pulseUs) {
  if (ledcSetup(0, 50, servoResolutionBits) == 0) return false;
  pulse(pulseUs); ledcAttachPin(pins::servo, 0);
  active_ = false; attached_ = true; longTest_ = false; return true;
}
void ServoController::tick(uint32_t now) {
  static const uint16_t pulses[] = {1500, 1450, 1500, 1550, 1500};
  static const uint16_t positiveNudge[] = {1500, 1550, 1500};
  static const uint16_t negativeNudge[] = {1500, 1450, 1500};
  static const uint16_t longPulses[] = {
      1500, 1450, 1500, 1550, 1500, 1450, 1500,
      1550, 1500, 1450, 1500, 1550, 1500};
  if (!active_ || uint32_t(now - at_) < 700) return;
  const uint16_t* sequence = longTest_ ? longPulses : (sequence_ == 1 ? positiveNudge : (sequence_ == 2 ? negativeNudge : pulses));
  const size_t length = longTest_ ? sizeof(longPulses) / sizeof(longPulses[0]) : (sequence_ == 0 ? sizeof(pulses) / sizeof(pulses[0]) : 3);
  if (++index_ >= length) { stop(); return; }
  pulse(sequence[index_]); at_ = now;
}
void ServoController::stop() {
  if (attached_) { ledcDetachPin(pins::servo); ledcWrite(0, 0); }
  digitalWrite(pins::servo, LOW); pinMode(pins::servo, OUTPUT);
  active_ = false; attached_ = false; pulseUs_ = 0;
  longTest_ = false; sequence_ = 0;
}
