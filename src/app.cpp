#include "app.h"

#include <WiFi.h>
#include <esp_ota_ops.h>
#include <esp_system.h>
#include <esp_log.h>
#include "config.h"
#include "pins.h"

String jsonQuote(const String& value) {
  String out = "\"";
  for (size_t i = 0; i < value.length(); ++i) {
    unsigned char c = value[i];
    if (c == '"' || c == '\\') { out += '\\'; out += char(c); }
    else if (c < 32) { char escaped[7]; snprintf(escaped, sizeof(escaped), "\\u%04x", c); out += escaped; }
    else out += char(c);
  }
  out += '"'; return out;
}

void App::begin() {
  // Set safe output latches first, before serial, NVS, Wi-Fi, or any web task.
  buzzer_.begin(); stepper_.begin(); servo_.begin();
  // This SDK has a secondary USB log console. Keep SDK log writers out of the
  // framed diagnostics channel; application events/status remain available.
  esp_log_level_set("*", ESP_LOG_NONE);
  pinMode(pins::hlkOut, INPUT_PULLDOWN);
  pinMode(pins::hlkRx, INPUT); pinMode(pins::hlkTx, INPUT);
  commands_ = xQueueCreate(8, sizeof(CommandRequest));
  snapshotMutex_ = xSemaphoreCreateMutex();
  if (!commands_ || !snapshotMutex_) { stopAll(); while (true) delay(1000); }
  bootReason_ = esp_reset_reason();
  console_.begin(*this);
  settings_.load();
  PoseSettings pose;
  const bool poseLoaded = settings_.loadPose(pose);
  if (poseLoaded && pose.stepperReferenceValid) {
    stepper_.setRelativeSteps(pose.stepperReferenceHalfSteps);
    stepperReferencePersisted_ = true;
    poseReferenceSource_ = "nvs";
  } else {
    // The previous firmware reported 1024 while this device was physically
    // parked. This is only a migration reference, not an absolute position.
    stepper_.setRelativeSteps(config::initialStepperReferenceHalfSteps);
    stepperReferencePersisted_ = settings_.saveStepperReference(config::initialStepperReferenceHalfSteps);
    poseReferenceSource_ = stepperReferencePersisted_ ? "migration_default_saved" : "migration_default_unsaved";
  }
  if (poseLoaded && pose.servoParkPulseValid) servoTargetUs_ = pose.servoParkPulseUs;
  network_.begin(*this, settings_);
  event("boot_idle_all_actuators_off");
  publish(millis());
  console_.send(String("{\"event\":\"ready\",\"version\":") + jsonQuote(config::version) +
                ",\"mode\":\"IDLE\",\"configured\":" + (settings_.configured() ? "true}" : "false}"));
}

void App::event(const char* text) {
  events_[eventIndex_++ % 8] = String(millis()) + ":" + text;
}
void App::stopAll() {
  buzzer_.stop(); stepper_.stop(); servo_.stop();
  stepperHolding_ = servoHolding_ = stepperMovePending_ = servoTestPending_ = false;
  safety_.stop();
}
bool App::beginPose(uint32_t now) {
  if (safety_.mode() == Mode::Parked) return true;
  return safety_.beginPark(now);
}
void App::syncPoseMode(uint32_t now) {
  if (stepperHolding_ || servoHolding_ || stepperMovePending_) {
    if (safety_.mode() == Mode::Idle) safety_.beginPark(now);
  } else if (safety_.mode() == Mode::Parked) {
    safety_.stop();
  }
}
void App::releaseStepper() {
  stepper_.stop(); stepperHolding_ = false; stepperMovePending_ = false;
  syncPoseMode(millis());
}
void App::releaseServo() {
  servo_.stop(); servoHolding_ = false; servoTestPending_ = false;
  syncPoseMode(millis());
}
void App::clearQueue() {
  CommandRequest discarded;
  while (xQueueReceive(commands_, &discarded, 0) == pdTRUE) {}
}
void App::requestStop() { stopRequested_.store(true); }

bool App::enqueue(Command command, uint32_t& id) {
  if (command == Command::Invalid || command == Command::Help || command == Command::Status) return false;
  if (command == Command::Stop) { requestStop(); id = 0; return true; }
  if (otaActive()) return false;
  id = nextId_.fetch_add(1);
  CommandRequest request{command, id, millis()};
  return xQueueSend(commands_, &request, 0) == pdTRUE;
}

