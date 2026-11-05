#include "wifi_scan.h"

#include <algorithm>
#include <string.h>

void WifiScanList::clear() { count_ = hidden_ = 0; truncated_ = false; }

void WifiScanList::add(const char* ssid, size_t length, int32_t rssi, uint8_t channel, uint8_t auth) {
  if (length == 0) { ++hidden_; return; }
  if (!ssid || length > 32 || memchr(ssid, 0, length)) return;
  for (size_t i = 0; i < count_; ++i) {
    auto& old = networks_[i];
    if (old.length == length && old.auth == auth && memcmp(old.ssid, ssid, length) == 0) {
      if (rssi > old.rssi) { old.rssi = rssi; old.channel = channel; }
      return;
    }
  }
  size_t index = count_;
  if (count_ == capacity) {
    truncated_ = true;
    index = 0;
    for (size_t i = 1; i < count_; ++i) if (networks_[i].rssi < networks_[index].rssi) index = i;
    if (rssi <= networks_[index].rssi) return;
  } else ++count_;
  auto& next = networks_[index];
  memcpy(next.ssid, ssid, length); next.ssid[length] = 0;
  next.length = uint8_t(length); next.rssi = rssi; next.channel = channel; next.auth = auth;
}

void WifiScanList::sortBySignal() {
  std::sort(networks_, networks_ + count_, [](const WifiNetwork& a, const WifiNetwork& b) { return a.rssi > b.rssi; });
}

void WifiScanList::hexSsid(const WifiNetwork& network, char (&out)[65]) {
  static const char digits[] = "0123456789abcdef";
  for (size_t i = 0; i < network.length; ++i) {
    uint8_t byte = uint8_t(network.ssid[i]);
    out[2*i] = digits[byte >> 4]; out[2*i+1] = digits[byte & 15];
  }
  out[2*network.length] = 0;
}
