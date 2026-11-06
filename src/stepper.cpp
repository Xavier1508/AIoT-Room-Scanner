#include "actuators.h"
#include "config.h"
#include "pins.h"

void StepperController::begin() {
  for (auto pin : pins::stepper) { digitalWrite(pin, LOW); pinMode(pin, OUTPUT); }
  stop();
}
bool StepperController::start(uint32_t nowUs, int halfSteps) {
  const int limit = halfSteps > config::stepCount ? config::longRelativeStepLimit : config::relativeStepLimit;
  if (halfSteps <= 0 || position_ + halfSteps > limit || position_ < -limit) return false;
  completed_ = 0; target_ = halfSteps; direction_ = 1; returnMove_ = true;
  holdAtEnd_ = false; active_ = true; nextUs_ = nowUs + config::stepIntervalUs;
  return true;
}
bool StepperController::startPark(uint32_t nowUs, int halfSteps, int direction) {
  if (halfSteps <= 0 || (direction != 1 && direction != -1) ||
      position_ + direction * halfSteps > config::longRelativeStepLimit ||
      position_ + direction * halfSteps < -config::longRelativeStepLimit) return false;
  completed_ = 0; target_ = halfSteps; direction_ = direction; returnMove_ = false;
  holdAtEnd_ = true; active_ = true; nextUs_ = nowUs + config::stepIntervalUs;
  return true;
}
void StepperController::tick(uint32_t nowUs) {
  if (!active_ || int32_t(nowUs - nextUs_) < 0) return;
  if (uint32_t(nowUs - nextUs_) > config::stepIntervalUs) ++late_;
  // Bit 0..3 = IN1..IN4. No AccelStepper constructor reordering involved.
  static const uint8_t halfSteps[] = {1, 3, 2, 6, 4, 12, 8, 9};
  const int direction = returnMove_ ? (completed_ < target_ ? direction_ : -direction_) : direction_;
  phase_ = (phase_ + direction + 8) % 8;
  for (unsigned i = 0; i < 4; ++i) {
    digitalWrite(pins::stepper[i], (halfSteps[phase_] >> i) & 1);
  }
  energized_ = true; position_ += direction; ++completed_;
  nextUs_ = nowUs + config::stepIntervalUs;
  if (completed_ == (returnMove_ ? 2 * target_ : target_)) {
    active_ = false;
    if (!holdAtEnd_) stop();
  }
}
void StepperController::stop() {
  for (auto pin : pins::stepper) digitalWrite(pin, LOW);
  active_ = energized_ = false;
}
