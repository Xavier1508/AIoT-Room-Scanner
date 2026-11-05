#pragma once

#include <Arduino.h>
#include <esp_http_server.h>
#include "settings.h"
#include "wifi_scan.h"

class App;

class Network {
 public:
  void begin(App& app, const SettingsStore& settings);
  void reconfigure();
  void tick(uint32_t now);
  bool connected() const;
  bool webReady() const { return server_ != nullptr; }
  uint32_t attempts() const { return attempts_; }
  const char* csrf() const { return csrf_; }
  bool startScan();
  void cancelScan();
  bool scanning() const { return scanRunning_; }
  const char* scanState() const { return scanState_; }
  uint32_t scanId() const { return scanId_; }
  String scanJson(int page = -1) const;
 private:
  bool startServer();
  bool authenticate(httpd_req_t* request);
  bool authorizeMutation(httpd_req_t* request);
  static esp_err_t rootHandler(httpd_req_t* request);
  static esp_err_t statusHandler(httpd_req_t* request);
  static esp_err_t sessionHandler(httpd_req_t* request);
  static esp_err_t commandHandler(httpd_req_t* request);
  static esp_err_t otaHandler(httpd_req_t* request);
  App* app_ = nullptr;
  const SettingsStore* settings_ = nullptr;
  httpd_handle_t server_ = nullptr;
  bool wasConnected_ = false, attempted_ = false, mdns_ = false;
  uint32_t lastAttempt_ = 0, attempts_ = 0, authBlockedUntil_ = 0;
  unsigned authFailures_ = 0;
  char authorization_[192] = {}, csrf_[33] = {};
  WifiScanList scanList_;
  bool scanRunning_ = false, scanInputLimited_ = false;
  const char* scanState_ = "idle";
  uint32_t scanStarted_ = 0, scanCompleted_ = 0, scanId_ = 0;
  int scanObserved_ = 0;
};
