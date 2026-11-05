#include "network.h"

#include <ESPmDNS.h>
#include <WiFi.h>
#include <esp_app_format.h>
#include <esp_ota_ops.h>
#include <esp_system.h>
#include <esp_wifi.h>
#include <mbedtls/base64.h>
#include <mbedtls/sha256.h>
#include <string.h>
#include "app.h"
#include "commands.h"
#include "config.h"
#include "web_page.h"

namespace {
void headers(httpd_req_t* request) {
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  httpd_resp_set_hdr(request, "X-Content-Type-Options", "nosniff");
  httpd_resp_set_hdr(request, "X-Frame-Options", "DENY");
}
esp_err_t json(httpd_req_t* request, const char* status, const String& body) {
  headers(request); httpd_resp_set_status(request, status);
  httpd_resp_set_type(request, "application/json");
  return httpd_resp_send(request, body.c_str(), body.length());
}
String header(httpd_req_t* request, const char* name, size_t limit = 192) {
  size_t n = httpd_req_get_hdr_value_len(request, name);
  if (!n || n > limit) return "";
  char value[256];
  if (n >= sizeof(value) || httpd_req_get_hdr_value_str(request, name, value, sizeof(value)) != ESP_OK) return "";
  return String(value);
}
bool constantEqual(const String& actual, const char* expected) {
  size_t n = strlen(expected);
  unsigned difference = actual.length() ^ n;
  for (size_t i = 0; i < n; ++i) difference |= uint8_t(i < actual.length() ? actual[i] : 0) ^ uint8_t(expected[i]);
  return difference == 0;
}
bool receive(httpd_req_t* request, uint8_t* out, size_t size, uint32_t began) {
  size_t got = 0;
  while (got < size) {
    if (uint32_t(millis() - began) > config::otaReceiveLimitMs) return false;
    int n = httpd_req_recv(request, reinterpret_cast<char*>(out + got), size - got);
    if (n <= 0) return false;  // Bounded one-second socket timeout, no endless retry.
    got += size_t(n);
  }
  return true;
}
}

void Network::begin(App& app, const SettingsStore& settings) {
  app_ = &app; settings_ = &settings;
  WiFi.persistent(false); WiFi.setAutoReconnect(false);
  reconfigure();
}
void Network::reconfigure() {
  cancelScan();
  scanList_.clear(); scanState_ = "idle"; scanObserved_ = 0;
  if (server_) { httpd_stop(server_); server_ = nullptr; }
  if (mdns_) { MDNS.end(); mdns_ = false; }
  WiFi.disconnect(false, false);
  wasConnected_ = false; attempted_ = false; attempts_ = 0;
  memset(authorization_, 0, sizeof(authorization_));
  if (!settings_->configured()) { WiFi.mode(WIFI_OFF); return; }
  WiFi.mode(WIFI_STA); WiFi.setHostname(config::hostname); WiFi.setSleep(false);
  char raw[80];
  snprintf(raw, sizeof(raw), "%s:%s", config::webUser, settings_->value().webPassword);
  unsigned char encoded[128]; size_t length = 0;
  mbedtls_base64_encode(encoded, sizeof(encoded), &length,
                       reinterpret_cast<const unsigned char*>(raw), strlen(raw));
  snprintf(authorization_, sizeof(authorization_), "Basic %.*s", int(length), encoded);
  volatile char* p = raw; for (size_t i = 0; i < sizeof(raw); ++i) p[i] = 0;
  memset(encoded, 0, sizeof(encoded));
  for (unsigned i = 0; i < 4; ++i) snprintf(csrf_ + i * 8, 9, "%08lx", static_cast<unsigned long>(esp_random()));
  authFailures_ = 0; authBlockedUntil_ = 0;
}
bool Network::connected() const { return WiFi.status() == WL_CONNECTED; }

bool Network::startScan() {
  if (scanRunning_) return false;
  scanList_.clear(); scanObserved_ = 0; scanInputLimited_ = false;
  scanState_ = "running"; scanStarted_ = millis(); scanCompleted_ = 0; ++scanId_;
  if (!WiFi.mode(WIFI_STA)) { scanState_ = "failed"; return false; }
  WiFi.scanDelete();
  // async=true, show_hidden=true, PASSIVE=true. No probes or IP/port scan.
  const int16_t result = WiFi.scanNetworks(true, true, true, 300);
  scanRunning_ = result == WIFI_SCAN_RUNNING || result >= 0;
  if (!scanRunning_) {
    scanState_ = "failed";
    if (!settings_->configured()) WiFi.mode(WIFI_OFF);
  }
  return scanRunning_;
}

