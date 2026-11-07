#pragma once

#include <stdint.h>

namespace config {
constexpr char version[] = "0.3.2-sensor-poll-throttled";
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
constexpr uint16_t servoParkPulseUs = 800;             // User-confirmed mechanical zero; saved without boot motion.
constexpr uint16_t servoNudgeUs = 50;
constexpr uint16_t servoCoarseUs = 200;
constexpr uint16_t servoMinPulseUs = 500;
constexpr uint16_t servoMaxPulseUs = 1400;
constexpr uint32_t sensorHcIntervalMs = 250;
constexpr uint32_t sensorHcTimeoutUs = 25000;           // Bounded to about 4.2 m acoustic range.
constexpr uint32_t sensorHcMinPulseUs = 116;            // About 2 cm at 343 m/s.
constexpr uint32_t sensorHcMaxPulseUs = 23325;          // About 4 m at 343 m/s.
constexpr uint32_t sensorHcMinRangeMm = 20;
constexpr uint32_t sensorHcMaxRangeMm = 4000;
constexpr uint32_t sensorTofIntervalMs = 100;
constexpr uint32_t sensorTofPollMs = 10;
constexpr uint32_t sensorTofBootTimeoutMs = 150;
constexpr uint32_t sensorTofMaxRangeMm = 4000;
constexpr uint32_t sensorStaleMs = 1500;
constexpr uint32_t sensorI2cHz = 100000;
constexpr uint32_t wifiRetryMs = 15000;
constexpr uint32_t otaReceiveLimitMs = 120000;
constexpr uint32_t provisioningTimeoutMs = 90000;
constexpr uint32_t wifiScanTimeoutMs = 20000;
}  // namespace config
