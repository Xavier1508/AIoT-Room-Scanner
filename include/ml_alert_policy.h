#pragma once

#include <stdint.h>

#include "config.h"

// Hybrid AI alert policy: the model classifies empty/human, while HLK provides
// the fast presence edge. The HLK 30-75 cm parking-sensor rule keeps priority
// whenever it is actively beeping; this policy only drives the room-presence
// buzzer outside that near-field ramp.
//
// Pure C++11 (no Arduino/String) so the host selftests can exercise every
// transition without hardware.

enum class MlAlertMode : uint8_t {
  Idle,
  Provisional,
  Confirmed,
};

inline const char* mlAlertModeName(MlAlertMode mode) {
  switch (mode) {
    case MlAlertMode::Provisional: return "provisional";
    case MlAlertMode::Confirmed: return "confirmed";
    default: return "idle";
  }
}

struct MlAlertInputs {
  uint32_t now = 0;
  bool enabled = false;
  bool muted = false;
  const char* muteReason = "muted";
  bool modelReady = false;
  bool windowReady = false;
  bool modelHuman = false;
  float confidence = 0.0f;
  uint8_t movingEnergy = 0;
  uint32_t hlkTimestampMs = 0;
  bool ruleActive = false;
};

struct MlAlertOutput {
  MlAlertMode mode = MlAlertMode::Idle;
  bool active = false;
  bool beep = false;
  const char* reason = "idle";
  bool transitioned = false;
};

class MlAlertPolicy {
 public:
  void reset() {
    mode_ = MlAlertMode::Idle;
    triggerStartMs_ = 0;
    releaseStartMs_ = 0;
    lastBeepMs_ = 0;
    lastVetoMs_ = 0;
    beeped_ = false;
    movingFrames_ = 0;
    lastHlkTimestampMs_ = 0;
  }

  void resetCounters() {
    triggerCount_ = 0;
    confirmCount_ = 0;
    vetoCount_ = 0;
    releaseCount_ = 0;
    unconfirmedCount_ = 0;
  }

