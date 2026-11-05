#include "hlk_protocol.h"

#include <string.h>
#include "config.h"

namespace {
constexpr uint8_t header[] = {0xf4, 0xf3, 0xf2, 0xf1};
constexpr uint8_t footer[] = {0xf8, 0xf7, 0xf6, 0xf5};
uint16_t le16(const uint8_t* p) { return p[0] | (uint16_t(p[1]) << 8); }
}

void HlkParser::reset() {
  used_ = expected_ = 0;
  reading_ = HlkReading{};
}

void HlkParser::expire(uint32_t now) {
  if (used_ && uint32_t(now - lastByteMs_) > config::frameTimeoutMs) {
    ++timeouts_; used_ = expected_ = 0;
  }
}

// Drop only one byte; feed() then rechecks any embedded/partial header.
void HlkParser::resync() {
  if (used_) { --used_; memmove(buffer_, buffer_ + 1, used_); }
  expected_ = 0;
}

bool HlkParser::feed(uint8_t byte, uint32_t now) {
  expire(now);
  lastByteMs_ = now;
  if (used_ >= sizeof(buffer_)) { ++rejected_; resync(); }
  buffer_[used_++] = byte;
  bool accepted = false;
  while (used_) {
    const size_t prefix = used_ < sizeof(header) ? used_ : sizeof(header);
    if (memcmp(buffer_, header, prefix) != 0) { resync(); continue; }
    if (used_ < 6) break;
    const size_t payload = le16(buffer_ + 4);
    if (payload < 13 || payload + 10 > sizeof(buffer_)) {
      ++rejected_; resync(); continue;
    }
    expected_ = payload + 10;
    if (used_ < expected_) break;
    if (decode(now)) {
      ++valid_; accepted = true;
      used_ -= expected_;
      memmove(buffer_, buffer_ + expected_, used_); expected_ = 0;
    } else {
      ++rejected_; resync();
    }
  }
  return accepted;
}

bool HlkParser::decode(uint32_t now) {
  const size_t payload = expected_ - 10;
  const uint8_t* p = buffer_ + 6;
  if (memcmp(buffer_ + 6 + payload, footer, 4) != 0 ||
      p[1] != 0xaa || p[payload - 2] != 0x55 || p[payload - 1] != 0 ||
      p[2] > 3 || p[5] > 100 || p[8] > 100) return false;
  // Basic payload is exactly 13 bytes. Engineering variants add gate data.
  if (!((p[0] == 2 && payload == 13) ||
        (p[0] == 1 && payload >= 33 && payload <= 64))) return false;
  HlkReading next;
  next.received = true; next.timestampMs = now;
  next.target = p[2]; next.movingCm = le16(p + 3);
  next.movingEnergy = p[5]; next.stationaryCm = le16(p + 6);
  next.stationaryEnergy = p[8]; next.detectionCm = le16(p + 9);
  next.engineering = p[0] == 1;
  reading_ = next;
  return true;
}