bool App::beginOta() {
  if (otaActive_.load()) return false;
  otaSafe_.store(false);
  bool expected = false;
  if (!otaActive_.compare_exchange_strong(expected, true)) return false;
  const uint32_t started = millis();
  while (!otaSafe_.load() && uint32_t(millis() - started) < 1000) vTaskDelay(pdMS_TO_TICKS(2));
  if (!otaSafe_.load()) { otaActive_.store(false); return false; }
  return true;
}
void App::finishOta(bool success, const char*) {
  otaSucceeded_.store(success); otaFinished_.store(true);
  if (success) rebootAt_.store(millis() + 1000);
  // On failure the main task clears the gate, after leaving all outputs off.
}

String App::execute(Command command) {
  const uint32_t now = millis();
  auto result = [](bool ok, const char* message) {
    return String("{\"ok\":") + (ok ? "true" : "false") + ",\"message\":" + jsonQuote(message) + "}";
  };
  if (command == Command::Status) { publish(now); return statusJson(); }
  if (command == Command::Help) return "{\"ok\":true,\"commands\":[\"help\",\"status\",\"buzzer_test\",\"hlk_start\",\"hlk_stop\",\"motor_arm\",\"step_test\",\"step_test_long\",\"servo_arm\",\"servo_test\",\"servo_test_long\",\"park_stepper\",\"stepper_left_10\",\"stepper_right_10\",\"release_stepper\",\"park_servo\",\"servo_up_50\",\"servo_down_50\",\"release_servo\",\"zero_stepper_here\",\"save_servo_here\",\"release_pose\",\"stop\",\"selftest\",\"wifi_scan\",\"wifi_scan_results\",\"wifi_scan_cancel\",\"wifi_scan_page_0\",\"wifi_scan_page_1\",\"wifi_scan_page_2\",\"wifi_scan_page_3\",\"wifi_scan_page_4\",\"wifi_scan_page_5\",\"wifi_scan_page_6\",\"wifi_scan_page_7\"],\"provisioning\":\"use tools/ops/device.py setup for numbered SSID selection over USB\"}";
  if (command == Command::Invalid) return result(false, "unknown_command_no_action");
  if (command == Command::Stop) {
    stopAll(); network_.cancelScan(); clearQueue();
    if (otaActive()) safety_.ota();
    event("stop_disarmed_outputs_off"); return result(true, "stopped_disarmed");
  }
  if (otaActive()) return result(false, "ota_locked_no_action");
  if (command == Command::ParkPose) return result(false, "use_separate_axis_commands");
  if (command == Command::WifiScanResults) return network_.scanJson();
  if (command >= Command::WifiScanPage0 && command <= Command::WifiScanPage7) {
    return network_.scanJson(int(command) - int(Command::WifiScanPage0));
  }
  if (command == Command::WifiScanCancel) {
    network_.cancelScan(); return result(true, "wifi_scan_cancelled");
  }
  if (command == Command::WifiScan) {
    stopAll(); clearQueue();
    const bool started = network_.startScan();
    if (started) event("passive_wifi_scan_started_disarmed");
    return result(started, started ? "wifi_scan_started" : "wifi_scan_busy_or_failed");
  }
  if (command == Command::ReleasePose) {
    if (safety_.mode() != Mode::Parked) return result(false, "not_parked_no_action");
    stopAll(); event("park_pose_released_outputs_off");
    return result(true, "pose_released_idle");
  }
  if (command == Command::ReleaseStepper) {
    if (safety_.mode() != Mode::Parked || (!stepperHolding_ && !stepperMovePending_)) return result(false, "stepper_not_held_no_action");
    releaseStepper(); event("stepper_axis_released"); return result(true, "stepper_released");
  }
  if (command == Command::ReleaseServo) {
    if (safety_.mode() != Mode::Parked || (!servoHolding_ && !servoTestPending_)) return result(false, "servo_not_active_no_action");
    releaseServo(); event("servo_axis_released"); return result(true, "servo_released");
  }
  if (command == Command::ZeroStepperHere) {
    if (safety_.mode() != Mode::Idle && safety_.mode() != Mode::Parked) return result(false, "busy_no_reference_change");
    if (stepper_.active() || stepperMovePending_) return result(false, "stepper_busy_no_reference_change");
    stepper_.setRelativeSteps(0);
    stepperReferencePersisted_ = settings_.saveStepperReference(0);
    poseReferenceSource_ = stepperReferencePersisted_ ? "nvs" : "nvs_save_failed";
    event("stepper_relative_reference_zeroed_here"); return result(stepperReferencePersisted_, stepperReferencePersisted_ ? "stepper_reference_zeroed" : "stepper_reference_save_failed");
  }
  if (command == Command::SaveServoHere) {
    if (safety_.mode() != Mode::Parked) return result(false, "pose_not_active_no_reference_change");
    if (!servoHolding_ || !servo_.attached()) return result(false, "servo_not_held_no_reference_change");
    const bool saved = settings_.saveServoParkPulse(servoTargetUs_);
    event(saved ? "servo_park_pulse_saved_nvs" : "servo_park_pulse_save_failed");
    return result(saved, saved ? "servo_park_pulse_saved" : "servo_park_pulse_save_failed");
  }
  if (command == Command::Selftest) {
    if (!safety_.idle()) return result(false, "busy");
    const auto test = runSelftests();
    return String("{\"ok\":") + (test.failed ? "false" : "true") +
           ",\"synthetic_only\":true,\"passed\":" + test.passed + ",\"failed\":" + test.failed + "}";
  }
  if (command == Command::HlkStop) {
    if (hlkEnabled_) hlkSerial_.end();
    hlkEnabled_ = false;
    pinMode(pins::hlkRx, INPUT); pinMode(pins::hlkTx, INPUT);
    event("hlk_stopped_no_config_writes"); return result(true, "hlk_stopped");
  }
  if (command == Command::HlkStart) {
    if (!hlkEnabled_) {
      hlk_.reset(); hlkSerial_.setRxBufferSize(1024);
      hlkSerial_.begin(config::hlkBaud, SERIAL_8N1, pins::hlkRx, pins::hlkTx);
      hlkEnabled_ = true;
    }
    event("hlk_passive_uart_started"); return result(true, "hlk_receiving_no_config_writes");
  }
  const bool poseCommand = command == Command::ParkStepper || command == Command::StepperLeft10 ||
      command == Command::StepperRight10 || command == Command::ParkServo || command == Command::ServoUp50 ||
      command == Command::ServoDown50;
  if ((!poseCommand && !safety_.idle()) || (poseCommand && safety_.mode() != Mode::Idle && safety_.mode() != Mode::Parked)) {
    return result(false, "busy_no_action");
  }
  if (network_.scanning()) return result(false, "wifi_scan_in_progress_actuators_idle");
  if (settings_.configured() && !network_.connected()) return result(false, "wifi_offline_actuators_remain_idle");
  if (command == Command::ParkStepper) {
    if (!beginPose(now)) return result(false, "pose_requires_idle_and_no_arms");
    if (stepper_.active()) return result(false, "stepper_busy");
    stepper_.holdCurrent(); stepperHolding_ = true;
    event("stepper_axis_parked_current_position_hold"); return result(true, "stepper_parked_current_position");
  }
  if (command == Command::StepperLeft10 || command == Command::StepperRight10) {
    if (!beginPose(now)) return result(false, "pose_requires_idle_and_no_arms");
    if (stepper_.active()) return result(false, "stepper_busy");
    const int direction = command == Command::StepperRight10 ? config::stepperClockwiseSign : -config::stepperClockwiseSign;
    if (!stepper_.startPark(micros(), config::stepperNudgeHalfSteps, direction)) {
      syncPoseMode(now); return result(false, "stepper_pose_limit");
    }
    stepperHolding_ = false; stepperMovePending_ = true;
    event(command == Command::StepperRight10 ? "stepper_nudge_right_10_started" : "stepper_nudge_left_10_started");
    return result(true, command == Command::StepperRight10 ? "stepper_right_10_started" : "stepper_left_10_started");
  }
  if (command == Command::ParkServo || command == Command::ServoUp50 || command == Command::ServoDown50) {
    if (!beginPose(now)) return result(false, "pose_requires_idle_and_no_arms");
    if (servo_.active()) return result(false, "servo_busy");
    const bool nudge = command != Command::ParkServo;
    const bool started = nudge ? servo_.startNudge(now, command == Command::ServoUp50) : servo_.start(now, false);
    if (!started) {
      syncPoseMode(now); return result(false, "servo_pwm_setup_failed");
    }
    servoHolding_ = false; servoTestPending_ = true;
    event(command == Command::ParkServo ? "servo_old_small_test_started" : "servo_old_directional_nudge_started");
    return result(true, command == Command::ParkServo ? "servo_small_test_started" : "servo_small_nudge_started");
  }
  if (command == Command::MotorArm) {
    safety_.armMotor(now); event("motor_armed_30s_physical_readiness_is_operator_responsibility");
    return result(true, "motor_armed_one_test_30s");
  }
  if (command == Command::ServoArm) {
    safety_.armServo(now); event("servo_armed_30s_physical_readiness_is_operator_responsibility");
    return result(true, "servo_armed_one_test_30s");
  }
  if (command == Command::BuzzerTest && safety_.start(Mode::Buzzer, now)) {
    buzzer_.start(now); event("buzzer_test_started"); return result(true, "buzzer_test_started");
  }
  if (command == Command::StepTest || command == Command::StepTestLong) {
    if (!safety_.start(Mode::Stepper, now)) return result(false, "motor_not_armed_or_expired");
    const bool longTest = command == Command::StepTestLong;
    if (!stepper_.start(micros(), longTest ? config::longStepCount : config::stepCount)) { stopAll(); return result(false, "relative_step_limit"); }
    event(longTest ? "stepper_long_test_started_512_forward_512_reverse" : "stepper_test_started_64_forward_64_reverse");
    return result(true, longTest ? "stepper_long_test_started" : "stepper_test_started");
  }
  if (command == Command::ServoTest || command == Command::ServoTestLong) {
    if (!safety_.start(Mode::Servo, now)) return result(false, "servo_not_armed_or_expired");
    const bool longTest = command == Command::ServoTestLong;
    if (!servo_.start(now, longTest)) { stopAll(); return result(false, "servo_pwm_setup_failed"); }
    event(longTest ? "servo_long_test_started_small_pulses" : "servo_test_started_small_pulses");
    return result(true, longTest ? "servo_long_test_started" : "servo_test_started");
  }
  return result(false, "command_rejected_no_action");
}

