#include "sensors.h"

#include <Wire.h>
#include <string.h>
#include "config.h"
#include "pins.h"

namespace {
constexpr uint8_t tofAddress = 0x29;
constexpr uint16_t tofExpectedModel = 0xEACC;
constexpr uint32_t tofTargetRate = 0x0A00;
constexpr uint32_t tofTimingGuardUs = 4528;

// VL53L1X register map. The small implementation below is derived from the
// ST VL53L1X API register sequence and the BSD-3-Clause Pololu Arduino driver;
// it keeps this project self-contained and does not install a PlatformIO
// dependency during bring-up.
constexpr uint16_t regSoftReset = 0x0000;
constexpr uint16_t regVhvTimeout = 0x0008;
constexpr uint16_t regVhvInit = 0x000B;
constexpr uint16_t regPartToPartOffset = 0x001E;
constexpr uint16_t regMmOuterOffset = 0x0022;
constexpr uint16_t regTargetTotalRate = 0x0024;
constexpr uint16_t regPadI2cHvExtsup = 0x002E;
constexpr uint16_t regGpioStatus = 0x0031;
constexpr uint16_t regSigmaPulseWidth = 0x0036;
constexpr uint16_t regCrosstalkHeight = 0x0039;
constexpr uint16_t regRangeIgnoreHeight = 0x003E;
constexpr uint16_t regRangeMinClip = 0x003F;
constexpr uint16_t regConsistencyTolerance = 0x0040;
constexpr uint16_t regPhasecalTimeout = 0x004B;
constexpr uint16_t regPhasecalOverride = 0x004D;
constexpr uint16_t regRoiMode = 0x004F;
constexpr uint16_t regThresholdHigh = 0x0050;
constexpr uint16_t regThresholdLow = 0x0052;
constexpr uint16_t regManualSpads = 0x0054;
constexpr uint16_t regApertureAttenuation = 0x0057;
constexpr uint16_t regMmTimeoutA = 0x005A;
constexpr uint16_t regMmTimeoutB = 0x005C;
constexpr uint16_t regRangeTimeoutA = 0x005E;
constexpr uint16_t regVcselPeriodA = 0x0060;
constexpr uint16_t regRangeTimeoutB = 0x0061;
constexpr uint16_t regVcselPeriodB = 0x0063;
constexpr uint16_t regSigmaThreshold = 0x0064;
constexpr uint16_t regMinCountRate = 0x0066;
constexpr uint16_t regIntermeasurement = 0x006C;
constexpr uint16_t regGroupedHold0 = 0x0071;
constexpr uint16_t regSeedConfig = 0x0077;
constexpr uint16_t regWoiSd0 = 0x0078;
constexpr uint16_t regWoiSd1 = 0x0079;
constexpr uint16_t regInitialPhaseSd0 = 0x007A;
constexpr uint16_t regInitialPhaseSd1 = 0x007B;
constexpr uint16_t regGroupedHold1 = 0x007C;
constexpr uint16_t regQuantifier = 0x007E;
constexpr uint16_t regSequenceConfig = 0x0081;
constexpr uint16_t regGroupedHold = 0x0082;
constexpr uint16_t regInterruptClear = 0x0086;
constexpr uint16_t regModeStart = 0x0087;
constexpr uint16_t regRangeStatus = 0x0089;
constexpr uint16_t regOscCalibrate = 0x00DE;
constexpr uint16_t regFirmwareSystemStatus = 0x00E5;
constexpr uint16_t regPhasecalVcselStart = 0x00D8;
constexpr uint16_t regModelId = 0x010F;
constexpr uint16_t regFastOscFrequency = 0x0006;

String quote(const String& value) {
  String out = "\"";
  for (size_t i = 0; i < value.length(); ++i) {
    const uint8_t c = static_cast<uint8_t>(value[i]);
    if (c == '\"' || c == '\\') { out += '\\'; out += static_cast<char>(c); }
    else if (c < 32) { char escaped[7]; snprintf(escaped, sizeof(escaped), "\\u%04x", c); out += escaped; }
    else out += static_cast<char>(c);
  }
  out += '\"';
  return out;
}

bool elapsed(uint32_t now, uint32_t then, uint32_t interval) {
  return static_cast<uint32_t>(now - then) >= interval;
}
}

