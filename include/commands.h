#pragma once

#include <string.h>

enum class Command {
  Invalid, Help, Status, BuzzerTest, HlkStart, HlkStop,
  MotorArm, StepTest, StepTestLong, ServoArm, ServoTest, ServoTestLong,
  ParkPose, ParkStepper, StepperLeft10, StepperRight10, StepperLeft5, StepperRight5, ReleaseStepper,
  ParkServo, ServoUp200, ServoDown200, ServoUp50, ServoDown50, ServoUp25, ServoDown25, ReleaseServo,
  ZeroStepperHere, SaveServoHere, ReleasePose, SensorsStart, SensorsStop,
  ScanModeStart, ScanModeStop, HlkAlertOn, HlkAlertOff, Stop, Selftest,
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
      {"park_pose", Command::ParkPose}, {"park_stepper", Command::ParkStepper},
      {"stepper_left_10", Command::StepperLeft10}, {"stepper_right_10", Command::StepperRight10},
      {"stepper_left_5", Command::StepperLeft5}, {"stepper_right_5", Command::StepperRight5},
      {"release_stepper", Command::ReleaseStepper}, {"park_servo", Command::ParkServo},
      {"servo_up_200", Command::ServoUp200}, {"servo_down_200", Command::ServoDown200},
      {"servo_up_50", Command::ServoUp50}, {"servo_down_50", Command::ServoDown50},
      {"servo_up_25", Command::ServoUp25}, {"servo_down_25", Command::ServoDown25},
      {"release_servo", Command::ReleaseServo}, {"zero_stepper_here", Command::ZeroStepperHere},
      {"save_servo_here", Command::SaveServoHere}, {"release_pose", Command::ReleasePose},
      {"sensors_start", Command::SensorsStart}, {"sensors_stop", Command::SensorsStop},
      {"scan_mode_start", Command::ScanModeStart}, {"scan_mode_stop", Command::ScanModeStop},
      {"hlk_alert_on", Command::HlkAlertOn}, {"hlk_alert_off", Command::HlkAlertOff},
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