void Network::cancelScan() {
  if (!scanRunning_) return;
  esp_wifi_scan_stop(); WiFi.scanDelete();
  scanRunning_ = false; scanState_ = "cancelled";
  if (!settings_->configured()) WiFi.mode(WIFI_OFF);
}

String Network::scanJson(int page) const {
  String result; result.reserve(1400);
  result = String("{\"ok\":true,\"wifi_scan\":{\"state\":") + jsonQuote(scanState_) +
      ",\"scan_id\":" + scanId_ + ",\"passive\":true,\"band\":\"2.4GHz\",\"completed_ms\":" + scanCompleted_ +
      ",\"observed_ap_count\":" + scanObserved_ + ",\"hidden_ap_count\":" + scanList_.hidden() +
      ",\"retained_networks\":" + scanList_.count() + ",\"pages\":" + ((scanList_.count() + WifiScanList::pageSize - 1) / WifiScanList::pageSize) +
      ",\"truncated\":" + (scanList_.truncated() || scanInputLimited_ ? "true" : "false") +
      ",\"page\":" + (page < 0 ? String("null") : String(page)) + ",\"networks\":[";
  if (page >= 0 && page < 8 && strcmp(scanState_, "done") == 0) {
    const size_t first = size_t(page) * WifiScanList::pageSize;
    for (size_t i = first; i < first + WifiScanList::pageSize && i < scanList_.count(); ++i) {
      const WifiNetwork& network = *scanList_.at(i);
      char hex[65]; WifiScanList::hexSsid(network, hex);
      if (i != first) result += ',';
      // SSIDs are untrusted arbitrary bytes: hex on the wire, escaped on PC.
      result += String("{\"ssid_hex\":\"") + hex + "\",\"rssi_dbm\":" + network.rssi +
          ",\"channel\":" + network.channel + ",\"auth\":" + network.auth + "}";
    }
  }
  result += "]}}";
  return result;
}

void Network::tick(uint32_t now) {
  if (scanRunning_) {
    const int16_t count = WiFi.scanComplete();
    if (count == WIFI_SCAN_RUNNING && uint32_t(now - scanStarted_) < config::wifiScanTimeoutMs) return;
    scanRunning_ = false;
    if (count >= 0) {
      scanObserved_ = count; scanInputLimited_ = count > 256;
      for (int i = 0; i < count && i < 256; ++i) {
        String ssid = WiFi.SSID(uint8_t(i));
        scanList_.add(ssid.c_str(), ssid.length(), WiFi.RSSI(uint8_t(i)),
                      uint8_t(WiFi.channel(uint8_t(i))), uint8_t(WiFi.encryptionType(uint8_t(i))));
      }
      scanList_.sortBySignal(); scanState_ = "done"; scanCompleted_ = now;
    } else { esp_wifi_scan_stop(); scanState_ = "failed"; }
    WiFi.scanDelete();
    if (!settings_->configured()) WiFi.mode(WIFI_OFF);
    return;
  }
  if (!settings_->configured()) return;
  const bool up = connected();
  if (up) {
    if (!wasConnected_) {
      if (!mdns_) { mdns_ = MDNS.begin(config::hostname); if (mdns_) MDNS.addService("http", "tcp", 80); }
      startServer();
    } else if (!server_) startServer();
  } else {
    if (wasConnected_) {
      if (server_) { httpd_stop(server_); server_ = nullptr; }
      if (mdns_) { MDNS.end(); mdns_ = false; }
    }
    if (!attempted_ || uint32_t(now - lastAttempt_) >= config::wifiRetryMs) {
      attempted_ = true; lastAttempt_ = now; ++attempts_;
      WiFi.disconnect(false, false);
      WiFi.begin(settings_->value().ssid, settings_->value().wifiPassword);
    }
  }
  wasConnected_ = up;
}

