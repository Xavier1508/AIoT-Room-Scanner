#pragma once

#include <Arduino.h>

class App;

class Console {
 public:
  void begin(App& app);
  void tick();
  void send(const String& json);
  bool ready() const { return ready_; }
 private:
  App* app_ = nullptr;
  char input_[512] = {};
  size_t used_ = 0, sent_ = 0;
  bool overflow_ = false;
  bool ready_ = false;
  String output_;
};
