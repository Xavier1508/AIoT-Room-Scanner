#pragma once

#include <Arduino.h>
#include <stdint.h>

// Sensor bring-up is deliberately explicit. begin() only makes the HC-SR04
// trigger safe and configures optional input pins; start() performs I2C scan,
// VL53L1X initialization and periodic measurements.
class SensorController {
 public:
  void begin();
  bool start(uint32_t now);
  void stop();
  void tick(uint32_t now);
  bool running() const { return running_; }
  String statusJson(uint32_t now) const;

 private:
  bool scanI2c();
  bool initTof();
  bool startTofContinuous();
  void stopTofContinuous();
  bool tofDataReady();
  bool readTofMeasurement(uint32_t now);
  void sampleUltrasonic(uint32_t now);

  bool tofWrite8(uint16_t reg, uint8_t value);
  bool tofWrite16(uint16_t reg, uint16_t value);
  bool tofWrite32(uint16_t reg, uint32_t value);
  bool tofRead8(uint16_t reg, uint8_t& value);
  bool tofRead16(uint16_t reg, uint16_t& value);
  bool tofReadBlock(uint16_t reg, uint8_t* data, size_t length);
  bool tofSetTimingBudget(uint32_t budgetUs);
  uint32_t tofMacroPeriodUs(uint8_t vcselPeriod) const;
  static uint32_t encodeTimeout(uint32_t timeoutMclks);
  static uint32_t timeoutUsToMclks(uint32_t timeoutUs, uint32_t macroPeriodUs);
  void tofUpdateDss(uint16_t spads, uint16_t peakRate, uint16_t ambientRate);
  void tofManualCalibration();
  static const char* tofStatusName(uint8_t status);

  bool pinsReady_ = false;
  bool running_ = false;
  bool i2cInitialized_ = false;
  bool i2cScanComplete_ = false;
  bool i2cScanTruncated_ = false;
  uint8_t i2cAddresses_[16] = {};
  uint8_t i2cAddressCount_ = 0;

  bool tofPresent_ = false;
  bool tofInitialized_ = false;
  bool tofContinuous_ = false;
  bool tofCalibrated_ = false;
  uint8_t tofRawStatus_ = 0;
  uint16_t tofRangeMm_ = 0;
  uint16_t tofFastOscFrequency_ = 0;
  uint16_t tofOscCalibrateValue_ = 0;
  uint8_t tofSavedVhvInit_ = 0;
  uint8_t tofSavedVhvTimeout_ = 0;
  bool tofReceived_ = false;
  bool tofLastValid_ = false;
  uint32_t tofTimestampMs_ = 0;
  uint32_t tofLastValidMs_ = 0;
  uint32_t tofValidSamples_ = 0;
  uint32_t tofInvalidSamples_ = 0;
  uint32_t tofI2cErrors_ = 0;
  uint32_t tofReadyTimeouts_ = 0;

  bool hcReceived_ = false;
  bool hcLastValid_ = false;
  uint16_t hcDistanceMm_ = 0;
  uint32_t hcPulseUs_ = 0;
  uint32_t hcTimestampMs_ = 0;
  uint32_t hcLastValidMs_ = 0;
  uint32_t hcValidSamples_ = 0;
  uint32_t hcTimeouts_ = 0;
  uint32_t hcInvalidSamples_ = 0;
  uint32_t lastHcSampleMs_ = 0;
  uint32_t lastTofPollMs_ = 0;
  uint32_t lastTofMeasurementMs_ = 0;
  String lastError_;
};