  MlAlertOutput update(const MlAlertInputs& in) {
    MlAlertOutput out;
    if (!in.enabled) {
      transition(MlAlertMode::Idle, in.now, out);
      out.reason = "disabled";
      releaseStartMs_ = 0;
      movingFrames_ = 0;
      return out;
    }
    if (in.muted) {
      transition(MlAlertMode::Idle, in.now, out);
      out.reason = in.muteReason;
      releaseStartMs_ = 0;
      movingFrames_ = 0;
      return out;
    }
    if (in.ruleActive) {
      // The near-field parking rule owns the buzzer. Keep the AI state but
      // restart its confirmation window when the rule releases.
      if (mode_ != MlAlertMode::Idle) {
        triggerStartMs_ = in.now;
        releaseStartMs_ = 0;
      }
      out.mode = mode_;
      out.active = false;
      out.reason = "rule_priority";
      return out;
    }

    if (in.hlkTimestampMs != 0 &&
        in.hlkTimestampMs != lastHlkTimestampMs_) {
      lastHlkTimestampMs_ = in.hlkTimestampMs;
      if (in.movingEnergy >= config::mlAlertTriggerEnergy) {
        if (movingFrames_ < 255) ++movingFrames_;
      } else {
        movingFrames_ = 0;
      }
    }

    if (mode_ == MlAlertMode::Idle) {
      const bool cooldownElapsed =
          lastVetoMs_ == 0 ||
          uint32_t(in.now - lastVetoMs_) >= config::mlAlertVetoCooldownMs;
      if (movingFrames_ >= config::mlAlertTriggerFrames && cooldownElapsed) {
        transition(MlAlertMode::Provisional, in.now, out);
        triggerStartMs_ = in.now;
        ++triggerCount_;
        beeped_ = false;
        releaseStartMs_ = 0;
      } else if (in.modelReady && in.windowReady && in.modelHuman &&
                 in.confidence >= config::mlAlertConfidence) {
        // The model can start the room-presence alert without the fast HLK
        // edge (for slow movement below the trigger energy).
        transition(MlAlertMode::Confirmed, in.now, out);
        ++confirmCount_;
        beeped_ = false;
        releaseStartMs_ = 0;
      } else {
        out.reason = "idle";
        return out;
      }
    }

    if (mode_ == MlAlertMode::Provisional) {
      const uint32_t elapsed = uint32_t(in.now - triggerStartMs_);
      if (in.modelReady && in.windowReady && in.modelHuman &&
          in.confidence >= config::mlAlertConfidence) {
        transition(MlAlertMode::Confirmed, in.now, out);
        ++confirmCount_;
        beeped_ = false;
      } else if (elapsed >= config::mlAlertVetoDelayMs &&
                 in.modelReady && in.windowReady &&
                 !in.modelHuman &&
                 in.confidence >= config::mlAlertVetoConfidence) {
        transition(MlAlertMode::Idle, in.now, out);
        ++vetoCount_;
        lastVetoMs_ = in.now;
        movingFrames_ = 0;
        out.reason = "model_veto";
        return out;
      } else if (elapsed >= config::mlAlertProvisionalMs) {
        transition(MlAlertMode::Idle, in.now, out);
        ++unconfirmedCount_;
        lastVetoMs_ = in.now;
        movingFrames_ = 0;
        out.reason = "unconfirmed";
        return out;
      }
    }

    if (mode_ == MlAlertMode::Confirmed) {
      if (!in.modelReady || !in.windowReady) {
        transition(MlAlertMode::Idle, in.now, out);
        out.reason = "model_not_ready";
        return out;
      }
      if (!in.modelHuman && in.confidence >= config::mlAlertVetoConfidence) {
        transition(MlAlertMode::Idle, in.now, out);
        ++vetoCount_;
        lastVetoMs_ = in.now;
        movingFrames_ = 0;
        out.reason = "model_veto";
        return out;
      }
    }

    // Fast hybrid release: because the demo target always moves, no HLK
    // movement for one second is enough to stop the room-presence beep.
    // Keep the normal beep rhythm during the hold so brief movement gaps do
    // not sound like a broken/stuttering buzzer.
    bool releaseHolding = false;
    if (in.movingEnergy < config::mlAlertReleaseEnergy) {
      if (releaseStartMs_ == 0) releaseStartMs_ = in.now;
      if (uint32_t(in.now - releaseStartMs_) >= config::mlAlertReleaseHoldMs) {
        transition(MlAlertMode::Idle, in.now, out);
        ++releaseCount_;
        out.reason = "hlk_no_motion";
        return out;
      }
      releaseHolding = true;
    } else {
      releaseStartMs_ = 0;
    }

    out.mode = mode_;
    out.active = mode_ != MlAlertMode::Idle;
    out.reason = releaseHolding ? "release_hold" :
        (mode_ == MlAlertMode::Provisional ? "provisional" : "confirmed");
    if (out.active && (!beeped_ ||
        uint32_t(in.now - lastBeepMs_) >= config::mlAlertIntervalMs)) {
      out.beep = true;
      lastBeepMs_ = in.now;
      beeped_ = true;
    }
    return out;
  }

  MlAlertMode mode() const { return mode_; }
  uint32_t lastTransitionMs() const { return lastTransitionMs_; }
  uint32_t triggerCount() const { return triggerCount_; }
  uint32_t confirmCount() const { return confirmCount_; }
  uint32_t vetoCount() const { return vetoCount_; }
  uint32_t releaseCount() const { return releaseCount_; }
  uint32_t unconfirmedCount() const { return unconfirmedCount_; }

 private:
  void transition(MlAlertMode mode, uint32_t now, MlAlertOutput& out) {
    if (mode_ != mode) {
      mode_ = mode;
      lastTransitionMs_ = now;
      out.transitioned = true;
    }
    out.mode = mode;
    out.active = mode != MlAlertMode::Idle;
  }

  MlAlertMode mode_ = MlAlertMode::Idle;
  uint32_t triggerStartMs_ = 0;
  uint32_t releaseStartMs_ = 0;
  uint32_t lastBeepMs_ = 0;
  uint32_t lastVetoMs_ = 0;
  uint32_t lastTransitionMs_ = 0;
  uint32_t triggerCount_ = 0;
  uint32_t confirmCount_ = 0;
  uint32_t vetoCount_ = 0;
  uint32_t releaseCount_ = 0;
  uint32_t unconfirmedCount_ = 0;
  uint8_t movingFrames_ = 0;
  bool beeped_ = false;
  uint32_t lastHlkTimestampMs_ = 0;
};
