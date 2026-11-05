#pragma once

#include <stddef.h>
#include <stdint.h>

struct WifiNetwork {
  char ssid[33] = {};
  uint8_t length = 0, channel = 0, auth = 0;
  int32_t rssi = -127;
};

// Bounded, portable data model. No radio calls and no credentials.
class WifiScanList {
 public:
  static constexpr size_t capacity = 48;
  static constexpr size_t pageSize = 6;
  void clear();
  void add(const char* ssid, size_t length, int32_t rssi, uint8_t channel, uint8_t auth);
  void sortBySignal();
  const WifiNetwork* at(size_t index) const { return index < count_ ? &networks_[index] : nullptr; }
  size_t count() const { return count_; }
  size_t hidden() const { return hidden_; }
  bool truncated() const { return truncated_; }
  static void hexSsid(const WifiNetwork& network, char (&out)[65]);
 private:
  WifiNetwork networks_[capacity];
  size_t count_ = 0, hidden_ = 0;
  bool truncated_ = false;
};
