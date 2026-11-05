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
  bool start(uint32_t nowUs);
  void tick(uint32_t nowUs);
  void stop();
  bool active() const { return active_; }
  bool energized() const { return energized_; }
  int relativeSteps() const { return position_; }
  uint32_t schedulingLate() const { return late_; }
 private:
  bool active_ = false, energized_ = false;
  int position_ = 0, completed_ = 0, phase_ = 0;
  uint32_t nextUs_ = 0, late_ = 0;
};

class ServoController {
 public:
  void begin();
  bool start(uint32_t now);
  void tick(uint32_t now);
  void stop();
  bool active() const { return active_; }
  uint16_t pulseUs() const { return pulseUs_; }
 private:
  void pulse(uint16_t us);
  bool active_ = false;
  uint8_t index_ = 0;
  uint16_t pulseUs_ = 0;
  uint32_t at_ = 0;
};