void SensorController::begin() {
  pinMode(pins::hcTrig, OUTPUT);
  digitalWrite(pins::hcTrig, LOW);
  pinMode(pins::hcEcho, INPUT);
  // INT is optional. XSHUT is safe to drive HIGH: it enables a connected
  // VL53L1X and is harmless when the optional line is left unconnected.
  pinMode(pins::tofInt, INPUT);
  pinMode(pins::tofXshut, OUTPUT);
  digitalWrite(pins::tofXshut, HIGH);
  pinsReady_ = true;
  running_ = false;
}

bool SensorController::start(uint32_t now) {
  if (!pinsReady_) begin();
  if (running_) return true;
  lastError_ = "";
  running_ = true;
  startedMs_ = now;
  tofI2cErrors_ = 0;
  tofValidSamples_ = 0;
  tofInvalidSamples_ = 0;
  tofReadyTimeouts_ = 0;
  tofConsecutiveErrors_ = 0;
  tofLastSuccessMs_ = 0;
  tofResponsive_ = false;
  tofReceived_ = false;
  hcValidSamples_ = 0;
  hcTimeouts_ = 0;
  hcInvalidSamples_ = 0;
  hcReceived_ = false;
  lastHcSampleMs_ = now - config::sensorHcIntervalMs;
  lastTofPollMs_ = now - config::sensorTofPollMs;
  lastTofMeasurementMs_ = now - config::sensorTofIntervalMs;

  pinMode(pins::tofXshut, OUTPUT);
  digitalWrite(pins::tofXshut, LOW);
  delay(2);
  digitalWrite(pins::tofXshut, HIGH);
  delay(5);

  Wire.begin(pins::tofSda, pins::tofScl, config::sensorI2cHz);
  Wire.setTimeOut(50);
  i2cInitialized_ = true;
  i2cScanComplete_ = scanI2c();
  tofPresent_ = false;
  for (uint8_t i = 0; i < i2cAddressCount_; ++i) {
    if (i2cAddresses_[i] == tofAddress) { tofPresent_ = true; break; }
  }
  tofInitialized_ = false;
  tofContinuous_ = false;
  tofCalibrated_ = false;
  tofStallSuspended_ = false;
  tofDisabledUntilMs_ = 0;
  tofLastReadyMs_ = now;
  if (tofPresent_) {
    tofInitialized_ = initTof();
    if (tofInitialized_) {
      tofContinuous_ = startTofContinuous();
      if (tofContinuous_) {
        tofResponsive_ = true;
        tofLastSuccessMs_ = now;
      } else {
        lastError_ = "vl53l1x_start_failed";
      }
    } else {
      lastError_ = "vl53l1x_init_failed";
    }
  } else {
    lastError_ = "vl53l1x_not_detected";
  }
  return true;
}

void SensorController::stop() {
  if (tofContinuous_) stopTofContinuous();
  tofStallSuspended_ = false;
  tofDisabledUntilMs_ = 0;
  running_ = false;
  digitalWrite(pins::hcTrig, LOW);
}

void SensorController::tofNoteError() {
  ++tofI2cErrors_;
  ++tofConsecutiveErrors_;
  if (tofConsecutiveErrors_ >= 3) tofResponsive_ = false;
}

void SensorController::tofNoteSuccess() {
  tofConsecutiveErrors_ = 0;
  tofResponsive_ = true;
  tofLastSuccessMs_ = millis();
}

uint32_t SensorController::tofErrorRatePerMin(uint32_t now) const {
  const uint32_t elapsed = now - startedMs_;
  if (elapsed < 1000) return 0;
  return static_cast<uint32_t>((static_cast<uint64_t>(tofI2cErrors_) * 60000ULL) / elapsed);
}

