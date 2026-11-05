#include "actuators.h"
#include "config.h"
#include "pins.h"

void StepperController::begin() {
  for (auto pin : pins::stepper) { digitalWrite(pin, LOW); pinMode(pin, OUTPUT); }
  stop();
}
bool StepperController::start(uint32_t nowUs) {
  if (position_ + config::stepCount > config::relativeStepLimit ||
      position_ < -config::relativeStepLimit) return false;
  completed_ = 0; active_ = true; nextUs_ = nowUs + config::stepIntervalUs;
  return true;
}
void StepperController::tick(uint32_t nowUs) {
  if (!active_ || int32_t(nowUs - nextUs_) < 0) return;
  if (uint32_t(nowUs - nextUs_) > config::stepIntervalUs) ++late_;
  // Bit 0..3 = IN1..IN4. No AccelStepper constructor reordering involved.
  static const uint8_t halfSteps[] = {1, 3, 2, 6, 4, 12, 8, 9};
  const int direction = completed_ < config::stepCount ? 1 : -1;
  phase_ = (phase_ + direction + 8) % 8;
  for (unsigned i = 0; i < 4; ++i) {
    digitalWrite(pins::stepper[i], (halfSteps[phase_] >> i) & 1);
  }
  energized_ = true; position_ += direction; ++completed_;
  nextUs_ = nowUs + config::stepIntervalUs;
  if (completed_ == 2 * config::stepCount) stop();
}
void StepperController::stop() {
  for (auto pin : pins::stepper) digitalWrite(pin, LOW);
  active_ = energized_ = false;
}
