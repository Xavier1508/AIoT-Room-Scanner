#pragma once

#include <stdint.h>

namespace config {
constexpr char version[] = "0.2.2-long-tests";
constexpr char hostname[] = "aiot-room";
constexpr char webUser[] = "admin";
constexpr uint32_t hlkBaud = 256000;
constexpr uint32_t hlkStaleMs = 2000;
constexpr uint32_t frameTimeoutMs = 100;
constexpr uint32_t armTimeoutMs = 30000;
constexpr uint32_t testTimeoutMs = 20000;
constexpr uint32_t stepIntervalUs = 10000;  // 100 half-steps/s, no catch-up bursts.
constexpr int stepCount = 64;
constexpr int longStepCount = 512;
constexpr int relativeStepLimit = 128;  // Relative to boot, NOT absolute angle.
constexpr int longRelativeStepLimit = 1024;
constexpr uint32_t wifiRetryMs = 15000;
constexpr uint32_t otaReceiveLimitMs = 120000;
constexpr uint32_t provisioningTimeoutMs = 90000;
constexpr uint32_t wifiScanTimeoutMs = 20000;
}  // namespace config
