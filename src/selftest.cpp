#include "hlk_protocol.h"

#include <string.h>
#include "commands.h"
#include "safety.h"
#include "wifi_scan.h"
#include <stdio.h>

SelftestResult runSelftests() {
  SelftestResult result;
  auto check = [&result](bool condition) {
    if (condition) ++result.passed; else ++result.failed;
  };
  // Manufactured test fixtures; do not touch GPIO/UART or the live HlkParser.
  const uint8_t frame[] = {0xf4,0xf3,0xf2,0xf1,13,0,2,0xaa,3,
      0xf4,0,60,0x2c,1,40,0x2c,1,0x55,0,0xf8,0xf7,0xf6,0xf5};
  HlkParser parser;
  check(!parser.reading().received);
  for (size_t i = 0; i < sizeof(frame) - 1; ++i) parser.feed(frame[i], 10);
  check(!parser.reading().received);
  check(parser.feed(frame[sizeof(frame)-1], 11));
  check(parser.reading().movingCm == 244 && parser.reading().stationaryCm == 300);
  check(parser.reading().target == 3 && parser.reading().timestampMs == 11);
  check(parser.validFrames() == 1);
  uint8_t bad[sizeof(frame)]; memcpy(bad, frame, sizeof(frame));
  bad[sizeof(bad)-1] = 0;
  for (auto b : bad) parser.feed(b, 20);
  check(parser.validFrames() == 1 && parser.rejectedFrames() >= 1);
  for (auto b : frame) parser.feed(b, 30);
  check(parser.validFrames() == 2);
  parser.feed(0xf4, 40); parser.feed(0xf3, 40); parser.expire(150);
  check(parser.partialTimeouts() == 1);
  for (auto b : frame) parser.feed(b, 160);
  check(parser.validFrames() == 3);
  uint8_t tooLong[] = {0xf4,0xf3,0xf2,0xf1,0xff,0xff};
  for (auto b : tooLong) parser.feed(b, 170);
  check(parser.rejectedFrames() >= 2);
  parser.reset(); check(!parser.reading().received);
  uint8_t engineering[45] = {};
  memcpy(engineering, frame, 17); engineering[4] = 35; engineering[6] = 1;
  engineering[39] = 0x55; memcpy(engineering + 41, frame + 19, 4);
  for (auto b : engineering) parser.feed(b, 180);
  check(parser.reading().received && parser.reading().engineering);
  check(parser.reading().stationaryCm == 300);
  const uint32_t beforeBad = parser.validFrames();
  memcpy(bad, frame, sizeof(frame)); bad[8] = 4;
  for (auto b : bad) parser.feed(b, 190);
  check(parser.validFrames() == beforeBad);
  memcpy(bad, frame, sizeof(frame)); bad[11] = 101;
  for (auto b : bad) parser.feed(b, 200);
  check(parser.validFrames() == beforeBad);
  // A corrupt longer frame can contain a complete good frame. Recover it.
  uint8_t nested[46] = {0xf4,0xf3,0xf2,0xf1,36,0};
  memcpy(nested + 10, frame, sizeof(frame));
  for (auto b : nested) parser.feed(b, 210);
  check(parser.validFrames() == beforeBad + 1);
  check(parser.reading().timestampMs == 210 && !parser.reading().engineering);
  uint32_t random = 0x57ad1234;
  for (unsigned i = 0; i < 20000; ++i) {
    random ^= random << 13; random ^= random >> 17; random ^= random << 5;
    parser.feed(uint8_t(random), 220);
  }
  parser.expire(1000);
  for (auto b : frame) parser.feed(b, 1100);
  check(parser.reading().timestampMs == 1100 && parser.reading().movingCm == 244);
  SafetyState safety;
  check(safety.idle() && !safety.motorArmed() && !safety.servoArmed());
  check(!safety.start(Mode::Stepper, 1) && !safety.start(Mode::Servo, 1));
  check(safety.armMotor(2) && safety.start(Mode::Stepper, 3));
  check(!safety.motorArmed() && !safety.armServo(4));
  check(safety.overdue(config::testTimeoutMs + 3));
  safety.stop(); check(safety.idle() && !safety.motorArmed());
  check(safety.armServo(10)); safety.expire(30010);
  check(!safety.start(Mode::Servo, 30010));
  safety.armMotor(0xfffffff0u); safety.expire(0x20u);
  check(safety.motorArmed());
  safety.ota(); check(safety.mode() == Mode::Ota && !safety.motorArmed());
  check(!safety.armMotor(1) && !safety.start(Mode::Buzzer, 1));
  safety.stop(); check(safety.idle());
  SafetyState parked;
  check(parked.beginPark(20) && parked.mode() == Mode::Parked && !parked.idle());
  check(!parked.beginPark(21) && !parked.start(Mode::Parked, 21));
  parked.stop(); check(parked.idle());
  check(parked.armMotor(30) && !parked.beginPark(31));
  parked.stop();
  check(parseCommand("step_test") == Command::StepTest);
  check(parseCommand("step_test_long") == Command::StepTestLong);
  check(parseCommand("servo_test_long") == Command::ServoTestLong);
  check(parseCommand("park_pose") == Command::ParkPose);
  check(parseCommand("park_stepper") == Command::ParkStepper);
  check(parseCommand("stepper_left_10") == Command::StepperLeft10);
  check(parseCommand("stepper_right_10") == Command::StepperRight10);
  check(parseCommand("release_stepper") == Command::ReleaseStepper);
  check(parseCommand("park_servo") == Command::ParkServo);
  check(parseCommand("servo_up_200") == Command::ServoUp200);
  check(parseCommand("servo_down_200") == Command::ServoDown200);
  check(parseCommand("servo_1800") == Command::Invalid);
  check(parseCommand("servo_up_50") == Command::ServoUp50);
  check(parseCommand("servo_down_50") == Command::ServoDown50);
  check(parseCommand("release_servo") == Command::ReleaseServo);
  check(parseCommand("zero_stepper_here") == Command::ZeroStepperHere);
  check(parseCommand("save_servo_here") == Command::SaveServoHere);
  check(parseCommand("release_pose") == Command::ReleasePose);
  check(parseCommand("sensors_start") == Command::SensorsStart);
  check(parseCommand("sensors_stop") == Command::SensorsStop);
  check(parseCommand("stepper_left_5") == Command::StepperLeft5);
  check(parseCommand("stepper_right_5") == Command::StepperRight5);
  check(parseCommand("servo_up_25") == Command::ServoUp25);
  check(parseCommand("servo_down_25") == Command::ServoDown25);
  check(parseCommand("scan_mode_start") == Command::ScanModeStart);
  check(parseCommand("scan_mode_stop") == Command::ScanModeStop);
  check(parseCommand("hlk_alert_on") == Command::HlkAlertOn);
  check(parseCommand("hlk_alert_off") == Command::HlkAlertOff);
  check(config::stepperNudgeHalfSteps == 114 && config::servoNudgeUs == 50);
  check(config::servoMinPulseUs == 500 && config::servoParkPulseUs == 800 && config::servoMaxPulseUs == 1400);
  check(config::servoNudgeUs == 50 && config::servoCoarseUs == 200);
  check(config::stepperFineHalfSteps == 57 && config::servoFineUs == 25);
  check(config::scanStepperLimitHalfSteps == 684);
  check(config::scanServoMinPulseUs == 500 && config::scanServoMaxPulseUs == 950);
  check(config::hlkAlertMinCm == 30 && config::hlkAlertMaxCm == 75);
  check(config::hlkAlertMinIntervalMs == 150 && config::hlkAlertMaxIntervalMs == 2000);
  check(parseCommand("step_test 1000") == Command::Invalid);
  check(parseCommand("reboot") == Command::Invalid);
  check(parseCommand("wifi_scan") == Command::WifiScan);
  check(parseCommand("wifi_scan_page_7") == Command::WifiScanPage7);
  check(parseCommand("wifi_scan_page_8") == Command::Invalid);
  check(parseCommand("wifi_scan_page_0 extra") == Command::Invalid);
  WifiScanList networks;
  networks.add("room-net", 8, -70, 1, 3);
  networks.add("room-net", 8, -40, 6, 3);
  check(networks.count() == 1 && networks.at(0)->rssi == -40 && networks.at(0)->channel == 6);
  networks.add("room-net", 8, -80, 11, 3);
  check(networks.at(0)->rssi == -40);
  networks.add("room-net", 8, -50, 1, 0);
  check(networks.count() == 2);  // Different security is a separate choice.
  networks.add("", 0, -30, 1, 3);
  check(networks.hidden() == 1 && networks.count() == 2);
  const char invalidSsid[] = {'a', 0, 'b'};
  networks.add(invalidSsid, 3, -20, 1, 3);
  check(networks.count() == 2);
  char hex[65]; WifiScanList::hexSsid(*networks.at(0), hex);
  check(strcmp(hex, "726f6f6d2d6e6574") == 0);
  networks.clear(); check(networks.count() == 0 && networks.hidden() == 0);
  for (unsigned i = 0; i < WifiScanList::capacity + 5; ++i) {
    char ssid[16]; snprintf(ssid, sizeof(ssid), "fixture-%02u", i);
    networks.add(ssid, strlen(ssid), -100 + int(i), 6, 3);
  }
  check(networks.count() == WifiScanList::capacity && networks.truncated());
  networks.add("strongest", 9, -1, 11, 3); networks.sortBySignal();
  check(networks.at(0)->rssi == -1 && strcmp(networks.at(0)->ssid, "strongest") == 0);
  check(networks.at(WifiScanList::capacity) == nullptr);

  return result;
}