void SensorController::tick(uint32_t now) {
  if (!running_) return;
  if (elapsed(now, lastHcSampleMs_, config::sensorHcIntervalMs)) sampleUltrasonic(now);
  if (tofStallSuspended_) {
    if (int32_t(now - tofDisabledUntilMs_) >= 0) {
      tofStallSuspended_ = false;
      tofContinuous_ = startTofContinuous();
      tofLastReadyMs_ = now;
      lastTofMeasurementMs_ = now - config::sensorTofIntervalMs;
      ++tofRecoveries_;
      if (tofContinuous_) {
        lastError_ = "vl53l1x_stall_recovered";
      } else {
        lastError_ = "vl53l1x_stall_recovery_failed";
        tofStallSuspended_ = true;
        tofDisabledUntilMs_ = now + config::sensorTofRecoverRetryMs;
      }
    }
  } else if (tofContinuous_ && elapsed(now, lastTofPollMs_, config::sensorTofPollMs)) {
    lastTofPollMs_ = now;
    if (elapsed(now, lastTofMeasurementMs_, config::sensorTofIntervalMs) && tofDataReady()) {
      tofLastReadyMs_ = now;
      if (readTofMeasurement(now)) lastTofMeasurementMs_ = now;
    }
    if (tofContinuous_ && elapsed(now, tofLastReadyMs_, config::sensorTofStallRecoverMs)) {
      // The sensor is still ACKing I2C but has stopped producing data-ready.
      // Stop polling for a cooldown so a stuck bus cannot starve the main loop.
      stopTofContinuous();
      tofStallSuspended_ = true;
      tofDisabledUntilMs_ = now + config::sensorTofRecoverCooldownMs;
      ++tofRecoveries_;
      lastError_ = "vl53l1x_stall_suspended";
    }
  }
}

bool SensorController::scanI2c() {
  i2cAddressCount_ = 0;
  i2cScanTruncated_ = false;
  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    const uint8_t error = Wire.endTransmission();
    if (error == 0) {
      if (i2cAddressCount_ < sizeof(i2cAddresses_)) {
        i2cAddresses_[i2cAddressCount_++] = address;
      } else {
        i2cScanTruncated_ = true;
      }
    }
  }
  return true;
}

