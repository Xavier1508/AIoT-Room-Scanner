#pragma once

#include <stdint.h>

// GPIO numbers, never header positions. Keep identical to the handoff workbook.
namespace pins {
constexpr uint8_t hlkRx = 16;  // Sensor TX -> ESP RX.
constexpr uint8_t hlkTx = 17;  // Sensor RX <- ESP TX. No config commands sent.
constexpr uint8_t hlkOut = 18;
constexpr uint8_t stepper[4] = {4, 5, 6, 7};  // Physical IN1, IN2, IN3, IN4.
constexpr uint8_t servo = 15;
constexpr uint8_t buzzer = 21;  // Active LOW; 3V3 supply.
  constexpr uint8_t hcTrig = 10;  // HC-SR04 trigger; output starts LOW.
  constexpr uint8_t hcEcho = 11;  // HC-SR04 echo through the installed divider.
  constexpr uint8_t tofSda = 8;
  constexpr uint8_t tofScl = 9;
  constexpr uint8_t tofInt = 14;   // Optional VL53L1X interrupt, polling is used.
  constexpr uint8_t tofXshut = 13; // Optional VL53L1X shutdown, never driven at boot.
  // Compatibility names retained for source consumers of the pre-sensor map.
  constexpr uint8_t tofSdaReserved = tofSda;
  constexpr uint8_t tofSclReserved = tofScl;
constexpr uint8_t cdmConditionedReserved = 1;  // Do not read/connect raw CDM324.
}  // namespace pins
