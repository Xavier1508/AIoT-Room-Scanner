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
constexpr uint8_t tofSdaReserved = 8;
constexpr uint8_t tofSclReserved = 9;
constexpr uint8_t cdmConditionedReserved = 1;  // Do not read/connect raw CDM324.
}  // namespace pins
