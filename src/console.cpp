#include "console.h"
#include "app.h"

void Console::begin(App& app) {
  app_ = &app;
  // Start the board's native USB PHY using the core's supported HWCDC layer.
  // Larger queues cover a full provision record/status. Avoid zero TX timeout:
  // the pinned core uses a millisecond retry counter internally.
  Serial.setRxBufferSize(1024);
  Serial.setTxBufferSize(2048);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(2);
  ready_ = true;
  output_.reserve(8192);
}
void Console::send(const String& json) {
  // Never echo requests, especially provisioning payloads. Bound outgoing RAM.
  if (output_.length() - sent_ + json.length() > 16384) return;
  if (sent_) { output_.remove(0, sent_); sent_ = 0; }
  output_ += "AIOT "; output_ += json; output_ += '\n';
}
void Console::tick() {
  if (!ready_) return;
  uint8_t bytes[128];
  const int waiting = Serial.available();
  const int count = waiting > 0 ? Serial.read(bytes, waiting > int(sizeof(bytes)) ? sizeof(bytes) : size_t(waiting)) : 0;
  for (int index = 0; index < count; ++index) {
    char c = char(bytes[index]);
    if (c == '\r') continue;
    if (c == '\n') {
      if (overflow_) send("{\"ok\":false,\"message\":\"input_too_long\"}");
      else if (used_) { input_[used_] = 0; send(app_->serialLine(input_)); }
      volatile char* p = input_;
      for (size_t i = 0; i < sizeof(input_); ++i) p[i] = 0;
      used_ = 0; overflow_ = false;
    } else if (uint8_t(c) < 32 && c != '\t') overflow_ = true;
    else if (used_ < sizeof(input_) - 1 && !overflow_) input_[used_++] = c;
    else overflow_ = true;
  }
  // HWCDC's bool conversion also services its native-USB connection handshake.
  const bool connected = static_cast<bool>(Serial);
  if (connected && sent_ < output_.length()) {
    size_t n = output_.length() - sent_;
    if (n > 64) n = 64;
    const int available = Serial.availableForWrite();
    if (available > 0) {
      if (n > size_t(available)) n = size_t(available);
      sent_ += Serial.write(reinterpret_cast<const uint8_t*>(output_.c_str()) + sent_, n);
    }
  }
  if (sent_ == output_.length()) { output_ = ""; sent_ = 0; }
}
