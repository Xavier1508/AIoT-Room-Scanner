#pragma once

#include <Arduino.h>

class BuzzerController {
 public:
  void begin();
  void start(uint32_t now);
  void tick(uint32_t now);
  void stop();
  bool active() const { return active_; }
  bool sounding() const { return sounding_; }
 private:
  bool active_ = false, sounding_ = false;
  uint8_t pulses_ = 0;
  uint32_t at_ = 0;
};

class StepperController {
 public:
  void begin();
  bool start(uint32_t nowUs, int halfSteps);
  bool startPark(uint32_t nowUs, int halfSteps, int direction);
  void holdCurrent();
  void setRelativeSteps(int halfSteps) { if (!active_) position_ = halfSteps; }
  void tick(uint32_t nowUs);
  void stop();
  bool active() const { return active_; }
  bool energized() const { return energized_; }
  int relativeSteps() const { return position_; }
  uint32_t schedulingLate() const { return late_; }
 private:
  bool active_ = false, energized_ = false;
  int position_ = 0, completed_ = 0, target_ = 0, direction_ = 1, phase_ = 0;
  bool returnMove_ = true, holdAtEnd_ = false;
  uint32_t nextUs_ = 0, late_ = 0;
};

class ServoController {
 public:
  void begin();
  bool start(uint32_t now, bool longTest);
  bool holdAt(uint32_t now, uint16_t pulseUs);
  void tick(uint32_t now);
  void stop();
  bool active() const { return active_; }
  bool attached() const { return attached_; }
  uint16_t pulseUs() const { return pulseUs_; }
 private:
  void pulse(uint16_t us);
  bool active_ = false, attached_ = false;
  uint8_t index_ = 0;
  bool longTest_ = false;
  uint16_t pulseUs_ = 0;
  uint32_t at_ = 0;
};
