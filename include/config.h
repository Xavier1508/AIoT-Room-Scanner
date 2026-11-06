#pragma once

#include <stdint.h>

namespace config {
constexpr char version[] = "0.2.5-servo-small-test";
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
// Nominal pose only: 28BYJ-48 variants have no absolute encoder/homing here.
constexpr int parkHalfSteps = 512;          // Estimated 45 degrees for 4096 half-steps/rev.
constexpr int stepperClockwiseSign = 1;     // Invert to -1 after a controlled direction check.
constexpr int initialStepperReferenceHalfSteps = 1024; // Migrated from the observed 0.2.3 live status.
constexpr int stepperNudgeHalfSteps = 114;             // Nominal 10 degrees at 4096 half-steps/rev.
constexpr uint16_t servoParkPulseUs = 2000;            // Initial target; calibrate with ±50 us nudges.
constexpr uint16_t servoNudgeUs = 50;
constexpr uint16_t servoMinPulseUs = 1000;
constexpr uint16_t servoMaxPulseUs = 2000;
constexpr uint32_t wifiRetryMs = 15000;
constexpr uint32_t otaReceiveLimitMs = 120000;
constexpr uint32_t provisioningTimeoutMs = 90000;
constexpr uint32_t wifiScanTimeoutMs = 20000;
}  // namespace config
