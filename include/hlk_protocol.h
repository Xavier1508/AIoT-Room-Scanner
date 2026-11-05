#pragma once

#include <stddef.h>
#include <stdint.h>

struct HlkReading {
  bool received = false;
  uint32_t timestampMs = 0;
  uint8_t target = 0, movingEnergy = 0, stationaryEnergy = 0;
  uint16_t movingCm = 0, stationaryCm = 0, detectionCm = 0;
  bool engineering = false;
};

class HlkParser {
 public:
  bool feed(uint8_t byte, uint32_t now);
  void expire(uint32_t now);
  void reset();
  const HlkReading& reading() const { return reading_; }
  uint32_t validFrames() const { return valid_; }
  uint32_t rejectedFrames() const { return rejected_; }
  uint32_t partialTimeouts() const { return timeouts_; }
 private:
  bool decode(uint32_t now);
  void resync();
  uint8_t buffer_[96] = {};
  size_t used_ = 0, expected_ = 0;
  uint32_t lastByteMs_ = 0, valid_ = 0, rejected_ = 0, timeouts_ = 0;
  HlkReading reading_;
};

struct SelftestResult { unsigned passed = 0, failed = 0; };
SelftestResult runSelftests();  // Synthetic fixtures, NEVER real sensor readings.