String App::serialLine(char* line) {
  if (strncmp(line, "provision\t", 10) == 0) {
    if (otaActive() || !safety_.idle() || network_.scanning()) return "{\"ok\":false,\"message\":\"busy_no_config_change\"}";
    stopAll(); clearQueue();
    bool ok = settings_.provision(line);
    if (ok) { network_.reconfigure(); wifiWasConnected_ = false; event("local_provisioning_saved_no_secrets_logged"); }
    publish(millis());
    return ok ? "{\"ok\":true,\"message\":\"provisioned\"}" :
                "{\"ok\":false,\"message\":\"invalid_config_or_nvs_failure\"}";
  }
  Command command = parseCommand(line);
  String response = execute(command);
  if (command != Command::Status && command != Command::Help) lastResult_ = response;
  publish(millis());
  return response;
}

String App::statusJson() {
  if (xSemaphoreTake(snapshotMutex_, pdMS_TO_TICKS(30)) != pdTRUE) return "{\"error\":\"snapshot_busy\"}";
  String copy = snapshot_; xSemaphoreGive(snapshotMutex_); return copy;
}

void App::publish(uint32_t now) {
  const auto& reading = hlk_.reading();
  const bool valid = hlkEnabled_ && reading.received && uint32_t(now - reading.timestampMs) <= config::hlkStaleMs;
  const esp_partition_t* running = esp_ota_get_running_partition();
  const esp_partition_t* next = esp_ota_get_next_update_partition(nullptr);
  String s; s.reserve(5000);
  s = String("{\"version\":") + jsonQuote(config::version) + ",\"build\":" + jsonQuote(String(__DATE__) + " " + __TIME__) +
      ",\"uptime_ms\":" + now + ",\"mode\":" + jsonQuote(modeName(safety_.mode())) +
      ",\"motor_armed\":" + (safety_.motorArmed() ? "true" : "false") +
      ",\"servo_armed\":" + (safety_.servoArmed() ? "true" : "false") +
      ",\"ota_active\":" + (otaActive() ? "true" : "false");
  s += String(",\"wifi\":{\"configured\":") + (settings_.configured() ? "true" : "false") +
       ",\"connected\":" + (network_.connected() ? "true" : "false") +
       ",\"ip\":" + jsonQuote(network_.connected() ? WiFi.localIP().toString() : "") +
       ",\"rssi_dbm\":" + (network_.connected() ? String(WiFi.RSSI()) : "null") +
       ",\"channel\":" + (network_.connected() ? String(WiFi.channel()) : "null") +
       ",\"attempts\":" + network_.attempts() + ",\"scan_state\":" + jsonQuote(network_.scanState()) +
       ",\"scan_id\":" + network_.scanId() + ",\"web_ready\":" + (network_.webReady() ? "true}" : "false}");
  s += String(",\"diagnostics\":{\"chip\":") + jsonQuote(ESP.getChipModel()) +
       ",\"revision_major_core_api\":" + ESP.getChipRevision() + ",\"flash_bytes\":" + ESP.getFlashChipSize() +
       ",\"usb_console_ready\":" + (console_.ready() ? "true" : "false") +
       ",\"free_heap\":" + ESP.getFreeHeap() + ",\"min_free_heap\":" + ESP.getMinFreeHeap() +
       ",\"psram_enabled\":false,\"psram_bytes_initialized\":" + ESP.getPsramSize() +
       ",\"reset_reason_code\":" + bootReason_ + ",\"brownout_reset\":" + (bootReason_ == ESP_RST_BROWNOUT ? "true" : "false") +
       ",\"max_loop_us\":" + maxLoopUs_ + ",\"supply_voltage_measured\":false,\"wire_continuity_verified\":false}";
   s += String(",\"pose\":{\"stepper_reference_source\":") + jsonQuote(poseReferenceSource_) +
        ",\"stepper_reference_saved\":" + (stepperReferencePersisted_ ? "true" : "false") +
        ",\"stepper_nudge_half_steps\":" + config::stepperNudgeHalfSteps +
        ",\"servo_target_us\":" + servoTargetUs_ + ",\"servo_nudge_us\":" + config::servoNudgeUs +
        ",\"servo_min_us\":" + config::servoMinPulseUs + ",\"servo_max_us\":" + config::servoMaxPulseUs + "},";
   s += String("\"actuators\":{\"buzzer_commanded_on\":") + (buzzer_.sounding() ? "true" : "false") +
        ",\"stepper_energized\":" + (stepper_.energized() ? "true" : "false") +
        ",\"stepper_holding\":" + (stepperHolding_ ? "true" : "false") +
        ",\"relative_half_steps\":" + stepper_.relativeSteps() +
        ",\"relative_degrees_nominal\":" + String(stepper_.relativeSteps() * 360.0f / 4096.0f, 1) +
        ",\"step_scheduling_late\":" + stepper_.schedulingLate() +
        ",\"servo_attached\":" + (servo_.attached() ? "true" : "false") + ",\"servo_pulse_us\":" + servo_.pulseUs() +
        ",\"servo_holding\":" + (servoHolding_ ? "true" : "false") + ",\"servo_test_pending\":" + (servoTestPending_ ? "true" : "false") +
        ",\"servo_target_us\":" + servoTargetUs_ +
        ",\"physical_motion_verified\":false}";
  s += String(",\"hlk\":{\"enabled\":") + (hlkEnabled_ ? "true" : "false") +
       ",\"valid\":" + (valid ? "true" : "false") + ",\"stale\":" + (reading.received && !valid ? "true" : "false") +
       ",\"received\":" + (reading.received ? "true" : "false") + ",\"uart_bytes\":" + hlkBytes_ +
       ",\"valid_frames\":" + hlk_.validFrames() + ",\"rejected_frames\":" + hlk_.rejectedFrames() +
       ",\"partial_timeouts\":" + hlk_.partialTimeouts() + ",\"out_raw_unverified\":" + digitalRead(pins::hlkOut) +
       ",\"out_wiring_verified\":false,\"last_reading\":";
  if (!reading.received) s += "null}";
  else s += String("{\"timestamp_ms\":") + reading.timestampMs + ",\"age_ms\":" + uint32_t(now - reading.timestampMs) +
       ",\"target_state\":" + reading.target + ",\"presence\":" + (reading.target ? "true" : "false") +
       ",\"moving_distance_cm\":" + reading.movingCm + ",\"stationary_distance_cm\":" + reading.stationaryCm +
       ",\"moving_energy\":" + reading.movingEnergy + ",\"stationary_energy\":" + reading.stationaryEnergy +
       ",\"detection_distance_cm\":" + reading.detectionCm + ",\"engineering\":" + (reading.engineering ? "true}}" : "false}}");
  s += String(",\"ota\":{\"running_slot\":") + jsonQuote(running ? running->label : "unknown") +
       ",\"next_slot_bytes\":" + (next ? String(next->size) : "0") + ",\"automatic_rollback\":false}";
  s += String(",\"last_command_id\":") + lastCommandId_ + ",\"last_result\":" + lastResult_ + ",\"events\":[";
  bool first = true;
  for (unsigned i = 0; i < 8; ++i) {
    const String& item = events_[(eventIndex_ + i) % 8];
    if (!item.length()) continue;
    if (!first) s += ',';
    first = false; s += jsonQuote(item);
  }
  s += "]}";
  if (xSemaphoreTake(snapshotMutex_, pdMS_TO_TICKS(2)) == pdTRUE) {
    snapshot_ = s; xSemaphoreGive(snapshotMutex_);
  }
  lastPublish_ = now;
}