bool Network::startServer() {
  if (server_) return true;
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.stack_size = 8192; cfg.core_id = 0; cfg.max_uri_handlers = 8;
  cfg.max_open_sockets = 4; cfg.lru_purge_enable = true;
  cfg.recv_wait_timeout = 1; cfg.send_wait_timeout = 2;
  if (httpd_start(&server_, &cfg) != ESP_OK) { server_ = nullptr; return false; }
  struct Route { const char* uri; httpd_method_t method; esp_err_t (*handler)(httpd_req_t*); };
  const Route routes[] = {{"/", HTTP_GET, rootHandler}, {"/api/status", HTTP_GET, statusHandler},
      {"/api/session", HTTP_GET, sessionHandler}, {"/api/command", HTTP_POST, commandHandler},
      {"/api/ota", HTTP_POST, otaHandler}};
  for (const auto& route : routes) {
    httpd_uri_t uri = {};
    uri.uri = route.uri; uri.method = route.method; uri.handler = route.handler; uri.user_ctx = this;
    if (httpd_register_uri_handler(server_, &uri) != ESP_OK) {
      httpd_stop(server_); server_ = nullptr; return false;
    }
  }
  return true;
}

bool Network::authenticate(httpd_req_t* request) {
  if (authBlockedUntil_ && int32_t(millis() - authBlockedUntil_) < 0) {
    json(request, "429 Too Many Requests", "{\"message\":\"auth_cooldown\"}"); return false;
  }
  if (constantEqual(header(request, "Authorization"), authorization_) && authorization_[0]) {
    authFailures_ = 0; return true;
  }
  if (++authFailures_ >= 5) { authBlockedUntil_ = millis() + 15000; authFailures_ = 0; }
  httpd_resp_set_hdr(request, "WWW-Authenticate", "Basic realm=\"AIoT local device\", charset=\"UTF-8\"");
  json(request, "401 Unauthorized", "{\"message\":\"authentication_required\"}"); return false;
}
bool Network::authorizeMutation(httpd_req_t* request) {
  if (!authenticate(request)) return false;
  if (!constantEqual(header(request, "X-CSRF-Token", 64), csrf_)) {
    json(request, "403 Forbidden", "{\"message\":\"csrf_required\"}"); return false;
  }
  const String host = header(request, "Host", 100);
  const String ip = WiFi.localIP().toString();
  const String mdns = String(config::hostname) + ".local";
  if (!(host == ip || host == ip + ":80" || host == mdns || host == mdns + ":80")) {
    json(request, "403 Forbidden", "{\"message\":\"unexpected_host\"}"); return false;
  }
  const String origin = header(request, "Origin", 140);
  if (origin.length() && origin != String("http://") + host) {
    json(request, "403 Forbidden", "{\"message\":\"cross_origin_rejected\"}"); return false;
  }
  return true;
}

esp_err_t Network::rootHandler(httpd_req_t* request) {
  auto& self = *static_cast<Network*>(request->user_ctx);
  if (!self.authenticate(request)) return ESP_FAIL;
  headers(request);
  httpd_resp_set_hdr(request, "Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'; connect-src 'self'");
  httpd_resp_set_type(request, "text/html; charset=utf-8");
  return httpd_resp_send(request, webPage, sizeof(webPage) - 1);
}
esp_err_t Network::statusHandler(httpd_req_t* request) {
  auto& self = *static_cast<Network*>(request->user_ctx);
  if (!self.authenticate(request)) return ESP_FAIL;
  return json(request, "200 OK", self.app_->statusJson());
}
esp_err_t Network::sessionHandler(httpd_req_t* request) {
  auto& self = *static_cast<Network*>(request->user_ctx);
  if (!self.authenticate(request)) return ESP_FAIL;
  return json(request, "200 OK", String("{\"csrf\":") + jsonQuote(self.csrf_) + "}");
}
esp_err_t Network::commandHandler(httpd_req_t* request) {
  auto& self = *static_cast<Network*>(request->user_ctx);
  if (!self.authorizeMutation(request)) return ESP_FAIL;
  const String type = header(request, "Content-Type", 80);
  if (!type.startsWith("text/plain") || request->content_len == 0 || request->content_len > 48) {
    json(request, "400 Bad Request", "{\"message\":\"expected_short_text_command\"}"); return ESP_FAIL;
  }
  char body[49] = {};
  if (!receive(request, reinterpret_cast<uint8_t*>(body), request->content_len, millis())) {
    json(request, "408 Request Timeout", "{\"message\":\"request_incomplete\"}"); return ESP_FAIL;
  }
  // Embedded NULs and trailing command parameters must not be accepted.
  Command command = strlen(body) == request->content_len ? parseCommand(body) : Command::Invalid;
  if (command == Command::Invalid || command == Command::Help || command == Command::Status) {
    return json(request, "400 Bad Request", "{\"message\":\"unknown_command_no_action\"}");
  }
  uint32_t id = 0;
  if (!self.app_->enqueue(command, id)) return json(request, "409 Conflict", "{\"message\":\"ota_locked_or_queue_full\"}");
  return json(request, "202 Accepted", String("{\"accepted\":true,\"command_id\":") + id +
              ",\"message\":\"queued_not_physical_success\"}");
}

