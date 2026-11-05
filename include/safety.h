#pragma once

#include <stdint.h>
#include "config.h"

enum class Mode { Idle, Buzzer, Stepper, Servo, Ota };

// Pure state only. No persistent arm flags; shared by host tests and firmware.
class SafetyState {
 public:
  Mode mode() const { return mode_; }
  bool motorArmed() const { return motorArmed_; }
  bool servoArmed() const { return servoArmed_; }
  bool idle() const { return mode_ == Mode::Idle; }
  bool armMotor(uint32_t now) {
    if (!idle()) return false;
    motorArmed_ = true; motorAt_ = now; return true;
  }
  bool armServo(uint32_t now) {
    if (!idle()) return false;
    servoArmed_ = true; servoAt_ = now; return true;
  }
  bool start(Mode next, uint32_t now) {
    expire(now);
    if (!idle() || next == Mode::Idle || next == Mode::Ota) return false;
    if (next == Mode::Stepper && !motorArmed_) return false;
    if (next == Mode::Servo && !servoArmed_) return false;
    motorArmed_ = servoArmed_ = false;  // A test consumes all arms.
    mode_ = next; startedAt_ = now; return true;
  }
  void stop() { mode_ = Mode::Idle; motorArmed_ = servoArmed_ = false; }
  void ota() { stop(); mode_ = Mode::Ota; }
  void expire(uint32_t now) {
    if (static_cast<uint32_t>(now - motorAt_) >= config::armTimeoutMs) motorArmed_ = false;
    if (static_cast<uint32_t>(now - servoAt_) >= config::armTimeoutMs) servoArmed_ = false;
  }
  bool overdue(uint32_t now) const {
    return mode_ != Mode::Idle && mode_ != Mode::Ota &&
           static_cast<uint32_t>(now - startedAt_) >= config::testTimeoutMs;
  }
 private:
  Mode mode_ = Mode::Idle;
  bool motorArmed_ = false, servoArmed_ = false;
  uint32_t motorAt_ = 0, servoAt_ = 0, startedAt_ = 0;
};

inline const char* modeName(Mode mode) {
  switch (mode) {
    case Mode::Buzzer: return "BUZZER_TEST";
    case Mode::Stepper: return "STEPPER_TEST";
    case Mode::Servo: return "SERVO_TEST";
    case Mode::Ota: return "OTA";
    default: return "IDLE";
  }
}