void App::tick() {
  const uint32_t loopStart = micros();
  const uint32_t now = millis();
  if (stopRequested_.exchange(false)) {
    stopAll(); network_.cancelScan(); clearQueue(); event("priority_stop_disarmed");
    if (otaActive()) safety_.ota();
  }
  if (otaActive() && !otaSafe_.load()) {
    stopAll(); network_.cancelScan(); clearQueue(); safety_.ota(); event("ota_safe_outputs_off"); otaSafe_.store(true);
  }
  if (otaFinished_.exchange(false)) {
    if (otaSucceeded_.load()) event("ota_image_verified_reboot_pending");
    else { stopAll(); otaActive_.store(false); otaSafe_.store(false); event("ota_failed_disarmed_idle"); }
  }
  if (wifiWasConnected_ && !network_.connected()) {
    stopAll(); clearQueue(); event("wifi_lost_disarmed");
    if (otaActive()) safety_.ota();
  }
  wifiWasConnected_ = network_.connected();
  console_.tick();
  CommandRequest request;
  if (!otaActive() && xQueueReceive(commands_, &request, 0) == pdTRUE) {
    lastCommandId_ = request.id;
    lastResult_ = uint32_t(millis() - request.queuedAt) > 500 ?
        "{\"ok\":false,\"message\":\"expired_no_action\"}" : execute(request.command);
  }
  safety_.expire(now);
  if (safety_.overdue(now)) { stopAll(); event("test_timeout_outputs_off"); }
  buzzer_.tick(now);
  const bool stepperWasActive = stepper_.active();
  stepper_.tick(micros());
  if (stepperMovePending_ && stepperWasActive && !stepper_.active()) {
    stepperMovePending_ = false; stepperHolding_ = true;
    stepperReferencePersisted_ = settings_.saveStepperReference(stepper_.relativeSteps());
    poseReferenceSource_ = stepperReferencePersisted_ ? "nvs" : "nvs_save_failed";
    event("stepper_nudge_complete_hold");
  }
  const bool servoWasActive = servo_.active();
  servo_.tick(now);
  if (servoTestPending_ && servoWasActive && !servo_.active()) {
    servoTestPending_ = false;
    event("servo_old_small_test_complete_detached");
    syncPoseMode(now);
  }
  if ((safety_.mode() == Mode::Buzzer && !buzzer_.active()) ||
      (safety_.mode() == Mode::Stepper && !stepper_.active()) ||
      (safety_.mode() == Mode::Servo && !servo_.active())) {
    stopAll(); event("test_schedule_complete_physical_result_unverified");
  }
  if (hlkEnabled_) {
    unsigned budget = 512;
    while (hlkSerial_.available() && budget--) { hlk_.feed(uint8_t(hlkSerial_.read()), now); ++hlkBytes_; }
    hlk_.expire(now);
  }
  network_.tick(now);
  if (uint32_t(now - lastPublish_) >= 200) publish(now);
  const uint32_t reboot = rebootAt_.load();
  if (reboot && int32_t(now - reboot) >= 0) { stopAll(); ESP.restart(); }
  const uint32_t elapsed = micros() - loopStart;
  if (elapsed > maxLoopUs_) maxLoopUs_ = elapsed;
}
