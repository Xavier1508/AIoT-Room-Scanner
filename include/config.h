#pragma once

#include <stdint.h>

namespace config {
constexpr char version[] = "0.9.0-hybrid-alert";
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
constexpr int stepperFineHalfSteps = 57;               // Nominal 5 degrees at 4096 half-steps/rev.
constexpr uint16_t servoParkPulseUs = 800;             // User-confirmed mechanical zero; saved without boot motion.
constexpr uint16_t servoNudgeUs = 50;
constexpr uint16_t servoCoarseUs = 200;
constexpr uint16_t servoFineUs = 25;
constexpr uint16_t servoMinPulseUs = 500;
constexpr uint16_t servoMaxPulseUs = 1400;
// Mapping scan envelope requested by the operator. It is enforced only while
// scan mode is active, so manual tuning retains the wider 500-1400 us range.
constexpr int scanStepperLimitHalfSteps = 684;          // 12 x 57 = 60.1 deg nominal; cable-safe user limit.
constexpr uint16_t scanServoMinPulseUs = 500;           // Up.
constexpr uint16_t scanServoMaxPulseUs = 950;           // Down.
constexpr uint16_t hlkAlertMinCm = 30;                  // LD2410C blind/clamp zone.
constexpr uint16_t hlkAlertMaxCm = 75;                  // Parking-sensor ramp starts here.
constexpr uint16_t hlkAlertHysteresisCm = 10;           // Stop above max + hysteresis.
constexpr uint8_t hlkAlertEnergy = 40;
constexpr uint32_t hlkAlertMinIntervalMs = 150;         // Fast beep near 30 cm.
constexpr uint32_t hlkAlertMaxIntervalMs = 2000;        // Slow beep at 75 cm.
constexpr uint16_t hlkAlertBeepMs = 70;
constexpr uint8_t hlkAlertConfirmFrames = 3;
constexpr uint32_t hlkAlertParkedStableMs = 1000;      // Re-arm only after the arm is still.
constexpr uint32_t mlAlertIntervalMs = 700;             // AI-alert beep period.
constexpr float mlAlertConfidence = 0.80f;              // Minimum human confidence.
constexpr uint16_t mlAlertTriggerEnergy = 70;           // HLK moving energy fast edge.
constexpr uint8_t mlAlertTriggerFrames = 2;             // Consecutive HLK frames.
constexpr uint32_t mlAlertVetoDelayMs = 6500;           // Let the 32-frame window fill.
constexpr uint32_t mlAlertVetoCooldownMs = 5000;        // No re-trigger after a veto.
constexpr uint32_t mlAlertProvisionalMs = 8000;         // Max unconfirmed beep time.
constexpr float mlAlertVetoConfidence = 0.90f;          // Confident empty veto.
constexpr uint16_t mlAlertReleaseEnergy = 20;           // HLK movement considered stopped.
constexpr uint32_t mlAlertReleaseHoldMs = 1000;         // Fast release after no movement.
constexpr int16_t hcOffsetMm = 0;                       // Provisional; refine in PC calibration.
constexpr int16_t tofOffsetMm = 50;                     // ToF lens is ~5 cm ahead of HC reference.
constexpr uint16_t tofNearReflectorMm = 500;            // Fixed near return (mount/cover) threshold.
constexpr uint16_t tofNearReflectorHcMm = 1000;         // Only flag when HC sees farther than this.
constexpr uint16_t tofNearReflectorClearMm = 800;       // Clear the flag when ToF sees beyond this.
constexpr uint8_t tofNearReflectorSamples = 10;         // Consecutive samples before flagging.
constexpr uint16_t hlkMinRangeCm = 30;
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
constexpr uint32_t sensorTofStallRecoverMs = 3000;
constexpr uint32_t sensorTofRecoverCooldownMs = 5000;
constexpr uint32_t sensorTofRecoverRetryMs = 10000;
constexpr uint32_t sensorStaleMs = 1500;
constexpr uint32_t sensorI2cHz = 100000;
constexpr uint32_t wifiRetryMs = 15000;
constexpr uint32_t otaReceiveLimitMs = 120000;
constexpr uint32_t provisioningTimeoutMs = 90000;
constexpr uint32_t wifiScanTimeoutMs = 20000;
}  // namespace config
