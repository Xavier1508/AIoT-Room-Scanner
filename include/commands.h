#pragma once

#include <string.h>

enum class Command {
  Invalid, Help, Status, BuzzerTest, HlkStart, HlkStop,
  MotorArm, StepTest, StepTestLong, ServoArm, ServoTest, ServoTestLong, Stop, Selftest,
  WifiScan, WifiScanResults, WifiScanCancel,
  WifiScanPage0, WifiScanPage1, WifiScanPage2, WifiScanPage3,
  WifiScanPage4, WifiScanPage5, WifiScanPage6, WifiScanPage7
};

inline Command parseCommand(const char* text) {
  struct Entry { const char* name; Command value; };
  static const Entry entries[] = {
      {"help", Command::Help}, {"status", Command::Status},
      {"buzzer_test", Command::BuzzerTest}, {"hlk_start", Command::HlkStart},
      {"hlk_stop", Command::HlkStop}, {"motor_arm", Command::MotorArm},
      {"step_test", Command::StepTest}, {"servo_arm", Command::ServoArm},
      {"step_test_long", Command::StepTestLong},
      {"servo_test", Command::ServoTest}, {"servo_test_long", Command::ServoTestLong},
      {"stop", Command::Stop},
      {"selftest", Command::Selftest}, {"wifi_scan", Command::WifiScan},
      {"wifi_scan_results", Command::WifiScanResults},
      {"wifi_scan_cancel", Command::WifiScanCancel}};
  for (const auto& entry : entries) {
    if (strcmp(text, entry.name) == 0) return entry.value;
  }
  if (strncmp(text, "wifi_scan_page_", 15) == 0 && text[15] >= '0' &&
      text[15] <= '7' && text[16] == 0) {
    return static_cast<Command>(int(Command::WifiScanPage0) + text[15] - '0');
  }
  return Command::Invalid;
}
