#include "actuators.h"
#include "pins.h"

void BuzzerController::begin() {
  digitalWrite(pins::buzzer, HIGH); pinMode(pins::buzzer, OUTPUT); stop();
}
void BuzzerController::start(uint32_t now) {
  active_ = sounding_ = true; pulses_ = 1; at_ = now;
  digitalWrite(pins::buzzer, LOW);
}
void BuzzerController::tick(uint32_t now) {
  if (!active_) return;
  if (sounding_ && uint32_t(now - at_) >= 150) {
    digitalWrite(pins::buzzer, HIGH); sounding_ = false; at_ = now;
    if (pulses_ == 3) stop();
  } else if (!sounding_ && uint32_t(now - at_) >= 350) {
    ++pulses_; sounding_ = true; at_ = now; digitalWrite(pins::buzzer, LOW);
  }
}
void BuzzerController::stop() {
  digitalWrite(pins::buzzer, HIGH); active_ = sounding_ = false;
}