bool SensorController::tofWrite8(uint16_t reg, uint8_t value) {
  Wire.beginTransmission(tofAddress);
  Wire.write(static_cast<uint8_t>(reg >> 8));
  Wire.write(static_cast<uint8_t>(reg));
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool SensorController::tofWrite16(uint16_t reg, uint16_t value) {
  Wire.beginTransmission(tofAddress);
  Wire.write(static_cast<uint8_t>(reg >> 8));
  Wire.write(static_cast<uint8_t>(reg));
  Wire.write(static_cast<uint8_t>(value >> 8));
  Wire.write(static_cast<uint8_t>(value));
  return Wire.endTransmission() == 0;
}

bool SensorController::tofWrite32(uint16_t reg, uint32_t value) {
  Wire.beginTransmission(tofAddress);
  Wire.write(static_cast<uint8_t>(reg >> 8));
  Wire.write(static_cast<uint8_t>(reg));
  Wire.write(static_cast<uint8_t>(value >> 24));
  Wire.write(static_cast<uint8_t>(value >> 16));
  Wire.write(static_cast<uint8_t>(value >> 8));
  Wire.write(static_cast<uint8_t>(value));
  return Wire.endTransmission() == 0;
}

bool SensorController::tofRead8(uint16_t reg, uint8_t& value) {
  Wire.beginTransmission(tofAddress);
  Wire.write(static_cast<uint8_t>(reg >> 8));
  Wire.write(static_cast<uint8_t>(reg));
  if (Wire.endTransmission() != 0) return false;
  if (Wire.requestFrom(static_cast<int>(tofAddress), 1) != 1) return false;
  value = static_cast<uint8_t>(Wire.read());
  return true;
}

bool SensorController::tofRead16(uint16_t reg, uint16_t& value) {
  Wire.beginTransmission(tofAddress);
  Wire.write(static_cast<uint8_t>(reg >> 8));
  Wire.write(static_cast<uint8_t>(reg));
  if (Wire.endTransmission() != 0) return false;
  if (Wire.requestFrom(static_cast<int>(tofAddress), 2) != 2) return false;
  value = static_cast<uint16_t>(Wire.read()) << 8;
  value |= static_cast<uint8_t>(Wire.read());
  return true;
}

bool SensorController::tofReadBlock(uint16_t reg, uint8_t* data, size_t length) {
  if (length == 0 || length > 32) return false;
  Wire.beginTransmission(tofAddress);
  Wire.write(static_cast<uint8_t>(reg >> 8));
  Wire.write(static_cast<uint8_t>(reg));
  if (Wire.endTransmission() != 0) return false;
  if (Wire.requestFrom(static_cast<int>(tofAddress), static_cast<int>(length)) != length) return false;
  for (size_t i = 0; i < length; ++i) data[i] = static_cast<uint8_t>(Wire.read());
  return true;
}

bool SensorController::initTof() {
  uint16_t model = 0;
  if (!tofRead16(regModelId, model) || model != tofExpectedModel) return false;
  if (!tofWrite8(regSoftReset, 0x00)) return false;
  delayMicroseconds(100);
  if (!tofWrite8(regSoftReset, 0x01)) return false;
  delay(1);

  const uint32_t started = millis();
  uint8_t boot = 0;
  do {
    if (tofRead8(regFirmwareSystemStatus, boot) && (boot & 0x01)) break;
    delay(1);
  } while (static_cast<uint32_t>(millis() - started) < config::sensorTofBootTimeoutMs);
  if (!(boot & 0x01)) return false;

  uint8_t pad = 0;
  if (!tofRead8(regPadI2cHvExtsup, pad) || !tofWrite8(regPadI2cHvExtsup, pad | 0x01)) return false;
  if (!tofRead16(regFastOscFrequency, tofFastOscFrequency_) || tofFastOscFrequency_ == 0) return false;
  if (!tofRead16(regOscCalibrate, tofOscCalibrateValue_) || tofOscCalibrateValue_ == 0) return false;

  bool ok = true;
  ok = tofWrite16(regTargetTotalRate, tofTargetRate) && ok;
  ok = tofWrite8(regGpioStatus, 0x02) && ok;
  ok = tofWrite8(regSigmaPulseWidth, 8) && ok;
  ok = tofWrite8(0x0037, 16) && ok;
  ok = tofWrite8(regCrosstalkHeight, 1) && ok;
  ok = tofWrite8(regRangeIgnoreHeight, 0xFF) && ok;
  ok = tofWrite8(regRangeMinClip, 0) && ok;
  ok = tofWrite8(regConsistencyTolerance, 2) && ok;
  ok = tofWrite16(regThresholdHigh, 0) && ok;
  ok = tofWrite16(regThresholdLow, 0) && ok;
  ok = tofWrite8(regApertureAttenuation, 0x38) && ok;
  ok = tofWrite16(regSigmaThreshold, 360) && ok;
  ok = tofWrite16(regMinCountRate, 192) && ok;
  ok = tofWrite8(regGroupedHold0, 1) && ok;
  ok = tofWrite8(regGroupedHold1, 1) && ok;
  ok = tofWrite8(regQuantifier, 2) && ok;
  ok = tofWrite8(regGroupedHold, 0) && ok;
  ok = tofWrite8(regSeedConfig, 1) && ok;
  ok = tofWrite8(regSequenceConfig, 0x8B) && ok;
  ok = tofWrite16(regManualSpads, 200 << 8) && ok;
  ok = tofWrite8(regRoiMode, 2) && ok;
  if (!ok || !tofWrite8(regVcselPeriodA, 0x0F) || !tofWrite8(regVcselPeriodB, 0x0D) ||
      !tofWrite8(0x0069, 0xB8) || !tofWrite8(regWoiSd0, 0x0F) ||
      !tofWrite8(regWoiSd1, 0x0D) || !tofWrite8(regInitialPhaseSd0, 14) ||
      !tofWrite8(regInitialPhaseSd1, 14) || !tofSetTimingBudget(50000)) return false;

  uint16_t outerOffset = 0;
  if (!tofRead16(regMmOuterOffset, outerOffset) || !tofWrite16(regPartToPartOffset, outerOffset * 4)) return false;
  return true;
}

uint32_t SensorController::tofMacroPeriodUs(uint8_t vcselPeriod) const {
  if (tofFastOscFrequency_ == 0) return 0;
  const uint32_t pllPeriodUs = static_cast<uint32_t>((uint64_t(1) << 30) / tofFastOscFrequency_);
  const uint8_t vcselPeriodPclks = static_cast<uint8_t>((vcselPeriod + 1) << 1);
  uint32_t macro = (2304UL * pllPeriodUs) >> 6;
  macro = (macro * vcselPeriodPclks) >> 6;
  return macro;
}

uint32_t SensorController::timeoutUsToMclks(uint32_t timeoutUs, uint32_t macroPeriodUs) {
  if (!macroPeriodUs) return 0;
  return ((timeoutUs << 12) + (macroPeriodUs >> 1)) / macroPeriodUs;
}

uint32_t SensorController::encodeTimeout(uint32_t timeoutMclks) {
  if (!timeoutMclks) return 0;
  uint32_t lsByte = timeoutMclks - 1;
  uint16_t msByte = 0;
  while ((lsByte & 0xFFFFFF00UL) != 0) { lsByte >>= 1; ++msByte; }
  return (static_cast<uint32_t>(msByte) << 8) | (lsByte & 0xFF);
}

bool SensorController::tofSetTimingBudget(uint32_t budgetUs) {
  if (budgetUs <= tofTimingGuardUs) return false;
  uint32_t rangeTimeoutUs = (budgetUs - tofTimingGuardUs) / 2;
  if (rangeTimeoutUs > 1100000UL) return false;
  const uint32_t macroA = tofMacroPeriodUs(0x0F);
  const uint32_t macroB = tofMacroPeriodUs(0x0D);
  if (!macroA || !macroB) return false;
  uint32_t phaseTimeout = timeoutUsToMclks(1000, macroA);
  if (phaseTimeout > 0xFF) phaseTimeout = 0xFF;
  bool ok = tofWrite8(regPhasecalTimeout, static_cast<uint8_t>(phaseTimeout));
  ok = tofWrite16(regMmTimeoutA, encodeTimeout(timeoutUsToMclks(1, macroA))) && ok;
  ok = tofWrite16(regRangeTimeoutA, encodeTimeout(timeoutUsToMclks(rangeTimeoutUs, macroA))) && ok;
  ok = tofWrite16(regMmTimeoutB, encodeTimeout(timeoutUsToMclks(1, macroB))) && ok;
  ok = tofWrite16(regRangeTimeoutB, encodeTimeout(timeoutUsToMclks(rangeTimeoutUs, macroB))) && ok;
  return ok;
}

bool SensorController::startTofContinuous() {
  if (!tofInitialized_ || !tofOscCalibrateValue_) return false;
  bool ok = tofWrite32(regIntermeasurement, config::sensorTofIntervalMs * tofOscCalibrateValue_);
  ok = tofWrite8(regInterruptClear, 0x01) && ok;
  ok = tofWrite8(regModeStart, 0x40) && ok;
  return ok;
}

void SensorController::stopTofContinuous() {
  tofWrite8(regModeStart, 0x80);
  if (tofSavedVhvInit_) tofWrite8(regVhvInit, tofSavedVhvInit_);
  if (tofSavedVhvTimeout_) tofWrite8(regVhvTimeout, tofSavedVhvTimeout_);
  tofWrite8(regPhasecalOverride, 0x00);
  tofContinuous_ = false;
  tofCalibrated_ = false;
}

bool SensorController::tofHardReset() {
  pinMode(pins::tofXshut, OUTPUT);
  digitalWrite(pins::tofXshut, LOW);
  delay(5);
  digitalWrite(pins::tofXshut, HIGH);
  delay(10);
  tofInitialized_ = initTof();
  if (!tofInitialized_) return false;
  tofContinuous_ = startTofContinuous();
  return tofContinuous_;
}

bool SensorController::tofDataReady() {
  uint8_t status = 0;
  if (!tofRead8(regGpioStatus, status)) {
    tofNoteError();
    return false;
  }
  tofNoteSuccess();
  // VL53L1X GPIO__TIO_HV_STATUS reports data-ready active LOW.
  return (status & 0x01) == 0;
}

void SensorController::tofManualCalibration() {
  if (!tofRead8(regVhvInit, tofSavedVhvInit_) || !tofRead8(regVhvTimeout, tofSavedVhvTimeout_)) {
    ++tofI2cErrors_;
    return;
  }
  bool ok = tofWrite8(regVhvInit, tofSavedVhvInit_ & 0x7F);
  ok = tofWrite8(regVhvTimeout, static_cast<uint8_t>((tofSavedVhvTimeout_ & 0x03) + (3 << 2))) && ok;
  ok = tofWrite8(regPhasecalOverride, 0x01) && ok;
  uint8_t vcselStart = 0;
  ok = tofRead8(regPhasecalVcselStart, vcselStart) && ok;
  ok = tofWrite8(0x0047, vcselStart) && ok;
  if (!ok) ++tofI2cErrors_;
}

void SensorController::tofUpdateDss(uint16_t spads, uint16_t peakRate, uint16_t ambientRate) {
  if (!spads) { tofWrite16(regManualSpads, 0x8000); return; }
  uint32_t totalRate = static_cast<uint32_t>(peakRate) + ambientRate;
  if (totalRate > 0xFFFF) totalRate = 0xFFFF;
  totalRate <<= 16;
  totalRate /= spads;
  if (!totalRate) { tofWrite16(regManualSpads, 0x8000); return; }
  uint32_t required = (tofTargetRate << 16) / totalRate;
  if (required > 0xFFFF) required = 0xFFFF;
  tofWrite16(regManualSpads, static_cast<uint16_t>(required));
}

bool SensorController::readTofMeasurement(uint32_t now) {
  uint8_t data[17] = {};
  if (!tofReadBlock(regRangeStatus, data, sizeof(data))) {
    tofNoteError();
    return false;
  }
  tofNoteSuccess();
  tofRawStatus_ = data[0];
  const uint16_t spads = (static_cast<uint16_t>(data[3]) << 8) | data[4];
  const uint16_t ambient = (static_cast<uint16_t>(data[7]) << 8) | data[8];
  const uint16_t rangeRaw = (static_cast<uint16_t>(data[13]) << 8) | data[14];
  const uint16_t peak = (static_cast<uint16_t>(data[15]) << 8) | data[16];
  if (!tofCalibrated_) { tofManualCalibration(); tofCalibrated_ = true; }
  tofUpdateDss(spads, peak, ambient);
  if (!tofWrite8(regInterruptClear, 0x01)) ++tofI2cErrors_;

  tofReceived_ = true;
  tofTimestampMs_ = now;
  const bool valid = tofRawStatus_ == 9 && rangeRaw > 0 && rangeRaw <= config::sensorTofMaxRangeMm;
  tofLastValid_ = valid;
  if (valid) {
    tofRangeMm_ = static_cast<uint16_t>((static_cast<uint32_t>(rangeRaw) * 2011 + 0x0400) / 0x0800);
    tofLastValidMs_ = now;
    ++tofValidSamples_;
  } else {
    ++tofInvalidSamples_;
  }
  return true;
}

void SensorController::sampleUltrasonic(uint32_t now) {
  lastHcSampleMs_ = now;
  digitalWrite(pins::hcTrig, LOW);
  delayMicroseconds(2);
  digitalWrite(pins::hcTrig, HIGH);
  delayMicroseconds(10);
  digitalWrite(pins::hcTrig, LOW);
  const uint32_t pulse = pulseIn(pins::hcEcho, HIGH, config::sensorHcTimeoutUs);
  const uint32_t sampledAt = millis();
  hcReceived_ = true;
  hcTimestampMs_ = sampledAt;
  hcPulseUs_ = pulse;
  hcLastValid_ = false;
  if (!pulse) {
    ++hcTimeouts_;
    return;
  }
  if (pulse < config::sensorHcMinPulseUs || pulse > config::sensorHcMaxPulseUs) {
    ++hcInvalidSamples_;
    return;
  }
  const uint32_t distanceMm = (pulse * 343UL + 1000UL) / 2000UL;
  if (distanceMm < config::sensorHcMinRangeMm || distanceMm > config::sensorHcMaxRangeMm) {
    ++hcInvalidSamples_;
    return;
  }
  hcDistanceMm_ = static_cast<uint16_t>(distanceMm);
  hcLastValid_ = true;
  hcLastValidMs_ = sampledAt;
  ++hcValidSamples_;
}

const char* SensorController::tofStatusName(uint8_t status) {
  switch (status) {
    case 0: return "none";
    case 1: case 2: case 3: case 17: return "hardware_fail";
    case 4: return "signal_fail";
    case 5: return "out_of_bounds_fail";
    case 6: return "sigma_fail";
    case 7: return "wrap_target_fail";
    case 8: return "range_valid_min_clipped";
    case 9: return "range_valid";
    case 12: return "xtalk_signal_fail";
    case 13: return "min_range_fail";
    case 18: return "synchronization_interrupt";
    default: return "unknown";
  }
}

String SensorController::statusJson(uint32_t now, const SensorExternalState& external) const {
  const bool hcValid = hcLastValid_ && static_cast<uint32_t>(now - hcLastValidMs_) <= config::sensorStaleMs;
  const bool hcStale = hcLastValidMs_ != 0 && !hcValid;
  const bool tofValid = tofLastValid_ && static_cast<uint32_t>(now - tofLastValidMs_) <= config::sensorStaleMs;
  const bool tofStale = tofLastValidMs_ != 0 && !tofValid;
  const char* hcHealth = hcValid ? "OK" : (hcReceived_ ? "STALE" : "NO_DATA");
  const char* tofHealth = !tofPresent_ ? "ABSENT" : !tofInitialized_ ? "INIT_FAILED" :
      !tofResponsive_ ? "FAULT" : (tofValid ? "OK" : "STALE");
  const char* hlkHealth = !external.hlkEnabled ? "OFF" :
      external.hlkValid ? "OK" : (external.hlkStale ? "STALE" : "NO_DATA");
  const bool fault = strcmp(tofHealth, "ABSENT") == 0 || strcmp(tofHealth, "INIT_FAILED") == 0 ||
      strcmp(tofHealth, "FAULT") == 0 || strcmp(hcHealth, "NO_DATA") == 0;
  const bool degraded = fault || strcmp(hcHealth, "OK") != 0 || strcmp(tofHealth, "OK") != 0 ||
      strcmp(hlkHealth, "OK") != 0;
  const char* overall = fault ? "FAULT" : (degraded ? "DEGRADED" : "OK");
  const int hcCalMm = static_cast<int>(hcDistanceMm_) + config::hcOffsetMm;
  const int tofCalMm = static_cast<int>(tofRangeMm_) + config::tofOffsetMm;
  String s;
  s.reserve(3600);
  s = String("{\"enabled\":") + (running_ ? "true" : "false") +
      ",\"state\":" + quote(running_ ? "running" : "stopped") +
      ",\"health\":{\"overall\":" + quote(overall) +
      ",\"hc_sr04\":" + quote(hcHealth) +
      ",\"vl53l1x\":" + quote(tofHealth) +
      ",\"hlk\":" + quote(hlkHealth) + "}" +
      ",\"last_error\":" + quote(lastError_) +
      ",\"configured\":{\"hc_trig_gpio\":" + pins::hcTrig +
      ",\"hc_echo_gpio\":" + pins::hcEcho +
      ",\"hc_echo_divider_required\":true,\"tof_sda_gpio\":" + pins::tofSda +
      ",\"tof_scl_gpio\":" + pins::tofScl + ",\"tof_int_gpio\":" + pins::tofInt +
      ",\"tof_xshut_gpio\":" + pins::tofXshut + "}" +
      ",\"calibration\":{\"hc_offset_mm\":" + config::hcOffsetMm +
      ",\"tof_offset_mm\":" + config::tofOffsetMm +
      ",\"hlk_min_range_cm\":" + config::hlkMinRangeCm + "}" +
      ",\"i2c\":{\"initialized\":" + (i2cInitialized_ ? "true" : "false") +
      ",\"scan_complete\":" + (i2cScanComplete_ ? "true" : "false") +
      ",\"scan_truncated\":" + (i2cScanTruncated_ ? "true" : "false") + ",\"addresses\":[";
  for (uint8_t i = 0; i < i2cAddressCount_; ++i) {
    if (i) s += ',';
    s += i2cAddresses_[i];
  }
  s += String("]},\"stats\":{\"started_ms\":") + startedMs_ +
      ",\"tof_i2c_errors\":" + tofI2cErrors_ +
      ",\"tof_error_rate_per_min\":" + tofErrorRatePerMin(now) +
      ",\"tof_consecutive_errors\":" + tofConsecutiveErrors_ +
      ",\"tof_last_success_ms\":" + tofLastSuccessMs_ +
      ",\"tof_recoveries\":" + tofRecoveries_ +
      ",\"tof_hard_resets\":" + tofHardResets_ +
      ",\"tof_stall_suspended\":" + (tofStallSuspended_ ? "true" : "false") +
      ",\"tof_responsive\":" + (tofResponsive_ ? "true" : "false") + "}" +
      ",\"hc_sr04\":{\"configured\":true,\"received\":" + (hcReceived_ ? "true" : "false") +
      ",\"valid\":" + (hcValid ? "true" : "false") +
      ",\"stale\":" + (hcStale ? "true" : "false") + ",\"last_sample_valid\":" +
      (hcLastValid_ ? "true" : "false") + ",\"timestamp_ms\":" +
      (hcReceived_ ? String(hcTimestampMs_) : String("null")) + ",\"age_ms\":" +
      (hcLastValidMs_ ? String(static_cast<uint32_t>(now - hcLastValidMs_)) : String("null")) +
      ",\"pulse_us\":" + hcPulseUs_ + ",\"distance_mm\":" +
      (hcValid ? String(hcDistanceMm_) : String("null")) + ",\"distance_cm\":" +
      (hcValid ? String(hcDistanceMm_ / 10.0f, 1) : String("null")) +
      ",\"distance_cal_mm\":" + (hcValid ? String(hcCalMm) : String("null")) +
      ",\"distance_cal_cm\":" + (hcValid ? String(hcCalMm / 10.0f, 1) : String("null")) +
      ",\"valid_samples\":" + hcValidSamples_ + ",\"timeouts\":" + hcTimeouts_ +
      ",\"invalid_samples\":" + hcInvalidSamples_ +
      ",\"range_min_mm\":" + config::sensorHcMinRangeMm +
      ",\"range_max_mm\":" + config::sensorHcMaxRangeMm + "}" +
      ",\"vl53l1x\":{\"address\":41,\"present\":" + (tofPresent_ ? "true" : "false") +
      ",\"initialized\":" + (tofInitialized_ ? "true" : "false") +
      ",\"continuous\":" + (tofContinuous_ ? "true" : "false") + ",\"received\":" +
      (tofReceived_ ? "true" : "false") + ",\"valid\":" + (tofValid ? "true" : "false") +
      ",\"stale\":" + (tofStale ? "true" : "false") + ",\"responsive\":" +
      (tofResponsive_ ? "true" : "false") + ",\"last_sample_valid\":" +
      (tofLastValid_ ? "true" : "false") + ",\"timestamp_ms\":" +
      (tofReceived_ ? String(tofTimestampMs_) : String("null")) + ",\"age_ms\":" +
      (tofLastValidMs_ ? String(static_cast<uint32_t>(now - tofLastValidMs_)) : String("null")) +
      ",\"distance_mm\":" + (tofValid ? String(tofRangeMm_) : String("null")) +
      ",\"distance_cm\":" + (tofValid ? String(tofRangeMm_ / 10.0f, 1) : String("null")) +
      ",\"distance_cal_mm\":" + (tofValid ? String(tofCalMm) : String("null")) +
      ",\"distance_cal_cm\":" + (tofValid ? String(tofCalMm / 10.0f, 1) : String("null")) +
      ",\"raw_status\":" + tofRawStatus_ + ",\"status\":" + quote(tofStatusName(tofRawStatus_)) +
      ",\"valid_samples\":" + tofValidSamples_ + ",\"invalid_samples\":" + tofInvalidSamples_ +
      ",\"i2c_errors\":" + tofI2cErrors_ + ",\"ready_timeouts\":" + tofReadyTimeouts_ + "}" +
      ",\"hlk\":{\"enabled\":" + (external.hlkEnabled ? "true" : "false") +
      ",\"valid\":" + (external.hlkValid ? "true" : "false") +
      ",\"stale\":" + (external.hlkStale ? "true" : "false") +
      ",\"frames\":" + external.hlkFrames +
      ",\"age_ms\":" + external.hlkAgeMs +
      ",\"distance_cm\":" + external.hlkDistanceCm +
      ",\"energy\":" + external.hlkEnergy +
      ",\"target_state\":" + external.hlkTargetState +
      ",\"min_range_cm\":" + config::hlkMinRangeCm + "}}";
  return s;
}