esp_err_t Network::otaHandler(httpd_req_t* request) {
  auto& self = *static_cast<Network*>(request->user_ctx);
  if (!self.authorizeMutation(request)) return ESP_FAIL;
  const auto* partition = esp_ota_get_next_update_partition(nullptr);
  if (header(request, "Content-Type", 80) != "application/octet-stream" ||
      header(request, "X-Firmware-Name", 80) != "firmware.bin") {
    json(request, "400 Bad Request", "{\"message\":\"application_firmware_bin_only\"}"); return ESP_FAIL;
  }
  constexpr size_t prefixSize = sizeof(esp_image_header_t) + sizeof(esp_image_segment_header_t) + sizeof(esp_app_desc_t);
  if (!partition || request->content_len < prefixSize || request->content_len > partition->size) {
    json(request, "413 Payload Too Large", "{\"message\":\"image_size_or_ota_partition_invalid\"}"); return ESP_FAIL;
  }
  if (!self.app_->beginOta()) {
    json(request, "409 Conflict", "{\"message\":\"cannot_enter_safe_ota\"}"); return ESP_FAIL;
  }
  const uint32_t began = millis();
  uint8_t buffer[2048];
  auto fail = [&](const char* reason) {
    self.app_->finishOta(false, reason);
    json(request, "400 Bad Request", String("{\"message\":") + jsonQuote(reason) + ",\"actuators_disarmed\":true}");
    return ESP_FAIL;
  };
  if (!receive(request, buffer, prefixSize, began)) return fail("incomplete_image_header");
  esp_image_header_t image; esp_app_desc_t description;
  memcpy(&image, buffer, sizeof(image));
  memcpy(&description, buffer + sizeof(image) + sizeof(esp_image_segment_header_t), sizeof(description));
  if (image.magic != ESP_IMAGE_HEADER_MAGIC || image.chip_id != ESP_CHIP_ID_ESP32S3 ||
      image.segment_count == 0 || image.segment_count > ESP_IMAGE_MAX_SEGMENTS ||
      description.magic_word != ESP_APP_DESC_MAGIC_WORD) return fail("not_an_esp32s3_application_image");
  const String expectedSha = header(request, "X-Firmware-SHA256", 64);
  if (expectedSha.length() && expectedSha.length() != 64) return fail("invalid_sha256_header");
  esp_ota_handle_t handle = 0;
  esp_err_t error = esp_ota_begin(partition, request->content_len, &handle);
  if (error != ESP_OK) return fail("ota_begin_failed");
  mbedtls_sha256_context sha;
  mbedtls_sha256_init(&sha); mbedtls_sha256_starts_ret(&sha, 0);
  size_t total = prefixSize;
  mbedtls_sha256_update_ret(&sha, buffer, prefixSize);
  error = esp_ota_write(handle, buffer, prefixSize);
  while (error == ESP_OK && total < request->content_len) {
    size_t n = request->content_len - total;
    if (n > sizeof(buffer)) n = sizeof(buffer);
    if (!receive(request, buffer, n, began)) { error = ESP_ERR_TIMEOUT; break; }
    mbedtls_sha256_update_ret(&sha, buffer, n);
    error = esp_ota_write(handle, buffer, n); total += n;
  }
  uint8_t digest[32]; char hex[65];
  mbedtls_sha256_finish_ret(&sha, digest); mbedtls_sha256_free(&sha);
  for (unsigned i = 0; i < 32; ++i) snprintf(hex + 2 * i, 3, "%02x", digest[i]);
  if (error != ESP_OK || total != request->content_len) { esp_ota_abort(handle); return fail("upload_incomplete_or_flash_write_failed"); }
  if (expectedSha.length() && !constantEqual(expectedSha, hex)) { esp_ota_abort(handle); return fail("sha256_mismatch"); }
  error = esp_ota_end(handle);  // IDF validates image checksum/hash and chip compatibility.
  if (error != ESP_OK) return fail("image_verification_failed");
  if (esp_ota_set_boot_partition(partition) != ESP_OK) return fail("boot_partition_selection_failed");
  self.app_->finishOta(true, "verified");
  return json(request, "200 OK", String("{\"ok\":true,\"reboot_pending\":true,\"sha256\":") +
              jsonQuote(hex) + ",\"message\":\"verify_new_version_and_idle_after_reboot\"}");
}
