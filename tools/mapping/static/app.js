'use strict';

const $ = (id) => document.getElementById(id);
function storedYawScale() {
  try {
    const value = Number(localStorage.getItem('mapping.yawScale'));
    return Number.isFinite(value) && value >= 0.5 && value <= 1.0 ? value : 0.76;
  } catch (error) {
    return 0.76;
  }
}

function storedMapRotation() {
  try {
    const raw = localStorage.getItem('mapping.mapRotation');
    if (raw === null) return 10.7;
    const value = Number(raw);
    return Number.isFinite(value) && value >= -45 && value <= 45 ? value : 10.7;
  } catch (error) {
    return 10.7;
  }
}

const state = {
  health: null,
  scans: [],
  calibration: null,
  points: [],
  scanJob: null,
  loadedScan: null,
  reconstruction: null,
  annotations: null,
  undoStack: [],
  undoLimit: 30,
  selectedBoxId: null,
  lastBoxPick: null,
  pointLabels: {},
  labelCatalog: {},
  manualBoxes: [],
  room: null,
  roomOutline: [],
  selectedPointIndices: [],
  selectionRect: null,
  selectDepthMin: -5,
  selectDepthMax: 5,
  selectThrough: true,
  priorVisible: true,
  priorEditMode: false,
  showAxis: true,
  datasetRuns: [],
  presence: null,
  presenceError: null,
  presenceBusy: false,
  mlMetrics: null,
  showDistances: true,
  yawScale: storedYawScale(),
  mapRotation: storedMapRotation(),
  topZoom: 1.0,
  topPanX: 0,
  topPanY: 0,
  viewMode: 'both',
  viewYaw: -0.65,
  viewPitch: 0.55,
  zoom: 1.4,
  viewPanX: 0,
  viewPanY: 0,
};

async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || data.message || `HTTP ${response.status}`);
  }
  return data;
}

function fmt(value, suffix = '') {
  return value === null || value === undefined || Number.isNaN(Number(value))
    ? '—' : `${Number(value).toFixed(1)}${suffix}`;
}

function badge(id, value) {
  const element = $(id);
  element.textContent = value || '—';
  element.className = `badge ${value || ''}`;
}

function setText(id, text) {
  $(id).textContent = text;
}

let toastTimer = null;
function showToast(message, type = 'info', ms = 2600) {
  const toast = $('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.className = 'toast';
  }, ms);
}

async function withBusy(button, action, busyText = 'Memproses...') {
  if (!button) return action();
  const original = button.textContent;
  button.disabled = true;
  button.classList.add('busy');
  button.textContent = busyText;
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.classList.remove('busy');
    button.textContent = original;
  }
}

function updateUndoButton() {
  const button = $('undo-annotations');
  if (!button) return;
  const count = state.undoStack.length;
  button.disabled = count === 0;
  button.title = count ? `${count} langkah bisa di-undo` : 'Belum ada perubahan untuk di-undo';
  button.textContent = count ? `Undo (${count})` : 'Undo (Ctrl+Z)';
}

async function undoLast() {
  if (!state.undoStack.length) {
    showToast('Belum ada perubahan yang bisa di-undo.', 'warn');
    return;
  }
  const snapshot = state.undoStack.pop();
  updateUndoButton();
  const next = JSON.parse(snapshot);
  try {
    await withBusy($('undo-annotations'),
      () => saveAnnotations(next, 'Undo berhasil. Prior, label, dan daftar hapus dipulihkan.',
        state.selectedBoxId, { skipUndo: true }), 'Undo...');
    updateUndoButton();
    showToast('Undo berhasil.', 'success');
  } catch (error) {
    state.undoStack.push(snapshot);
    updateUndoButton();
    showToast(`Undo gagal: ${error.message}`, 'error', 4500);
  }
}

function switchTab(name) {
  for (const button of document.querySelectorAll('[data-tab]')) {
    button.classList.toggle('active', button.dataset.tab === name);
  }
  for (const section of document.querySelectorAll('.tab')) {
    section.classList.toggle('active', section.id === `tab-${name}`);
  }
  if (name === 'cloud') { drawCloud(); drawTopDown(); }
  if (name === 'presence') { renderPresence(); drawPresenceTrend(); }
}

async function refreshScans() {
  try {
    const data = await api('/api/mapping/scans');
    state.scans = data.scans || [];
    renderScans();
  } catch (error) {
    setText('scan-list', `Daftar scan gagal: ${error.message}`);
  }
}

async function refreshHealth() {
  try {
    const response = await fetch('/api/mapping/health', { cache: 'no-store' });
    const data = await response.json();
    state.health = data;
    state.scans = data.scans || [];
    state.calibration = data.calibration || {};
    state.mlMetrics = data.ml_metrics || state.mlMetrics;
    if (data.presence) state.presence = data.presence;
    state.presenceError = data.ok === false ? (data.error || 'ESP offline') : null;
    renderHealth();
    renderPresence();
    renderScans();
    renderCalibration();
  } catch (error) {
    setText('summary', `ESP32 belum terhubung: ${error.message}`);
    state.presenceError = error.message;
    renderPresence();
    await refreshScans();
  }
}

function renderHealth() {
  const data = state.health;
  if (!data || !data.esp) {
    setText('summary', 'ESP32 belum terhubung. Pastikan device.local.json dan jaringan benar.');
    return;
  }
  const esp = data.esp;
  const sensors = esp.sensors || {};
  const hc = sensors.hc_sr04 || {};
  const tof = sensors.vl53l1x || {};
  const hlk = sensors.hlk || {};
  const health = sensors.health || {};
  const stats = sensors.stats || {};
  const actuators = esp.actuators || {};
  const scan = esp.scan || {};
  const alert = esp.hlk_alert || {};
  setText('summary', `${esp.version || '—'} · ${esp.mode || '—'} · ${esp.ip || '—'}`);
  setText('esp-summary', `${esp.mode || '—'} · ${esp.version || '—'}`);
  setText('esp-detail', `IP ${esp.ip || '—'} · scan mode ${scan.mode ? 'ON' : 'OFF'} · servo ${actuators.servo_target_us ?? '—'} µs · stepper ${actuators.relative_half_steps ?? '—'} hsteps`);
  $('manual-link').href = esp.ip ? `http://${esp.ip}/` : '#';
  const hcValue = hc.valid ? (hc.distance_cal_cm ?? hc.distance_cm) : null;
  const tofValue = tof.valid ? (tof.distance_cal_cm ?? tof.distance_cm) : null;
  setText('hc', hcValue != null ? `${fmt(hcValue)} cm` : '—');
  setText('tof', tofValue != null ? `${fmt(tofValue)} cm` : '—');
  setText('hlk', hlk.valid ? `${fmt(hlk.distance_cm)} cm` : '—');
  badge('hc-health', health.hc_sr04);
  badge('tof-health', health.vl53l1x);
  badge('hlk-health', health.hlk);
  setText('health', `Overall ${health.overall || '—'} · ToF errors ${stats.tof_i2c_errors ?? '—'} · ${stats.tof_error_rate_per_min ?? '—'}/min · responsive ${tof.responsive ? 'yes' : 'no'}${tof.near_reflector ? ' · NEAR REFLECTOR (~30 cm)' : ''}`);
  setText('pose', `${actuators.servo_attached ? 'servo attached' : 'servo detached'} · ${actuators.stepper_energized ? 'stepper energized' : 'stepper off'}`);
  setText('pose-detail', `servo ${actuators.servo_target_us ?? '—'} µs · stepper ${actuators.relative_half_steps ?? '—'} hsteps · yaw ${fmt(scan.yaw_deg_nominal, '°')}`);
  setText('alert', `HLK alert ${alert.enabled ? 'ON' : 'OFF'} · ${alert.min_cm ?? 30}–${alert.max_cm ?? 75} cm · ${alert.state || 'idle'} · ${alert.mute_reason || '—'} · count ${alert.count ?? 0}`);
  if (document.getElementById('tab-cloud').classList.contains('active')) { drawCloud(); drawTopDown(); }
  renderScans();
}

function renderScans() {
  const scans = state.scans || [];
  const list = $('scan-list');
  const select = $('scan-select');
  list.replaceChildren();
  select.replaceChildren();
  if (!scans.length) {
    list.textContent = 'Belum ada scan.';
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'Belum ada scan';
    select.append(option);
    setText('last-scan', 'Belum ada scan.');
    renderExportScans();
    return;
  }
  const table = document.createElement('table');
  const head = document.createElement('tr');
  for (const label of ['Scan', 'Points', 'Valid', 'ToF', 'HC', 'Bounds', 'Status']) {
    const th = document.createElement('th');
    th.textContent = label;
    head.append(th);
  }
  table.append(head);
  for (const scan of scans.slice(0, 20)) {
    const row = document.createElement('tr');
    const config = scan.config || {};
    const bounds = `${config.yaw_limit_deg ?? '—'}° / ${config.tilt_min_us ?? '—'}–${config.tilt_max_us ?? '—'} µs`;
    for (const value of [scan.scan_id, scan.points, scan.valid_points, scan.tof_points,
                         scan.hc_points, bounds, scan.error ? 'ERROR' : 'OK']) {
      const td = document.createElement('td');
      td.textContent = value ?? '—';
      row.append(td);
    }
    table.append(row);
    const option = document.createElement('option');
    option.value = scan.scan_id;
    option.textContent = `${scan.scan_id} · ${scan.points} pts`;
    select.append(option);
  }
  list.append(table);
  const latest = scans.find(scan => !scan.error && (scan.points || 0) > 0) || scans[0];
  const latestConfig = latest.config || {};
  setText('last-scan', `${latest.scan_id} · ${latest.points} points · ${latest.valid_points} valid · ${latest.tof_points} ToF · ${latest.hc_points} HC · yaw ±${latestConfig.yaw_limit_deg ?? '—'}° · tilt ${latestConfig.tilt_min_us ?? '—'}–${latestConfig.tilt_max_us ?? '—'} µs`);
  if (!state.loadedScan) {
    select.value = latest.scan_id;
  } else {
    select.value = state.loadedScan;
  }
  renderExportScans();
}

function renderCalibration() {
  const calibration = state.calibration || {};
  const latest = calibration.latest;
  setText('cal-latest', latest
    ? `actual ${latest.actual_cm} cm\nHC raw ${latest.hc_raw_mm} mm → offset ${latest.hc_offset_mm} mm\nToF raw ${latest.tof_raw_mm} mm → offset ${latest.tof_offset_mm} mm\nHLK ${latest.hlk_cm} cm · health ${latest.sensor_health?.overall || '—'}`
    : 'Belum ada record kalibrasi.');
  const table = $('cal-table');
  table.replaceChildren();
  const records = calibration.records || [];
  if (!records.length) {
    table.textContent = 'Belum ada record.';
    return;
  }
  const element = document.createElement('table');
  const head = document.createElement('tr');
  for (const label of ['UTC', 'Actual cm', 'HC mm', 'ToF mm', 'HLK cm', 'HC offset', 'ToF offset', 'ToF valid']) {
    const th = document.createElement('th');
    th.textContent = label;
    head.append(th);
  }
  element.append(head);
  for (const record of records.slice(-20).reverse()) {
    const row = document.createElement('tr');
    for (const value of [record.utc, record.actual_cm, record.hc_raw_mm, record.tof_raw_mm,
                         record.hlk_cm, record.hc_offset_mm, record.tof_offset_mm,
                         record.tof_valid_rate]) {
      const td = document.createElement('td');
      td.textContent = value ?? '—';
      row.append(td);
    }
    element.append(row);
  }
  table.append(element);
}

async function refreshCalibration() {
  try {
    const data = await api('/api/mapping/calibration');
    state.calibration = data.calibration || {};
    renderCalibration();
  } catch (error) {
    setText('cal-latest', `Kalibrasi belum tersedia: ${error.message}`);
  }
}

function renderPresence() {
  const presence = state.presence;
  const ml = state.mlMetrics || state.health?.ml_metrics || {};
  const alert = state.health?.esp?.hlk_alert || {};
  if (!presence) {
    setText('presence-summary', state.presenceError ? 'ESP offline' : 'Menunggu data HLK…');
    setText('presence-detail', state.presenceError || 'Belum ada data presence.');
    setText('presence-class', '—');
    setText('presence-confidence', '—');
    setText('presence-distance', '—');
    setText('presence-reason', '—');
    badge('presence-state', '—');
    badge('presence-energy', '—');
  } else {
    const offlineEmpty = Boolean(state.presenceError) && presence.state === 'empty';
    const confidence = Math.max(0, Math.min(1, Number(presence.confidence) || 0));
    setText('presence-summary', offlineEmpty
      ? 'OFFLINE · no live HLK'
      : `${String(presence.class || 'empty').toUpperCase()} · ${Math.round(confidence * 100)}%`);
    setText('presence-detail', offlineEmpty
      ? `Tidak ada data HLK live: ${state.presenceError}`
      : `state ${presence.state} · ${presence.reason} · gate ${presence.gate || '-'} · konfirmasi ${presence.confirm_frames}/${presence.confirm_required} frame · hold ${presence.hold_s}s · wall ${presence.max_range_cm ?? '-'} cm`);
    setText('presence-class', offlineEmpty ? '—' : String(presence.class || 'empty'));
    setText('presence-confidence', offlineEmpty ? '—' : `${Math.round(confidence * 100)}%`);
    setText('presence-distance', presence.distance_cm != null ? `${Number(presence.distance_cm).toFixed(1)} cm` : '—');
    badge('presence-state', presence.state);
    badge('presence-energy', presence.energy != null ? `energy ${presence.energy}` : 'energy —');
    setText('presence-reason', `Rule: ${presence.rule}. Model: ${presence.model}.`);
    if (state.presenceError && !offlineEmpty) setText('presence-detail', `${presence.state} · offline: ${state.presenceError}`);
  }
  if (alert.enabled != null) {
    setText('actuator-summary', `${alert.enabled ? 'ON' : 'OFF'} · ${alert.state || 'idle'}`);
    setText('actuator-detail', `mute ${alert.mute_reason || '—'} · count ${alert.count ?? 0} · last ${alert.last_distance_cm ?? '—'} cm / energy ${alert.last_energy ?? '—'} · range ${alert.min_cm ?? 30}–${alert.max_cm ?? 75} cm`);
  } else {
    setText('actuator-summary', 'ESP offline');
    setText('actuator-detail', state.presenceError || 'Status aktuator belum tersedia.');
  }
  const accuracy = ml.final_val_accuracy != null
    ? `${(Number(ml.final_val_accuracy) * 100).toFixed(1)}%` : '—';
  const classes = Array.isArray(ml.classes) && ml.classes.length
    ? ml.classes.join(' / ') : 'binary empty / human';
  setText('model-summary', `${classes} · val ${accuracy}`);
  setText('model-detail', `${ml.frames ?? '—'} frame · ${ml.windows ?? '—'} window · ${ml.tflite_bytes ?? '—'} byte TFLite · holdout ${ml.holdout_sessions?.length ?? 0} sesi`);
  renderModelComparison(ml);
  drawPresenceTrend();
}

function renderModelComparison(ml) {
  const container = $('model-comparison');
  if (!container) return;
  container.replaceChildren();
  const rule = ml.rule_baseline || {};
  const rows = [
    ['Rule max(moving_energy)>0',
      rule.val_accuracy != null ? `${(Number(rule.val_accuracy) * 100).toFixed(1)}%` : '100.0%',
      'Baseline pada split yang sama; bukan model DL.'],
    ['DL 1D CNN binary',
      ml.final_val_accuracy != null ? `${(Number(ml.final_val_accuracy) * 100).toFixed(1)}%` : '82.7%',
      'empty recall 91.0%, human recall 77.2%; belum deployed.'],
  ];
  const table = document.createElement('table');
  const head = document.createElement('tr');
  for (const label of ['Metode', 'Validasi', 'Catatan']) {
    const th = document.createElement('th');
    th.textContent = label;
    head.append(th);
  }
  table.append(head);
  for (const row of rows) {
    const tr = document.createElement('tr');
    for (const value of row) {
      const td = document.createElement('td');
      td.textContent = value;
      tr.append(td);
    }
    table.append(tr);
  }
  container.append(table);
  if (Array.isArray(ml.val_confusion_matrix)) {
    const note = document.createElement('p');
    note.className = 'note';
    note.textContent = `Confusion matrix DL [[${ml.val_confusion_matrix.map(row => row.join(', ')).join('], [')}]] — baris empty/human.`;
    container.append(note);
  }
  if (ml.conclusion) {
    const note = document.createElement('p');
    note.className = 'note';
    note.textContent = ml.conclusion;
    container.append(note);
  }
}

function drawPresenceTrend() {
  const canvas = $('presence-trend');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const width = canvas.width, height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  const history = state.presence?.history || [];
  if (history.length < 2) {
    ctx.fillStyle = '#9fb1c7';
    ctx.font = '14px system-ui';
    ctx.fillText('Belum ada riwayat HLK. Nyalakan board dan buka tab ini.', 20, 34);
    return;
  }
  const pad = { left: 46, right: 52, top: 18, bottom: 30 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const maxEnergy = 255;
  const maxDistance = Math.max(200, ...history.map(item => Number(item.distance_cm) || 0));
  ctx.strokeStyle = '#1a2a3d';
  ctx.lineWidth = 1;
  for (let index = 0; index <= 4; index++) {
    const y = pad.top + plotH * index / 4;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
  }
  const xAt = (index) => pad.left + plotW * index / Math.max(1, history.length - 1);
  const yEnergy = (value) => pad.top + plotH * (1 - Math.max(0, Math.min(maxEnergy, value)) / maxEnergy);
  const yDistance = (value) => pad.top + plotH * (1 - Math.max(0, Math.min(maxDistance, value)) / maxDistance);
  ctx.lineWidth = 2;
  ctx.strokeStyle = '#59e0ff';
  ctx.beginPath();
  history.forEach((item, index) => {
    const x = xAt(index), y = yEnergy(Number(item.energy) || 0);
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.stroke();
  ctx.strokeStyle = '#ffb45c';
  ctx.beginPath();
  history.forEach((item, index) => {
    const x = xAt(index), y = yDistance(Number(item.distance_cm) || 0);
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.stroke();
  const stateColor = (value) => value === 'present' ? '#6bff9c'
    : (value === 'holding' || value === 'confirming') ? '#ffe06b' : '#5a6b80';
  history.forEach((item, index) => {
    const x = xAt(index), y = height - pad.bottom + 8;
    ctx.fillStyle = stateColor(item.state);
    ctx.beginPath(); ctx.arc(x, y, 2.2, 0, Math.PI * 2); ctx.fill();
  });
  ctx.fillStyle = '#9fb1c7';
  ctx.font = '11px system-ui';
  ctx.fillText('energy', pad.left, 12);
  ctx.fillStyle = '#59e0ff';
  ctx.fillText('0–255', pad.left + 44, 12);
  ctx.fillStyle = '#ffb45c';
  ctx.fillText(`jarak 0–${Math.round(maxDistance)} cm`, width - pad.right - 120, 12);
  ctx.fillStyle = '#9fb1c7';
  ctx.fillText('frame terakhir →', width - pad.right - 90, height - 8);
}

async function refreshPresence() {
  if (state.presenceBusy) return;
  state.presenceBusy = true;
  try {
    const response = await fetch('/api/mapping/presence', { cache: 'no-store' });
    const data = await response.json();
    if (data.presence) state.presence = data.presence;
    state.presenceError = data.ok === false ? (data.error || 'ESP offline') : null;
    if (data.hlk_alert) {
      if (!state.health) state.health = {};
      if (!state.health.esp) state.health.esp = {};
      state.health.esp.hlk_alert = data.hlk_alert;
    }
    renderPresence();
    if (document.getElementById('tab-cloud')?.classList.contains('active')) {
      drawCloud();
      drawTopDown();
    }
  } catch (error) {
    state.presenceError = error.message;
    renderPresence();
  } finally {
    state.presenceBusy = false;
  }
}

async function refreshScanStatus() {
  try {
    const data = await api('/api/mapping/scan/status');
    const job = data.job;
    state.scanJob = job;
    const total = Math.max(1, Number(job.total) || 1);
    const points = Number(job.points) || 0;
    $('scan-progress').value = Math.min(100, Math.round(100 * points / total));
    setText('scan-status', JSON.stringify(job, null, 2));
    $('start-scan').disabled = job.state === 'running';
    $('stop-scan').disabled = job.state !== 'running';
    if (job.state === 'done' && job.scan_id && job.scan_id !== state.loadedScan) {
      await refreshHealth();
      $('scan-select').value = job.scan_id;
      await loadPoints(job.scan_id);
    }
  } catch (error) {
    setText('scan-status', `Status scan gagal: ${error.message}`);
  }
}

async function startScan() {
  try {
    if (!$('power-confirm').checked) {
      alert('Konfirmasi dulu bahwa suplai servo/5V sudah diperbaiki dan diukur. Brownout servo attach belum terselesaikan.');
      return;
    }
    const body = {
      yaw_step_deg: Number($('yaw-step').value),
      yaw_limit_deg: Number($('yaw-limit').value),
      tilt_step_us: Number($('tilt-step').value),
      tilt_min_us: Number($('tilt-min').value),
      tilt_max_us: Number($('tilt-max').value),
      stepper_step_deg: Number($('yaw-step').value),
      servo_step_delay_s: Number($('servo-delay').value),
      column_cooldown_s: Number($('cooldown').value),
      release_stepper_during_sweep: $('release-stepper').checked,
      sample_interval_ms: Number($('sample-interval').value),
      dwell_ms: Number($('dwell').value),
      samples: Number($('samples').value),
      confirm_power: true,
    };
    $('start-scan').disabled = true;
    setText('scan-status', 'Memulai scan…');
    await api('/api/mapping/scan/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    await refreshScanStatus();
  } catch (error) {
    setText('scan-status', `Scan gagal dimulai: ${error.message}`);
    $('start-scan').disabled = false;
  }
}

async function stopScan() {
  try {
    await api('/api/mapping/scan/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    setText('scan-status', 'Stop diminta; scan menyelesaikan titik saat ini lalu kembali ke tengah.');
  } catch (error) {
    setText('scan-status', `Stop gagal: ${error.message}`);
  }
}

async function refreshMlStatus() {
  try {
    const data = await api('/api/mapping/ml/status');
    const job = data.job || {};
    setText('ml-status', JSON.stringify(job, null, 2));
    $('ml-start').disabled = job.state === 'running';
    $('ml-stop').disabled = job.state !== 'running';
  } catch (error) {
    setText('ml-status', `Status dataset gagal: ${error.message}`);
  }
}

async function startMl() {
  try {
    const label = $('ml-label').value;
    $('ml-start').disabled = true;
    setText('ml-status', 'Memulai rekaman…');
    await api('/api/mapping/ml/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label }),
    });
    await refreshMlStatus();
  } catch (error) {
    setText('ml-status', `Gagal mulai rekam: ${error.message}`);
    $('ml-start').disabled = false;
  }
}

async function stopMl() {
  try {
    await api('/api/mapping/ml/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    setText('ml-status', 'Stop diminta; menunggu frame terakhir…');
  } catch (error) {
    setText('ml-status', `Gagal stop rekam: ${error.message}`);
  }
}

async function captureCalibration() {
  try {
    const body = {
      actual_cm: Number($('actual-cm').value),
      samples: Number($('cal-samples').value),
      label: $('cal-label').value,
    };
    $('capture-cal').disabled = true;
    setText('cal-latest', 'Mengambil sampel…');
    await api('/api/mapping/calibration/capture', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    await refreshHealth();
  } catch (error) {
    setText('cal-latest', `Kalibrasi gagal: ${error.message}`);
  } finally {
    $('capture-cal').disabled = false;
  }
}

async function loadPoints(scanId, preserveCalibration = false) {
  if (!scanId) return;
  try {
    let preAnnotations = null;
    try {
      const ann = await api(`/api/mapping/scans/${encodeURIComponent(scanId)}/annotations`);
      preAnnotations = ann.annotations || null;
    } catch (error) {
      preAnnotations = null;
    }
    if (!preserveCalibration && preAnnotations?.room) {
      const yaw = Number(preAnnotations.room.yaw_scale);
      const rotation = Number(preAnnotations.room.map_rotation_deg);
      if (Number.isFinite(yaw)) state.yawScale = Math.max(0.50, Math.min(1.00, yaw));
      if (Number.isFinite(rotation)) state.mapRotation = Math.max(-45, Math.min(45, rotation));
    }
    const data = await api(`/api/mapping/scans/${encodeURIComponent(scanId)}/points`);
    state.points = data.points || [];
    state.loadedScan = scanId;
    $('scan-select').value = scanId;
    $('yaw-scale').value = Number(state.yawScale).toFixed(2);
    $('map-rotation').value = Number(state.mapRotation).toFixed(1);
    setText('yaw-scale-note', `yaw ${Number(state.yawScale).toFixed(2)} · rotasi ${Number(state.mapRotation).toFixed(1)}° — sesuaikan sampai dinding lurus.`);
    let reconstruction = null;
    let annotations = preAnnotations || { labels: {}, hidden: [], merges: [] };
    try {
      const rec = await api(`/api/mapping/scans/${encodeURIComponent(scanId)}/reconstruct?yaw_scale=${state.yawScale}&map_rotation=${state.mapRotation}`);
      reconstruction = rec.reconstruction;
      annotations = rec.annotations || annotations;
    } catch (error) {
      reconstruction = null;
    }
    state.reconstruction = reconstruction;
    applyAnnotationState(annotations);
    state.undoStack = [];
    updateUndoButton();
    state.selectedBoxId = null;
    state.selectedPointIndices = [];
    state.selectionRect = null;
    const blocks = reconstruction?.boxes?.length ?? 0;
    const mountBoxes = reconstruction?.mount_boxes ?? 0;
    setText('cloud-stats', `${scanId} · ${state.points.length} points · ${state.points.filter(p => p.range_mm != null).length} with range · yaw ${Number(reconstruction?.yaw_scale ?? state.yawScale).toFixed(2)} · rotasi ${Number(reconstruction?.map_rotation_deg ?? state.mapRotation).toFixed(1)}° · ${blocks} estimated blocks · mount ${reconstruction?.mount_points ?? '—'} pts / ${mountBoxes} box hidden`);
    renderBoxControls();
    drawCloud();
    drawTopDown();
  } catch (error) {
    setText('cloud-stats', `Gagal memuat point cloud: ${error.message}`);
  }
}

function rgbToHex(rgb) {
  return '#' + rgb.map(value => Math.max(0, Math.min(255, Math.round(value)))
    .toString(16).padStart(2, '0')).join('');
}

function ensureLabelCatalog(annotations, label) {
  if (!annotations.label_catalog) annotations.label_catalog = {};
  if (!annotations.label_catalog[label]) {
    annotations.label_catalog[label] = { color: rgbToHex(labelColor(label)) };
  }
}

function hexToRgb(value) {
  const match = /^#?([0-9a-f]{6})$/i.exec(String(value || ''));
  if (!match) return null;
  const number = parseInt(match[1], 16);
  return [(number >> 16) & 255, (number >> 8) & 255, number & 255];
}

function labelColor(label) {
  const catalog = state.labelCatalog || {};
  const entry = catalog[label];
  if (entry && entry.color) {
    const rgb = hexToRgb(entry.color);
    if (rgb) return rgb;
  }
  const palette = {
    wall: [80, 150, 230],
    wall_edge: [130, 200, 255],
    fan: [255, 190, 80],
    bed: [170, 140, 255],
    wardrobe: [205, 130, 255],
    chair: [255, 150, 120],
    table: [255, 170, 90],
    desk: [255, 150, 90],
    door: [150, 220, 180],
    mount: [150, 150, 150],
    object: [70, 210, 150],
  };
  if (palette[label]) return palette[label];
  let hash = 0;
  for (const character of String(label || 'object')) {
    hash = (hash * 31 + character.charCodeAt(0)) & 0xffffffff;
  }
  const hue = Math.abs(hash) % 360;
  const channel = (offset) => Math.round(128 + 100 * Math.cos((hue + offset) * Math.PI / 180));
  return [channel(0), channel(120), channel(240)];
}

function boxColor(box) {
  return labelColor(box.label);
}

function boxName(box) {
  if (box.source === 'prior') return `${box.label} (prior)`;
  return `${box.label}${box.label_source === 'manual' ? '*' : ''}`;
}

function visibleBoxes() {
  return currentBoxes().filter(box => state.priorVisible || box.source !== 'prior');
}

function applyAnnotationState(annotations) {
  const source = annotations || {};
  state.annotations = {
    labels: source.labels || {},
    hidden: source.hidden || [],
    removed: source.removed || [],
    merges: source.merges || [],
    point_labels: source.point_labels || {},
    label_catalog: source.label_catalog || {},
    manual_boxes: source.manual_boxes || [],
    room_outline: source.room_outline || [],
    room: source.room || {},
  };
  state.pointLabels = state.annotations.point_labels;
  state.labelCatalog = state.annotations.label_catalog;
  state.manualBoxes = state.annotations.manual_boxes;
  state.room = state.annotations.room;
  state.roomOutline = state.annotations.room_outline;
  renderLabelSuggestions();
  renderRoomInfo();
}

function renderLabelSuggestions() {
  const datalist = $('label-suggestions');
  if (!datalist) return;
  datalist.replaceChildren();
  const labels = new Set([
    'wall', 'wall_edge', 'fan', 'bed', 'wardrobe', 'chair', 'table',
    'desk', 'door', 'object', 'mount',
    ...Object.keys(state.labelCatalog || {}),
  ]);
  for (const label of labels) {
    const option = document.createElement('option');
    option.value = label;
    datalist.append(option);
  }
}

function renderRoomInfo() {
  const room = state.room || {};
  if (room.width_m && room.depth_m) {
    const bedroom = room.bedroom_m2 ?? (room.width_m * room.depth_m);
    const total = room.total_m2 ?? (bedroom + (room.bathroom_m2 || 0) + (room.desk_niche_m2 || 0));
    setText('room-info', `Prior: ${Number(room.width_m).toFixed(2)}×${Number(room.depth_m).toFixed(2)} m = `
      + `${Number(bedroom).toFixed(2)} m² · kamar mandi ${Number(room.bathroom_m2 || 0).toFixed(2)} m²`
      + ` · niche ${Number(room.desk_niche_m2 || 0).toFixed(2)} m² · total ${Number(total).toFixed(2)} m²`);
  } else {
    setText('room-info', 'Prior ruangan belum diisi.');
  }
}

function boxDistance(box) {
  const value = (box.label === 'wall' || box.label === 'wall_edge'
    || box.source === 'prior') ? box.nearest_m : box.distance_m;
  return Number(value);
}

function formatMeters(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)} m` : '—';
}

function currentBoxes() {
  return state.reconstruction?.boxes || [];
}

function annotationsClone() {
  const source = state.annotations || {};
  return JSON.parse(JSON.stringify({
    labels: source.labels || {},
    hidden: source.hidden || [],
    removed: source.removed || [],
    merges: source.merges || [],
    point_labels: source.point_labels || {},
    label_catalog: source.label_catalog || {},
    manual_boxes: source.manual_boxes || [],
    room_outline: source.room_outline || [],
    room: source.room || {},
  }));
}

function renderBoxControls() {
  const select = $('box-select');
  const merge = $('box-merge');
  if (!select || !merge) return;
  const boxes = currentBoxes();
  const previous = state.selectedBoxId || select.value;
  select.replaceChildren();
  merge.replaceChildren();
  if (!boxes.length) {
    for (const element of [select, merge]) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'Tidak ada blok';
      element.append(option);
    }
    setText('annotation-status', 'Tidak ada blok untuk dianotasi.');
    renderBlockList();
    return;
  }
  boxes.forEach((box, index) => {
    const text = `${index + 1}. ${boxName(box)} · ${formatMeters(boxDistance(box))} · `
      + `${Number(box.length_m).toFixed(1)}×${Number(box.width_m).toFixed(1)} m`;
    const option = document.createElement('option');
    option.value = box.id;
    option.textContent = text;
    select.append(option);
    const mergeOption = document.createElement('option');
    mergeOption.value = box.id;
    mergeOption.textContent = text;
    merge.append(mergeOption);
  });
  if (previous && boxes.some(box => box.id === previous)) select.value = previous;
  state.selectedBoxId = select.value;
  const mergeCandidate = boxes.find(box => box.id !== select.value);
  merge.value = mergeCandidate ? mergeCandidate.id : '';
  syncBoxLabel();
  syncPriorFields();
  const annotations = state.annotations || {};
  const count = Object.keys(annotations.labels || {}).length
    + (annotations.hidden || []).length + (annotations.merges || []).length;
  setText('annotation-status', count ? `${count} anotasi manual aktif.` : 'Belum ada anotasi manual.');
  renderBlockList();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

function boxSelectionRank(box) {
  // Non-wall boxes (doors, furniture) win over wall surfaces; within the same
  // rank the smallest footprint wins in selectBoxAt.
  return (box.label === 'wall' || box.label === 'wall_edge') ? 1 : 0;
}

function boxFootprintArea(box) {
  return Math.max(0.01, Number(box.length_m || 0) * Number(box.width_m || 0));
}

function renderSelectedSummary() {
  const element = $('selected-summary');
  if (!element) return;
  const boxes = currentBoxes();
  const box = boxes.find(item => item.id === state.selectedBoxId) || null;
  if (!box) {
    element.textContent = 'Belum ada blok dipilih. Klik baris di stack atau box di peta.';
    element.style.borderLeftColor = '#5096e6';
    return;
  }
  const index = boxes.findIndex(item => item.id === box.id) + 1;
  const color = boxColor(box);
  element.style.borderLeftColor = `rgb(${color[0]},${color[1]},${color[2]})`;
  element.innerHTML = `<b>#${index} ${escapeHtml(boxName(box))}</b> · `
    + `${box.source === 'prior' ? 'prior' : (box.label_source === 'manual' ? 'manual' : 'auto')}<br>`
    + `${formatMeters(boxDistance(box))} · `
    + `${Number(box.length_m).toFixed(2)}×${Number(box.width_m).toFixed(2)}×${Number(box.z_top_m).toFixed(2)} m`
    + ` · ${box.points} pts`;
}

function selectBoxById(id, switchTab = true) {
  const box = currentBoxes().find(item => String(item.id) === String(id));
  if (!box) return;
  state.selectedBoxId = box.id;
  $('box-select').value = box.id;
  syncBoxLabel();
  syncPriorFields();
  renderBlockList();
  if (switchTab) {
    setSidebarTab('edit');
    setSidebarOpen(true);
  }
  drawCloud();
  drawTopDown();
}

function setSidebarTab(name) {
  document.querySelectorAll('[data-sidebar-tab]').forEach(button => {
    button.classList.toggle('active', button.dataset.sidebarTab === name);
  });
  document.querySelectorAll('[data-sidebar-pane]').forEach(pane => {
    pane.hidden = pane.dataset.sidebarPane !== name;
  });
}

function setSidebarOpen(open) {
  const sidebar = $('block-sidebar');
  const toggle = $('block-sidebar-toggle');
  if (!sidebar || !toggle) return;
  sidebar.hidden = !open;
  toggle.hidden = open;
  toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  try {
    localStorage.setItem('mapping.sidebarOpen', open ? '1' : '0');
  } catch (error) {
    // localStorage can be blocked; the in-memory state still works.
  }
}

function renderBlockList() {
  const container = $('block-stack');
  if (!container) return;
  container.replaceChildren();
  const boxes = currentBoxes();
  const count = $('block-count');
  if (count) count.textContent = String(boxes.length);
  const toggle = $('block-sidebar-toggle');
  if (toggle) toggle.textContent = `Blok / Prior (${boxes.length})`;
  renderSelectedSummary();
  if (!boxes.length) {
    container.textContent = 'Tidak ada blok untuk ditampilkan.';
    return;
  }
  const filter = String($('block-filter')?.value || '').trim().toLowerCase();
  const groups = new Map();
  boxes.forEach((box, index) => {
    const label = boxName(box);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push({ box, index });
  });
  for (const [label, items] of groups) {
    const visible = items.filter(({ box }) => {
      if (!filter) return true;
      return `${boxName(box)} ${box.label} ${box.source || ''} ${box.label_source || ''}`
        .toLowerCase().includes(filter);
    });
    if (!visible.length) continue;
    const header = document.createElement('div');
    header.className = 'group-label';
    header.textContent = `${label} (${visible.length})`;
    container.append(header);
    for (const { box, index } of visible) {
      const row = document.createElement('div');
      row.className = `block-row${box.id === state.selectedBoxId ? ' selected' : ''}`;
      row.dataset.boxId = box.id;
      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      const color = boxColor(box);
      swatch.style.background = `rgb(${color[0]},${color[1]},${color[2]})`;
      const number = document.createElement('span');
      number.className = 'num';
      number.textContent = String(index + 1);
      const name = document.createElement('span');
      name.className = 'name';
      name.textContent = boxName(box);
      const meta = document.createElement('span');
      meta.className = 'meta';
      const source = box.source === 'prior' ? 'P'
        : (box.label_source === 'manual' ? 'M' : 'A');
      meta.textContent = `${formatMeters(boxDistance(box))} · `
        + `${Number(box.length_m).toFixed(1)}×${Number(box.width_m).toFixed(1)} · ${source}`;
      row.append(swatch, number, name, meta);
      row.addEventListener('click', () => selectBoxById(box.id));
      container.append(row);
    }
  }
}

function syncBoxLabel() {
  const box = currentBoxes().find(item => item.id === $('box-select').value);
  if (box) $('box-label').value = box.label;
}

function selectedBox() {
  return currentBoxes().find(item => item.id === $('box-select').value) || null;
}

function isEditableBox(box) {
  if (!box) return false;
  return box.source === 'prior' || box.source === 'manual'
    || box.label_source === 'manual' || box.label_source === 'prior';
}

function updatePriorFieldValues(box) {
  const values = {
    'prior-x': box.cx_m,
    'prior-y': box.cy_m,
    'prior-z0': box.z_bottom_m,
    'prior-z1': box.z_top_m,
    'prior-length': box.length_m,
    'prior-width': box.width_m,
    'prior-angle': box.angle_deg,
  };
  for (const [id, value] of Object.entries(values)) {
    if ($(id)) $(id).value = Number(value ?? 0).toFixed(2);
  }
}

function syncPriorFields() {
  const box = selectedBox();
  const ids = ['prior-x', 'prior-y', 'prior-z0', 'prior-z1',
               'prior-length', 'prior-width', 'prior-angle'];
  if (!box) {
    ids.forEach(id => { if ($(id)) $(id).value = ''; });
    setText('prior-status', 'Pilih blok prior untuk diedit.');
    return;
  }
  const editable = isEditableBox(box);
  updatePriorFieldValues(box);
  ids.forEach(id => { if ($(id)) $(id).disabled = !editable; });
  setText('prior-status', editable
    ? `Edit ${box.label} (${box.source || 'manual'}). Pivot putih = pusat objek; drag handle = ubah satu sisi.`
    : `Auto box ${box.label}: klik "Jadikan prior" untuk mengedit posisi/ukuran.`);
}

async function addPrior() {
  const next = annotationsClone();
  next.manual_boxes = next.manual_boxes || [];
  const id = `prior:${Date.now().toString(36)}`;
  next.manual_boxes.push({
    id,
    label: 'prior',
    cx_m: 0.8,
    cy_m: 0.0,
    angle_deg: 0,
    length_m: 0.6,
    width_m: 0.6,
    z_bottom_m: 0,
    z_top_m: 1.0,
    source: 'prior',
  });
  ensureLabelCatalog(next, 'prior');
  try {
    await withBusy($('add-prior'), () => saveAnnotations(next, 'Prior baru ditambahkan. Geser dengan drag/arrow.', id), 'Menambah...');
  } catch (error) {
    setText('prior-status', `Gagal menambah prior: ${error.message}`);
  }
}

async function deletePrior() {
  const box = selectedBox();
  if (!box) {
    showToast('Pilih blok dulu.', 'warn');
    return;
  }
  const next = annotationsClone();
  try {
    if (isEditableBox(box)) {
      if (!window.confirm(`Hapus prior "${box.label}"?`)) return;
      next.manual_boxes = (next.manual_boxes || [])
        .filter(item => String(item.id) !== String(box.id));
      delete next.labels[box.id];
      next.hidden = (next.hidden || []).filter(id => String(id) !== String(box.id));
      await withBusy($('delete-prior'),
        () => saveAnnotations(next, `Prior ${box.label} dihapus.`), 'Menghapus...');
    } else {
      next.removed = Array.from(new Set([...(next.removed || []), box.id]));
      next.hidden = (next.hidden || []).filter(id => String(id) !== String(box.id));
      delete next.labels[box.id];
      await withBusy($('delete-prior'),
        () => saveAnnotations(next, `Blok ${box.label} dihapus permanen.`), 'Menghapus...');
    }
  } catch (error) {
    setText('prior-status', `Gagal menghapus: ${error.message}`);
    showToast(`Gagal menghapus: ${error.message}`, 'error', 4500);
  }
}

async function convertToPrior() {
  const box = selectedBox();
  if (!box) return;
  if (isEditableBox(box)) {
    setText('prior-status', 'Blok ini sudah prior/manual.');
    return;
  }
  const next = annotationsClone();
  next.manual_boxes = next.manual_boxes || [];
  const id = `prior:${Date.now().toString(36)}`;
  next.manual_boxes.push({
    id,
    label: box.label || 'object',
    cx_m: Number(box.cx_m) || 0,
    cy_m: Number(box.cy_m) || 0,
    angle_deg: Number(box.angle_deg) || 0,
    length_m: Number(box.length_m) || 0.6,
    width_m: Number(box.width_m) || 0.6,
    z_bottom_m: Number(box.z_bottom_m) || 0,
    z_top_m: Number(box.z_top_m) || 1.0,
    source: 'prior',
  });
  next.hidden = Array.from(new Set([...(next.hidden || []), box.id]));
  ensureLabelCatalog(next, box.label || 'object');
  try {
    await withBusy($('convert-prior'), () => saveAnnotations(next,
      `Blok ${box.label} dijadikan prior editable; auto box disembunyikan.`, id), 'Mengubah...');
  } catch (error) {
    setText('prior-status', `Gagal menjadikan prior: ${error.message}`);
  }
}

async function promoteBoxToPrior(box) {
  const next = annotationsClone();
  next.manual_boxes = next.manual_boxes || [];
  const id = `prior:${Date.now().toString(36)}`;
  next.manual_boxes.push({
    id,
    label: box.label || 'object',
    cx_m: Number(box.cx_m) || 0,
    cy_m: Number(box.cy_m) || 0,
    angle_deg: Number(box.angle_deg) || 0,
    length_m: Number(box.length_m) || 0.6,
    width_m: Number(box.width_m) || 0.6,
    z_bottom_m: Number(box.z_bottom_m) || 0,
    z_top_m: Number(box.z_top_m) || 1.0,
    source: 'prior',
  });
  next.hidden = Array.from(new Set([...(next.hidden || []), box.id]));
  next.removed = (next.removed || []).filter(item => String(item) !== String(box.id));
  ensureLabelCatalog(next, box.label || 'object');
  await saveAnnotations(next, `Blok ${box.label} dijadikan prior; lanjut resize.`, id);
  return currentBoxes().find(item => String(item.id) === String(id)) || null;
}

async function applyPriorFields() {
  const box = selectedBox();
  if (!box || !isEditableBox(box)) {
    setText('prior-status', 'Pilih prior/manual box dulu.');
    return;
  }
  const next = annotationsClone();
  const manual = (next.manual_boxes || [])
    .find(item => String(item.id) === String(box.id));
  if (!manual) return;
  const z0 = Math.max(0, Number($('prior-z0').value) || 0);
  const z1 = Math.max(z0 + 0.05, Number($('prior-z1').value) || 0.05);
  Object.assign(manual, {
    cx_m: Number($('prior-x').value) || 0,
    cy_m: Number($('prior-y').value) || 0,
    z_bottom_m: z0,
    z_top_m: z1,
    length_m: Math.max(0.05, Number($('prior-length').value) || 0.05),
    width_m: Math.max(0.05, Number($('prior-width').value) || 0.05),
    angle_deg: Number($('prior-angle').value) || 0,
  });
  try {
    await withBusy($('apply-prior'), () => saveAnnotations(next, 'Prior disimpan.', box.id), 'Menyimpan...');
  } catch (error) {
    setText('prior-status', `Gagal menyimpan prior: ${error.message}`);
  }
}

async function nudgePrior(direction, button = null) {
  const box = selectedBox();
  if (!box || !isEditableBox(box)) {
    showToast('Pilih prior/manual box dulu.', 'warn');
    setText('prior-status', 'Pilih prior/manual box dulu.');
    return;
  }
  const next = annotationsClone();
  const manual = (next.manual_boxes || [])
    .find(item => String(item.id) === String(box.id));
  if (!manual) return;
  const step = Number($('prior-step').value) || 0.1;
  const dx = direction === 'x-' ? -step : direction === 'x+' ? step : 0;
  const dy = direction === 'y-' ? -step : direction === 'y+' ? step : 0;
  const dz = direction === 'z-' ? -step : direction === 'z+' ? step : 0;
  manual.cx_m = Number(manual.cx_m || 0) + dx;
  manual.cy_m = Number(manual.cy_m || 0) + dy;
  if (dz) {
    const z0 = Math.max(0, Number(manual.z_bottom_m || 0) + dz);
    const z1 = Math.max(z0 + 0.05, Number(manual.z_top_m || 0.05) + dz);
    manual.z_bottom_m = z0;
    manual.z_top_m = z1;
  }
  if (direction === 'rot-') manual.angle_deg = Number(manual.angle_deg || 0) - 5;
  if (direction === 'rot+') manual.angle_deg = Number(manual.angle_deg || 0) + 5;
  try {
    await withBusy(button,
      () => saveAnnotations(next, 'Prior digeser.', box.id),
      'Menggeser...');
  } catch (error) {
    setText('prior-status', `Gagal menggeser prior: ${error.message}`);
    showToast(`Gagal menggeser: ${error.message}`, 'error', 4500);
  }
}

async function saveAnnotations(annotations, message, keepSelection = null, options = {}) {
  if (!state.loadedScan) return;
  const snapshot = JSON.stringify(annotationsClone());
  annotations.room = annotations.room || {};
  annotations.room.yaw_scale = state.yawScale;
  annotations.room.map_rotation_deg = state.mapRotation;
  setText('annotation-status', 'Menyimpan...');
  showToast('Menyimpan anotasi...', 'info', 8000);
  let data;
  try {
    data = await api(`/api/mapping/scans/${encodeURIComponent(state.loadedScan)}/annotations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ annotations, yaw_scale: state.yawScale, map_rotation: state.mapRotation }),
    });
  } catch (error) {
    setText('annotation-status', `Gagal menyimpan: ${error.message}`);
    showToast(`Gagal menyimpan: ${error.message}`, 'error', 4500);
    throw error;
  }
  if (!options.skipUndo) {
    state.undoStack.push(snapshot);
    if (state.undoStack.length > state.undoLimit) state.undoStack.shift();
  }
  updateUndoButton();
  state.reconstruction = data.reconstruction;
  applyAnnotationState(data.annotations || annotations);
  state.selectedBoxId = keepSelection;
  renderBoxControls();
  drawCloud();
  drawTopDown();
  const blocks = data.reconstruction?.boxes?.length ?? 0;
  const removed = (data.annotations?.removed || []).length;
  setText('cloud-stats', `${state.loadedScan} · ${state.points.length} points · ${blocks} blocks · ${removed} dihapus permanen · mount ${data.reconstruction?.mount_points ?? '-'} hidden`);
  setText('annotation-status', message || 'Anotasi disimpan.');
  showToast(message || 'Anotasi disimpan.', 'success');
}

async function applyBoxLabel() {
  const box = currentBoxes().find(item => item.id === $('box-select').value);
  if (!box) return;
  const label = String($('box-label').value || '').trim();
  if (!label) {
    setText('annotation-status', 'Label tidak boleh kosong.');
    return;
  }
  const next = annotationsClone();
  next.labels[box.id] = label;
  ensureLabelCatalog(next, label);
  try {
    await withBusy($('apply-label'), () => saveAnnotations(next, `Label ${box.label} -> ${label}.`), 'Menyimpan...');
  } catch (error) {
    setText('annotation-status', `Gagal menyimpan label: ${error.message}`);
  }
}

async function hideSelectedBox() {
  const box = currentBoxes().find(item => item.id === $('box-select').value);
  if (!box) return;
  const next = annotationsClone();
  next.hidden = Array.from(new Set([...(next.hidden || []), box.id]));
  delete next.labels[box.id];
  try {
    await withBusy($('hide-box'), () => saveAnnotations(next, `Blok ${box.label} disembunyikan.`), 'Menyembunyikan...');
  } catch (error) {
    setText('annotation-status', `Gagal menyembunyikan blok: ${error.message}`);
  }
}

async function mergeSelectedBoxes() {
  const first = $('box-select').value;
  const second = $('box-merge').value;
  if (!first || !second || first === second) {
    setText('annotation-status', 'Pilih dua blok berbeda untuk digabung.');
    return;
  }
  const next = annotationsClone();
  next.merges = [...(next.merges || []), [first, second]];
  next.hidden = (next.hidden || []).filter(id => id !== first && id !== second);
  try {
    await withBusy($('merge-boxes'), () => saveAnnotations(next, 'Dua blok digabung menjadi satu bounding box.'), 'Menggabung...');
  } catch (error) {
    setText('annotation-status', `Gagal menggabung blok: ${error.message}`);
  }
}

async function resetAnnotations() {
  if (!window.confirm('Reset label, sembunyi sementara, merge, dan label titik? Prior dan blok yang sudah dihapus permanen tetap dipertahankan.')) {
    return;
  }
  const next = annotationsClone();
  next.labels = {};
  next.hidden = [];
  next.merges = [];
  next.point_labels = {};
  next.removed = state.annotations?.removed || [];
  try {
    await withBusy($('reset-annotations'), () => saveAnnotations(next, 'Label, sembunyi, merge, dan point label direset; prior + hapus permanen tetap.'), 'Reset...');
  } catch (error) {
    setText('annotation-status', `Gagal reset anotasi: ${error.message}`);
  }
}

function renderExportScans() {
  const select = $('export-scan');
  if (!select) return;
  const previous = select.value || state.loadedScan;
  select.replaceChildren();
  const scans = state.scans || [];
  if (!scans.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'Belum ada scan';
    select.append(option);
    return;
  }
  for (const scan of scans) {
    const option = document.createElement('option');
    option.value = scan.scan_id;
    option.textContent = `${scan.scan_id} · ${scan.points} pts · ${scan.valid_points} valid`;
    select.append(option);
  }
  const preferred = previous || (scans[0] && scans[0].scan_id);
  if (preferred && scans.some(scan => scan.scan_id === preferred)) {
    select.value = preferred;
  }
}

function renderDatasetIndex() {
  const container = $('dataset-index');
  if (!container) return;
  container.replaceChildren();
  const runs = state.datasetRuns || [];
  if (!runs.length) {
    container.textContent = 'Belum ada run dataset. Klik Export CSV.';
    return;
  }
  const table = document.createElement('table');
  const head = document.createElement('tr');
  for (const label of ['Run UTC', 'Scan', 'Label', 'Bersih', 'Points', 'Boxes', 'Folder']) {
    const th = document.createElement('th');
    th.textContent = label;
    head.append(th);
  }
  table.append(head);
  for (const run of runs.slice(-20).reverse()) {
    const row = document.createElement('tr');
    for (const value of [
      run.run_utc, run.scan_id, run.run_label || '-',
      String(run.clean).toLowerCase() === 'true' ? 'ya' : 'tidak',
      `${run.points_total || '-'} / ${run.points_valid || '-'}`,
      `${run.boxes_total || '-'} (${run.measured_boxes || 0}M/${run.prior_boxes || 0}P)`,
      run.folder || '-',
    ]) {
      const cell = document.createElement('td');
      cell.textContent = value ?? '-';
      row.append(cell);
    }
    table.append(row);
  }
  container.append(table);
}

async function refreshDatasetIndex() {
  try {
    const data = await api('/api/mapping/dataset');
    state.datasetRuns = data.runs || [];
    renderDatasetIndex();
  } catch (error) {
    setText('dataset-index', `Gagal memuat index dataset: ${error.message}`);
  }
}

async function exportDataset() {
  const scanId = $('export-scan').value || state.loadedScan;
  if (!scanId) {
    setText('export-status', 'Pilih scan dulu.');
    return;
  }
  const clean = $('export-clean').checked;
  const body = {
    clean,
    run_label: String($('export-label').value || '').trim(),
    notes: String($('export-notes').value || '').trim(),
  };
  try {
    setText('export-status', 'Mengekspor CSV...');
    const data = await withBusy($('export-run'), () => api(`/api/mapping/scans/${encodeURIComponent(scanId)}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }), 'Export...');
    setText('export-status',
      `OK ${data.folder}\n`
      + `points ${data.counts.points_total} (valid ${data.counts.points_valid}, ToF ${data.counts.tof_points}, HC ${data.counts.hc_points})\n`
      + `boxes ${data.counts.boxes_total} (measured ${data.counts.measured_boxes}, prior ${data.counts.prior_boxes})\n`
      + `clean=${data.clean} · run_label=${data.run_label || '-'}`);
    showToast(`Export selesai: ${data.folder}`, 'success', 4200);
    await refreshDatasetIndex();
  } catch (error) {
    setText('export-status', `Gagal export: ${error.message}`);
    showToast(`Gagal export: ${error.message}`, 'error', 4500);
  }
}

async function saveScene() {
  if (!state.loadedScan) {
    showToast('Pilih scan dulu.', 'warn');
    return;
  }
  try {
    setText('scene-status', 'Menyimpan scene 3D...');
    const data = await withBusy($('save-scene'), () => api(
      `/api/mapping/scans/${encodeURIComponent(state.loadedScan)}/scene`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yaw_scale: state.yawScale, map_rotation: state.mapRotation }),
      }), 'Menyimpan...');
    const sizeKb = (Number(data.bytes || 0) / 1024).toFixed(1);
    setText('scene-status',
      `OK ${data.file}\n`
      + `${data.counts.points} points · ${data.counts.boxes} boxes `
      + `(${data.counts.measured_boxes} measured / ${data.counts.prior_boxes} prior) · `
      + `${data.counts.faces} faces · ${sizeKb} KB\n`
      + `metadata: ${data.metadata_file}`);
    showToast(`3D tersimpan: ${data.file}`, 'success', 6000);
  } catch (error) {
    setText('scene-status', `Gagal simpan 3D: ${error.message}`);
    showToast(`Gagal simpan 3D: ${error.message}`, 'error', 4500);
  }
}

async function clearPresence() {
  try {
    await withBusy($('presence-clear'), () => api('/api/mapping/presence/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    }), 'Reset...');
    await refreshPresence();
    setText('presence-detail', 'Presence di-reset manual.');
    showToast('Presence di-reset manual.', 'success');
  } catch (error) {
    setText('presence-detail', `Gagal reset presence: ${error.message}`);
    showToast(`Gagal reset presence: ${error.message}`, 'error', 4500);
  }
}

function projectPoint(point, width, height, radius) {
  const x = Number(point.x_mm) / 1000;
  const y = Number(point.y_mm) / 1000;
  const z = Number(point.z_mm) / 1000;
  const cy = Math.cos(state.viewYaw);
  const sy = Math.sin(state.viewYaw);
  const cp = Math.cos(state.viewPitch);
  const sp = Math.sin(state.viewPitch);
  const x1 = x * cy - y * sy;
  const y1 = x * sy + y * cy;
  const y2 = y1 * sp + z * cp;
  const depth = y1 * cp - z * sp;
  const scale = Math.min(width, height) * 0.72 * state.zoom / (2 * radius + 0.6);
  return {
    x: width / 2 + x1 * scale + Number(state.viewPanX || 0),
    y: height / 2 - y2 * scale + Number(state.viewPanY || 0),
    depth,
  };
}

function drawGrid(ctx, width, height, radius) {
  const steps = 10;
  ctx.lineWidth = 1;
  for (let index = 0; index <= steps; index++) {
    const value = -radius + (2 * radius * index / steps);
    for (const [a, b] of [[value, -radius], [value, radius]]) {
      const p1 = projectPoint({ x_mm: a * 1000, y_mm: b * 1000, z_mm: 0 }, width, height, radius);
      const p2 = projectPoint({ x_mm: a * 1000, y_mm: (b === -radius ? radius : -radius) * 1000, z_mm: 0 }, width, height, radius);
      ctx.strokeStyle = index === steps / 2 ? '#2c4562' : '#1a2a3d';
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    }
    for (const [a, b] of [[-radius, value], [radius, value]]) {
      const p1 = projectPoint({ x_mm: a * 1000, y_mm: b * 1000, z_mm: 0 }, width, height, radius);
      const p2 = projectPoint({ x_mm: (a === -radius ? radius : -radius) * 1000, y_mm: b * 1000, z_mm: 0 }, width, height, radius);
      ctx.strokeStyle = index === steps / 2 ? '#2c4562' : '#1a2a3d';
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    }
  }
  const origin = projectPoint({ x_mm: 0, y_mm: 0, z_mm: 0 }, width, height, radius);
  const axes = [
    { p: { x_mm: radius * 1000, y_mm: 0, z_mm: 0 }, color: '#ff6b6b', label: 'X' },
    { p: { x_mm: 0, y_mm: radius * 1000, z_mm: 0 }, color: '#6bff9c', label: 'Y' },
    { p: { x_mm: 0, y_mm: 0, z_mm: radius * 1000 }, color: '#6bb8ff', label: 'Z' },
  ];
  ctx.font = '12px system-ui';
  for (const axis of axes) {
    const end = projectPoint(axis.p, width, height, radius);
    ctx.strokeStyle = axis.color; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(origin.x, origin.y); ctx.lineTo(end.x, end.y); ctx.stroke();
    ctx.fillStyle = axis.color; ctx.fillText(axis.label, end.x + 4, end.y - 4);
  }
  if (state.showAxis) {
    ctx.font = '9px system-ui';
    ctx.fillStyle = 'rgba(170,195,220,0.65)';
    ctx.textAlign = 'center';
    for (let value = -Math.floor(radius); value <= radius; value += 1) {
      if (value === 0) continue;
      const px = projectPoint({ x_mm: value * 1000, y_mm: -radius * 1000, z_mm: 0 }, width, height, radius);
      ctx.fillText(value.toFixed(0), px.x, px.y + 10);
      const py = projectPoint({ x_mm: -radius * 1000, y_mm: value * 1000, z_mm: 0 }, width, height, radius);
      ctx.fillText(value.toFixed(0), py.x - 8, py.y);
      const pz = projectPoint({ x_mm: 0, y_mm: 0, z_mm: value * 1000 }, width, height, radius);
      ctx.fillText(value.toFixed(0), pz.x - 8, pz.y);
    }
    ctx.textAlign = 'left';
  }
}

function boxCorners(box) {
  const angle = Number(box.angle_deg || 0) * Math.PI / 180;
  const ca = Math.cos(angle), sa = Math.sin(angle);
  const hl = Number(box.length_m || 0) / 2;
  const hw = Number(box.width_m || 0) / 2;
  const cx = Number(box.cx_m || 0), cy = Number(box.cy_m || 0);
  const z0 = Number(box.z_bottom_m || 0), z1 = Number(box.z_top_m || 0.1);
  const corners = [];
  for (const z of [z0, z1]) {
    for (const [u, v] of [[-hl, -hw], [hl, -hw], [hl, hw], [-hl, hw]]) {
      corners.push({ x_mm: (cx + u * ca - v * sa) * 1000, y_mm: (cy + u * sa + v * ca) * 1000, z_mm: z * 1000 });
    }
  }
  return corners;
}

function pointInBoxFootprint(box, x, y) {
  const angle = Number(box.angle_deg || 0) * Math.PI / 180;
  const ca = Math.cos(angle), sa = Math.sin(angle);
  const dx = x - Number(box.cx_m || 0);
  const dy = y - Number(box.cy_m || 0);
  const u = dx * ca + dy * sa;
  const v = -dx * sa + dy * ca;
  return Math.abs(u) <= Number(box.length_m || 0) / 2
    && Math.abs(v) <= Number(box.width_m || 0) / 2;
}

function scaledPoint(point) {
  const scale = Number(state.yawScale);
  const rotation = Number(state.mapRotation) * Math.PI / 180;
  const rotate = Number.isFinite(rotation) && Math.abs(rotation) > 1e-9;
  const yawScale = Number.isFinite(scale) && Math.abs(scale - 1) > 1e-6;
  if (!yawScale && !rotate) return point;
  const x = Number(point.x_mm);
  const y = Number(point.y_mm);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return point;
  const distance = Math.hypot(x, y);
  if (!distance) return point;
  const yaw = Math.atan2(y, x) * (Number.isFinite(scale) ? scale : 1);
  let rx = distance * Math.cos(yaw);
  let ry = distance * Math.sin(yaw);
  if (rotate) {
    const ca = Math.cos(rotation), sa = Math.sin(rotation);
    const nx = rx * ca - ry * sa;
    const ny = rx * sa + ry * ca;
    rx = nx;
    ry = ny;
  }
  return { ...point, x_mm: rx, y_mm: ry };
}

function applyYawScale() {
  const rawYaw = Number($('yaw-scale').value);
  const rawRotation = Number($('map-rotation').value);
  const yaw = Math.max(0.50, Math.min(1.00, Number.isFinite(rawYaw) ? rawYaw : 0.76));
  const rotation = Math.max(-45, Math.min(45, Number.isFinite(rawRotation) ? rawRotation : 10.7));
  state.yawScale = yaw;
  state.mapRotation = rotation;
  try {
    localStorage.setItem('mapping.yawScale', yaw.toFixed(2));
    localStorage.setItem('mapping.mapRotation', rotation.toFixed(1));
  } catch (error) {
    // localStorage can be unavailable in private/embedded contexts.
  }
  $('yaw-scale').value = yaw.toFixed(2);
  $('map-rotation').value = rotation.toFixed(1);
  setText('yaw-scale-note', `yaw ${yaw.toFixed(2)} · rotasi ${rotation.toFixed(1)}° — sesuaikan sampai dinding lurus.`);
  const scanId = state.loadedScan || $('scan-select').value;
  if (scanId) loadPoints(scanId, true);
}

function resetYawScale() {
  $('yaw-scale').value = '1.00';
  $('map-rotation').value = '0.0';
  applyYawScale();
}

function drawBoxes3D(ctx, width, height, radius) {
  const boxes = visibleBoxes();
  const labelScale = Math.max(1, Math.min(1.6, Number(state.zoom) || 1));
  const faces = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]];
  for (const [boxIndex, box] of boxes.entries()) {
    const projected = boxCorners(box).map(point => projectPoint(point, width, height, radius));
    const color = boxColor(box);
    const prior = box.source === 'prior';
    const ordered = faces.map(indices => ({
      indices,
      depth: indices.reduce((sum, index) => sum + projected[index].depth, 0) / indices.length,
    })).sort((a, b) => a.depth - b.depth);
    for (const face of ordered) {
      const [a, b, c, d] = face.indices.map(index => projected[index]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.lineTo(c.x, c.y); ctx.lineTo(d.x, d.y); ctx.closePath();
      ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},${prior ? 0.08 : 0.18})`;
      ctx.fill();
      ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},${prior ? 0.7 : 0.9})`;
      ctx.lineWidth = prior ? 1.0 : (box.label === 'wall' ? 1.6 : 1.2);
      if (prior || box.label === 'wall_edge') ctx.setLineDash([5, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (state.selectedBoxId === box.id) {
      const edges = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6],
        [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
      ctx.save();
      ctx.strokeStyle = 'rgba(255,255,255,0.95)';
      ctx.lineWidth = 3;
      ctx.setLineDash([6, 4]);
      for (const [a, b] of edges) {
        ctx.beginPath();
        ctx.moveTo(projected[a].x, projected[a].y);
        ctx.lineTo(projected[b].x, projected[b].y);
        ctx.stroke();
      }
      ctx.restore();
    }
    const top = projectPoint({
      x_mm: Number(box.cx_m) * 1000, y_mm: Number(box.cy_m) * 1000,
      z_mm: (Number(box.z_top_m) + 0.08) * 1000,
    }, width, height, radius);
    const distance = state.showDistances ? ` · ${formatMeters(boxDistance(box))}` : '';
    const dimensions = `${Number(box.length_m).toFixed(1)}×${Number(box.width_m).toFixed(1)} m`;
    if (state.selectedBoxId === box.id) {
      const text = `${boxName(box)} ${dimensions}${distance}`;
      ctx.font = `${14 * labelScale}px system-ui`;
      ctx.lineWidth = 3 * labelScale;
      ctx.strokeStyle = 'rgba(10,17,28,0.85)';
      ctx.strokeText(text, top.x + 12, top.y - 4);
      ctx.fillStyle = `rgb(${color[0]},${color[1]},${color[2]})`;
      ctx.fillText(text, top.x + 12, top.y - 4);
    } else {
      ctx.beginPath();
      ctx.arc(top.x, top.y, 11 * labelScale, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.92)`;
      ctx.fill();
      ctx.fillStyle = '#0a111c';
      ctx.font = `bold ${12 * labelScale}px system-ui`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(boxIndex + 1), top.x, top.y);
      ctx.textAlign = 'start';
      ctx.textBaseline = 'alphabetic';
    }
  }
}

function drawTag(ctx, x, y, text, color, scale = 1) {
  ctx.font = `${12 * scale}px system-ui`;
  const width = ctx.measureText(text).width + 9 * scale;
  ctx.fillStyle = 'rgba(10,17,28,0.80)';
  ctx.fillRect(x - width / 2, y - 10 * scale, width, 19 * scale);
  ctx.fillStyle = color;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, x, y);
  ctx.textAlign = 'start';
  ctx.textBaseline = 'alphabetic';
}

function drawOccludedWedges(ctx, toScreen, origin, extent, occluded, fovLimit) {
  for (const [start, end] of occluded || []) {
    if (!Number.isFinite(Number(start)) || !Number.isFinite(Number(end))) continue;
    const a0 = Number(start) * Math.PI / 180;
    const a1 = Number(end) * Math.PI / 180;
    const p1 = toScreen(Math.cos(a0) * extent, Math.sin(a0) * extent);
    const p2 = toScreen(Math.cos(a1) * extent, Math.sin(a1) * extent);
    ctx.beginPath();
    ctx.moveTo(origin.x, origin.y);
    ctx.lineTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.closePath();
    ctx.fillStyle = 'rgba(255,80,80,0.10)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,110,110,0.30)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 5]);
    ctx.stroke();
    ctx.setLineDash([]);
    const mid = (a0 + a1) / 2;
    const label = toScreen(Math.cos(mid) * extent * 0.82, Math.sin(mid) * extent * 0.82);
    ctx.fillStyle = 'rgba(255,150,150,0.72)';
    ctx.font = '10px system-ui';
    ctx.fillText('no data', label.x - 18, label.y);
  }
}

function drawHumanTopDown(ctx, toScreen, origin, scale, labelScale = 1) {
  const presence = state.presence;
  if (!presence || !['present', 'holding'].includes(presence.state)
      || presence.gate === 'beyond_wall') return;
  const distance = Number(presence.distance_cm) / 100;
  if (!Number.isFinite(distance) || distance <= 0) return;
  const yaw = Number(state.health?.esp?.scan?.yaw_deg_nominal || 0) * Math.PI / 180;
  const point = toScreen(distance * Math.cos(yaw), distance * Math.sin(yaw));
  const size = 0.5 * scale;
  const color = presence.class === 'non-human'
    ? [255, 170, 70]
    : (presence.state === 'holding' ? [255, 210, 90] : [90, 255, 170]);
  ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.14)`;
  ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},0.95)`;
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 3]);
  ctx.fillRect(point.x - size / 2, point.y - size / 2, size, size);
  ctx.strokeRect(point.x - size / 2, point.y - size / 2, size, size);
  ctx.setLineDash([]);
  ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},0.65)`;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(origin.x, origin.y);
  ctx.lineTo(point.x, point.y);
  ctx.stroke();
  const label = `${String(presence.class || 'human').toUpperCase()} ${distance.toFixed(2)} m · `
    + `${Math.round(Number(presence.confidence || 0) * 100)}%`;
  drawTag(ctx, point.x, point.y - size / 2 - 12, label,
    `rgb(${color[0]},${color[1]},${color[2]})`, labelScale);
}

function selectedPointSet() {
  return new Set((state.selectedPointIndices || []).map(Number));
}

function drawSelectionOverlay(ctx, canvasId) {
  const rect = state.selectionRect;
  if (!rect || rect.canvas !== canvasId) return;
  const x = Math.min(rect.x0, rect.x1);
  const y = Math.min(rect.y0, rect.y1);
  const width = Math.abs(rect.x1 - rect.x0);
  const height = Math.abs(rect.y1 - rect.y0);
  ctx.fillStyle = 'rgba(255,255,255,0.08)';
  ctx.fillRect(x, y, width, height);
  ctx.strokeStyle = 'rgba(255,255,255,0.9)';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([5, 4]);
  ctx.strokeRect(x, y, width, height);
  ctx.setLineDash([]);
}

function drawRoomOutline2D(ctx, toScreen) {
  if (!state.priorVisible || (state.roomOutline || []).length < 3) return;
  ctx.beginPath();
  state.roomOutline.forEach(([x, y], index) => {
    const point = toScreen(Number(x), Number(y));
    index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y);
  });
  ctx.closePath();
  ctx.fillStyle = 'rgba(120,255,200,0.04)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(120,255,200,0.45)';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([8, 6]);
  ctx.stroke();
  ctx.setLineDash([]);
  const labelCorner = state.roomOutline.reduce((best, point) =>
    (Number(point[0]) <= Number(best[0]) && Number(point[1]) >= Number(best[1]) ? point : best),
  state.roomOutline[0]);
  const first = toScreen(Number(labelCorner[0]), Number(labelCorner[1]));
  const room = state.room || {};
  const dimensions = room.width_m && room.depth_m
    ? `${Number(room.width_m).toFixed(2)}×${Number(room.depth_m).toFixed(2)} m` : 'prior';
  ctx.fillStyle = 'rgba(120,255,200,0.85)';
  ctx.font = '12px system-ui';
  ctx.fillText(`prior room ${dimensions}`, first.x + 6, first.y - 6);
}

function drawRoomOutline3D(ctx, width, height, radius) {
  if (!state.priorVisible || (state.roomOutline || []).length < 3) return;
  ctx.beginPath();
  state.roomOutline.forEach(([x, y], index) => {
    const point = projectPoint({
      x_mm: Number(x) * 1000, y_mm: Number(y) * 1000, z_mm: 0,
    }, width, height, radius);
    index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y);
  });
  ctx.closePath();
  ctx.strokeStyle = 'rgba(120,255,200,0.4)';
  ctx.lineWidth = 1.4;
  ctx.setLineDash([7, 5]);
  ctx.stroke();
  ctx.setLineDash([]);
}

function drawBoxPivot2D(ctx, box, toScreen, selected) {
  const center = toScreen(Number(box.cx_m), Number(box.cy_m));
  const size = selected ? 12 : 5;
  ctx.save();
  ctx.strokeStyle = selected ? 'rgba(255,255,255,0.98)' : 'rgba(255,255,255,0.55)';
  ctx.lineWidth = selected ? 2 : 1;
  ctx.beginPath();
  ctx.moveTo(center.x - size, center.y);
  ctx.lineTo(center.x + size, center.y);
  ctx.moveTo(center.x, center.y - size);
  ctx.lineTo(center.x, center.y + size);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(center.x, center.y, selected ? 5 : 2.5, 0, Math.PI * 2);
  ctx.stroke();
  if (selected) {
    const angle = Number(box.angle_deg || 0) * Math.PI / 180;
    const tip = toScreen(Number(box.cx_m) + Math.cos(angle) * 0.32,
      Number(box.cy_m) + Math.sin(angle) * 0.32);
    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(center.x, center.y);
    ctx.lineTo(tip.x, tip.y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(tip.x, tip.y, 2.5, 0, Math.PI * 2);
    ctx.fill();
    drawTag(ctx, center.x, center.y + 22,
      `pivot ${Number(box.cx_m).toFixed(2)}, ${Number(box.cy_m).toFixed(2)}`,
      '#ffffff', 0.92);
  }
  ctx.restore();
}

function resizeHandleList(box, toScreen) {
  const corners = boxCorners(box).slice(0, 4).map(point =>
    toScreen(Number(point.x_mm) / 1000, Number(point.y_mm) / 1000));
  const cornerSigns = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
  const edgeSigns = [[0, -1], [1, 0], [0, 1], [-1, 0]];
  const handles = corners.map((point, index) => ({
    ...point,
    su: cornerSigns[index][0],
    sv: cornerSigns[index][1],
    kind: 'corner',
  }));
  for (let index = 0; index < 4; index += 1) {
    const a = corners[index];
    const b = corners[(index + 1) % 4];
    handles.push({
      x: (a.x + b.x) / 2,
      y: (a.y + b.y) / 2,
      su: edgeSigns[index][0],
      sv: edgeSigns[index][1],
      kind: 'edge',
    });
  }
  return handles;
}

function handleAtPoint(box, point, toScreen) {
  let best = null;
  let bestDistance = Infinity;
  for (const handle of resizeHandleList(box, toScreen)) {
    const distance = Math.hypot(handle.x - point.x, handle.y - point.y);
    const limit = handle.kind === 'corner' ? 13 : 11;
    if (distance <= limit && distance < bestDistance) {
      best = handle;
      bestDistance = distance;
    }
  }
  return best;
}

function drawResizeHandles2D(ctx, box, toScreen) {
  const handles = resizeHandleList(box, toScreen);
  ctx.save();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = 'rgba(10,17,28,0.95)';
  for (const handle of handles) {
    ctx.fillStyle = '#ffffff';
    if (handle.kind === 'corner') {
      ctx.fillRect(handle.x - 4.5, handle.y - 4.5, 9, 9);
      ctx.strokeRect(handle.x - 4.5, handle.y - 4.5, 9, 9);
    } else {
      ctx.beginPath();
      ctx.arc(handle.x, handle.y, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
  }
  ctx.restore();
}

function drawAxisTicks2D(ctx, toScreen, extent) {
  if (!state.showAxis) return;
  const step = 0.5;
  ctx.save();
  ctx.fillStyle = 'rgba(170,195,220,0.72)';
  ctx.strokeStyle = 'rgba(170,195,220,0.35)';
  ctx.font = '10px system-ui';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (let value = -Math.floor(extent / step) * step; value <= extent; value += step) {
    const p = toScreen(value, -extent);
    ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x, p.y + 4); ctx.stroke();
    if (Math.abs(value) > 0.01) ctx.fillText(value.toFixed(1), p.x, p.y + 6);
  }
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let value = -Math.floor(extent / step) * step; value <= extent; value += step) {
    const p = toScreen(-extent, value);
    ctx.beginPath(); ctx.moveTo(p.x - 4, p.y); ctx.lineTo(p.x, p.y); ctx.stroke();
    if (Math.abs(value) > 0.01) ctx.fillText(value.toFixed(1), p.x - 6, p.y);
  }
  const bottomRight = toScreen(extent, -extent);
  const topLeft = toScreen(-extent, extent);
  ctx.textAlign = 'left';
  ctx.fillStyle = 'rgba(120,180,255,0.85)';
  ctx.fillText('X (m)', bottomRight.x - 34, bottomRight.y + 20);
  ctx.fillText('Y (m)', topLeft.x - 6, topLeft.y - 12);
  ctx.restore();
}

function drawTopDown() {
  const canvas = $('topdown');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const width = canvas.width, height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  const points = state.points.filter(p => p.x_mm != null && p.y_mm != null).map(scaledPoint);
  const boxes = visibleBoxes();
  const presence = state.presence;
  const hlk = state.health?.esp?.sensors?.hlk;
  const hlkRadius = presence?.distance_cm
    ? Number(presence.distance_cm) / 100
    : (hlk?.valid ? Number(hlk.distance_cm || 0) / 100 : 0);
  let extent = 1.0;
  for (const point of points) extent = Math.max(extent, Math.abs(Number(point.x_mm)) / 1000, Math.abs(Number(point.y_mm)) / 1000);
  for (const box of boxes) {
    for (const point of boxCorners(box)) extent = Math.max(extent, Math.abs(point.x_mm) / 1000, Math.abs(point.y_mm) / 1000);
  }
  extent = Math.max(extent, hlkRadius) * 1.15;
  const zoom = Math.max(0.4, Math.min(8, Number(state.topZoom) || 1));
  const scale = Math.min(width, height) * 0.42 / extent * zoom;
  const toScreen = (x, y) => ({
    x: width / 2 + x * scale + Number(state.topPanX || 0),
    y: height / 2 - y * scale + Number(state.topPanY || 0),
  });
  const labelScale = Math.max(1, Math.min(1.6, zoom));
  ctx.lineWidth = 1;
  const start = -Math.ceil(extent * 2) / 2;
  for (let value = start; value <= extent; value += 0.5) {
    const p1 = toScreen(value, -extent), p2 = toScreen(value, extent);
    const p3 = toScreen(-extent, value), p4 = toScreen(extent, value);
    ctx.strokeStyle = Math.abs(value) < 0.01 ? '#2c4562' : '#1a2a3d';
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(p3.x, p3.y); ctx.lineTo(p4.x, p4.y); ctx.stroke();
  }
  drawAxisTicks2D(ctx, toScreen, extent);
  const origin = toScreen(0, 0);
  const fovLimit = Number(state.reconstruction?.fov_limit_deg || 60);
  drawOccludedWedges(ctx, toScreen, origin, extent,
    state.reconstruction?.occluded_deg || [], fovLimit);
  const fov = fovLimit * Math.PI / 180;
  ctx.strokeStyle = 'rgba(120,180,255,0.45)';
  ctx.setLineDash([5, 5]);
  for (const angle of [-fov, fov]) {
    const end = toScreen(Math.cos(angle) * extent, Math.sin(angle) * extent);
    ctx.beginPath(); ctx.moveTo(origin.x, origin.y); ctx.lineTo(end.x, end.y); ctx.stroke();
  }
  ctx.setLineDash([]);
  const scanStart = toScreen(Math.cos(-fov) * extent * 0.82, Math.sin(-fov) * extent * 0.82);
  const scanEnd = toScreen(Math.cos(fov) * extent * 0.82, Math.sin(fov) * extent * 0.82);
  ctx.fillStyle = 'rgba(150,200,255,0.9)';
  ctx.font = '12px system-ui';
  ctx.fillText('start −60° (kursi)', scanStart.x - 24, scanStart.y - 8);
  ctx.fillText('end +60° (kasur/lemari)', scanEnd.x + 4, scanEnd.y - 8);
  ctx.fillText('scan searah jarum jam', origin.x + 8, origin.y + 20);
  drawRoomOutline2D(ctx, toScreen);
  if (state.showDistances) {
    for (const [boxIndex, box] of boxes.entries()) {
      if (box.source === 'prior') continue;
      const color = boxColor(box);
      let anchor;
      if (box.label === 'wall' || box.label === 'wall_edge') {
        const corners = boxCorners(box).slice(0, 4)
          .map(point => ({ x: Number(point.x_mm) / 1000, y: Number(point.y_mm) / 1000 }));
        const nearest = corners.reduce((best, point) =>
          Math.hypot(point.x, point.y) < Math.hypot(best.x, best.y) ? point : best, corners[0]);
        anchor = toScreen(nearest.x, nearest.y);
      } else {
        anchor = toScreen(Number(box.cx_m), Number(box.cy_m));
      }
      ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},0.32)`;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(origin.x, origin.y); ctx.lineTo(anchor.x, anchor.y); ctx.stroke();
      ctx.setLineDash([]);
      const mid = {
        x: origin.x + (anchor.x - origin.x) * 0.62,
        y: origin.y + (anchor.y - origin.y) * 0.62 + (boxIndex % 2 === 0 ? -8 : 8),
      };
      drawTag(ctx, mid.x, mid.y, `#${boxIndex + 1} ${formatMeters(boxDistance(box))}`,
        `rgb(${color[0]},${color[1]},${color[2]})`, labelScale);
    }
  }
  if (state.viewMode !== 'blocks') {
    const selected = selectedPointSet();
    for (const point of points) {
      const screen = toScreen(Number(point.x_mm) / 1000, Number(point.y_mm) / 1000);
      const isSelected = selected.has(Number(point.point_index));
      ctx.fillStyle = isSelected ? '#ffffff'
        : (point.range_source === 'tof' ? 'rgba(80,220,255,0.85)' : 'rgba(255,170,60,0.85)');
      ctx.beginPath();
      ctx.arc(screen.x, screen.y, isSelected ? 4.5 : 2.2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  if (state.viewMode !== 'points') {
    for (const [boxIndex, box] of boxes.entries()) {
      const corners = boxCorners(box).slice(0, 4).map(point => toScreen(Number(point.x_mm) / 1000, Number(point.y_mm) / 1000));
      const color = boxColor(box);
      const prior = box.source === 'prior';
      ctx.beginPath(); ctx.moveTo(corners[0].x, corners[0].y);
      for (const corner of corners.slice(1)) ctx.lineTo(corner.x, corner.y);
      ctx.closePath();
      ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},${prior ? 0.08 : 0.22})`;
      ctx.fill();
      ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},${prior ? 0.75 : 0.95})`;
      ctx.lineWidth = prior ? 1.4 : (box.label === 'wall' ? 2.2 : 1.6);
      if (prior || box.label === 'wall_edge') ctx.setLineDash([5, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
      if (state.selectedBoxId === box.id) {
        ctx.save();
        ctx.strokeStyle = 'rgba(255,255,255,0.95)';
        ctx.lineWidth = 3.5;
        ctx.setLineDash([7, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#ffffff';
        for (const corner of corners) {
          ctx.fillRect(corner.x - 3.5, corner.y - 3.5, 7, 7);
        }
        ctx.restore();
        const tag = toScreen(Number(box.cx_m),
          Number(box.cy_m) + Number(box.width_m) / 2 + 0.12);
        drawTag(ctx, tag.x, tag.y,
          `SELECTED #${boxIndex + 1} ${boxName(box)}`, '#ffffff', labelScale);
      }
      const label = toScreen(Number(box.cx_m), Number(box.cy_m));
      if (box.label === 'wall' || box.label === 'wall_edge' || box.source === 'prior') {
        ctx.beginPath();
        ctx.arc(label.x, label.y, 11 * labelScale, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.92)`;
        ctx.fill();
        ctx.fillStyle = '#0a111c';
        ctx.font = `bold ${12 * labelScale}px system-ui`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(boxIndex + 1), label.x, label.y);
        ctx.textAlign = 'start';
        ctx.textBaseline = 'alphabetic';
      } else {
        const shortName = box.label === 'door-wc' ? 'WC'
          : box.label === 'door-exit' ? 'exit' : box.label;
        const text = `#${boxIndex + 1} ${shortName}`;
        ctx.font = `${14 * labelScale}px system-ui`;
        ctx.lineWidth = 3 * labelScale;
        ctx.strokeStyle = 'rgba(10,17,28,0.85)';
        ctx.strokeText(text, label.x + 4, label.y - 4);
        ctx.fillStyle = `rgb(${color[0]},${color[1]},${color[2]})`;
        ctx.fillText(text, label.x + 4, label.y - 4);
      }
      if (box.source === 'prior' || state.selectedBoxId === box.id) {
        drawBoxPivot2D(ctx, box, toScreen, state.selectedBoxId === box.id);
      }
      if (state.selectedBoxId === box.id) {
        drawResizeHandles2D(ctx, box, toScreen);
        const dimension = toScreen(Number(box.cx_m),
          Number(box.cy_m) - Number(box.width_m) / 2 - 0.16);
        drawTag(ctx, dimension.x, dimension.y,
          `L ${Number(box.length_m).toFixed(2)} · W ${Number(box.width_m).toFixed(2)} · ${Number(box.angle_deg).toFixed(0)}°`,
          '#ffffff', labelScale);
      }
    }
  }
  drawHumanTopDown(ctx, toScreen, origin, scale, labelScale);
  ctx.fillStyle = '#ffffff';
  ctx.beginPath(); ctx.arc(origin.x, origin.y, 4, 0, Math.PI * 2); ctx.fill();
  ctx.font = '12px system-ui';
  ctx.strokeStyle = '#ff6b6b'; ctx.beginPath(); ctx.moveTo(origin.x, origin.y); ctx.lineTo(origin.x + 0.5 * scale, origin.y); ctx.stroke();
  ctx.fillStyle = '#ff6b6b'; ctx.fillText('X', origin.x + 0.5 * scale + 4, origin.y - 4);
  ctx.strokeStyle = '#6bff9c'; ctx.beginPath(); ctx.moveTo(origin.x, origin.y); ctx.lineTo(origin.x, origin.y - 0.5 * scale); ctx.stroke();
  ctx.fillStyle = '#6bff9c'; ctx.fillText('Y', origin.x + 4, origin.y - 0.5 * scale - 4);
  const barStart = { x: 24, y: height - 24 };
  ctx.strokeStyle = '#e6edf6'; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(barStart.x, barStart.y); ctx.lineTo(barStart.x + scale, barStart.y); ctx.stroke();
  ctx.fillStyle = '#e6edf6'; ctx.font = '12px system-ui'; ctx.fillText('1 m', barStart.x + scale / 2 - 12, barStart.y - 6);
  if (hlkRadius > 0 && !(presence && ['present', 'holding'].includes(presence.state))) {
    const gated = presence?.gate === 'beyond_wall';
    const yaw = Number(state.health?.esp?.scan?.yaw_deg_nominal || 0) * Math.PI / 180;
    const screen = toScreen(hlkRadius * Math.cos(yaw), hlkRadius * Math.sin(yaw));
    ctx.fillStyle = gated ? 'rgba(255,170,70,0.22)' : 'rgba(255,80,200,0.28)';
    ctx.strokeStyle = gated ? 'rgba(255,190,90,0.85)' : 'rgba(255,120,220,0.85)';
    ctx.beginPath(); ctx.arc(screen.x, screen.y, 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = gated ? '#ffc46b' : '#ff9be0'; ctx.font = '11px system-ui';
    ctx.fillText(gated
      ? `HLK beyond wall ${hlkRadius.toFixed(2)} m`
      : `HLK ${hlkRadius.toFixed(2)} m`, screen.x + 6, screen.y - 6);
  }
  drawSelectionOverlay(ctx, 'topdown');
}

function drawHuman3D(ctx, width, height, radius) {
  const presence = state.presence;
  if (!presence || !['present', 'holding'].includes(presence.state)
      || presence.gate === 'beyond_wall') return;
  const distance = Number(presence.distance_cm) / 100;
  if (!Number.isFinite(distance) || distance <= 0) return;
  const yaw = Number(state.health?.esp?.scan?.yaw_deg_nominal || 0) * Math.PI / 180;
  const cx = distance * Math.cos(yaw);
  const cy = distance * Math.sin(yaw);
  const radiusM = 0.24, heightM = 1.70, segments = 18;
  const bottom = [], top = [];
  for (let index = 0; index < segments; index++) {
    const angle = index / segments * Math.PI * 2;
    const x = (cx + radiusM * Math.cos(angle)) * 1000;
    const y = (cy + radiusM * Math.sin(angle)) * 1000;
    bottom.push(projectPoint({ x_mm: x, y_mm: y, z_mm: 0 }, width, height, radius));
    top.push(projectPoint({ x_mm: x, y_mm: y, z_mm: heightM * 1000 }, width, height, radius));
  }
  const color = presence.class === 'non-human'
    ? [255, 170, 70]
    : (presence.state === 'holding' ? [255, 210, 90] : [90, 255, 170]);
  const labelScale = Math.max(1, Math.min(1.6, Number(state.zoom) || 1));
  ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.12)`;
  ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},0.55)`;
  ctx.lineWidth = 1.2;
  for (let index = 0; index < segments; index++) {
    const next = (index + 1) % segments;
    ctx.beginPath();
    ctx.moveTo(bottom[index].x, bottom[index].y);
    ctx.lineTo(bottom[next].x, bottom[next].y);
    ctx.lineTo(top[next].x, top[next].y);
    ctx.lineTo(top[index].x, top[index].y);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
  ctx.beginPath();
  top.forEach((point, index) => (index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)));
  ctx.closePath();
  ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.28)`;
  ctx.fill();
  ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},0.95)`;
  ctx.lineWidth = 1.8;
  ctx.stroke();
  const labelPoint = projectPoint({
    x_mm: cx * 1000, y_mm: cy * 1000, z_mm: (heightM + 0.15) * 1000,
  }, width, height, radius);
  const text = `${String(presence.class || 'human').toUpperCase()} ${distance.toFixed(2)} m · `
    + `${Math.round(Number(presence.confidence || 0) * 100)}%`;
  ctx.font = `${14 * labelScale}px system-ui`;
  ctx.lineWidth = 3 * labelScale;
  ctx.strokeStyle = 'rgba(10,17,28,0.85)';
  ctx.strokeText(text, labelPoint.x + 6, labelPoint.y - 4);
  ctx.fillStyle = `rgb(${color[0]},${color[1]},${color[2]})`;
  ctx.fillText(text, labelPoint.x + 6, labelPoint.y - 4);
}

function drawCloud() {
  const canvas = $('cloud');
  const ctx = canvas.getContext('2d');
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  const points = state.points.filter(p => p.x_mm != null && p.y_mm != null && p.z_mm != null).map(scaledPoint);
  const boxes = visibleBoxes();
  const presence = state.presence;
  const hlk = state.health?.esp?.sensors?.hlk;
  const hlkRadius = presence?.distance_cm
    ? Number(presence.distance_cm) / 100
    : (hlk?.valid ? Number(hlk.distance_cm || 0) / 100 : 0);
  const boxExtents = boxes.flatMap(box => boxCorners(box).map(p => Math.max(
    Math.abs(Number(p.x_mm)), Math.abs(Number(p.y_mm)), Math.abs(Number(p.z_mm))) / 1000));
  const maxRadius = Math.max(1.0, hlkRadius, ...points.map(p => Math.max(
    Math.abs(Number(p.x_mm)), Math.abs(Number(p.y_mm)), Math.abs(Number(p.z_mm))) / 1000), ...boxExtents);
  drawGrid(ctx, width, height, maxRadius);
  drawRoomOutline3D(ctx, width, height, maxRadius);
  if (state.viewMode !== 'blocks') {
    const selected = selectedPointSet();
    const projected = points.map(point => ({
      point,
      screen: projectPoint(point, width, height, maxRadius),
    })).sort((a, b) => a.screen.depth - b.screen.depth);
    for (const item of projected) {
      const source = item.point.range_source;
      const base = source === 'tof' ? [80, 220, 255] : [255, 170, 60];
      const z = Number(item.point.z_mm) || 0;
      const alpha = Math.max(0.35, Math.min(1, 0.55 + z / (maxRadius * 2000)));
      const isSelected = selected.has(Number(item.point.point_index));
      ctx.fillStyle = isSelected ? '#ffffff' : `rgba(${base[0]},${base[1]},${base[2]},${alpha})`;
      ctx.beginPath();
      ctx.arc(item.screen.x, item.screen.y, isSelected ? 4.8 : (source === 'tof' ? 2.6 : 2.2), 0, Math.PI * 2);
      ctx.fill();
    }
  }
  if (state.viewMode !== 'points') drawBoxes3D(ctx, width, height, maxRadius);
  drawHuman3D(ctx, width, height, maxRadius);
  if (hlkRadius > 0 && !(presence && ['present', 'holding'].includes(presence.state))) {
    const gated = presence?.gate === 'beyond_wall';
    const yawDeg = Number(state.health?.esp?.scan?.yaw_deg_nominal || 0);
    const yaw = yawDeg * Math.PI / 180;
    const marker = projectPoint({
      x_mm: hlkRadius * 1000 * Math.cos(yaw),
      y_mm: hlkRadius * 1000 * Math.sin(yaw),
      z_mm: 0,
    }, width, height, maxRadius);
    const markerRadius = 8 + Math.min(18, Number(hlk?.energy || 0) / 6);
    ctx.fillStyle = gated ? 'rgba(255,170,70,0.20)' : 'rgba(255,80,200,0.22)';
    ctx.strokeStyle = gated ? 'rgba(255,190,90,0.95)' : 'rgba(255,120,220,0.95)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(marker.x, marker.y, markerRadius, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = gated ? '#ffc46b' : '#ffb8e8';
    ctx.font = '12px system-ui';
    ctx.fillText(gated
      ? `HLK beyond wall ${hlkRadius.toFixed(2)} m`
      : `HLK ${hlk?.distance_cm ?? '—'} cm`, marker.x + markerRadius + 4, marker.y - 4);
  }
  if (!points.length && !boxes.length) {
    ctx.fillStyle = '#9fb1c7';
    ctx.font = '16px system-ui';
    ctx.fillText('Belum ada point cloud. Jalankan scan atau pilih scan.', 24, 36);
  }
  drawSelectionOverlay(ctx, 'cloud');
}

function canvasPoint(event, canvas) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left) * canvas.width / rect.width,
    y: (event.clientY - rect.top) * canvas.height / rect.height,
  };
}

function pointInPolygon(point, polygon) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index++) {
    const xi = polygon[index].x, yi = polygon[index].y;
    const xj = polygon[previous].x, yj = polygon[previous].y;
    if (((yi > point.y) !== (yj > point.y))
        && (point.x < (xj - xi) * (point.y - yi) / (yj - yi) + xi)) {
      inside = !inside;
    }
  }
  return inside;
}

function topDownTransform(canvas) {
  const points = state.points.filter(p => p.x_mm != null && p.y_mm != null).map(scaledPoint);
  const boxes = visibleBoxes();
  const hlk = state.health?.esp?.sensors?.hlk;
  const hlkRadius = state.presence?.distance_cm
    ? Number(state.presence.distance_cm) / 100
    : (hlk?.valid ? Number(hlk.distance_cm || 0) / 100 : 0);
  let extent = 1.0;
  for (const point of points) {
    extent = Math.max(extent, Math.abs(Number(point.x_mm)) / 1000,
      Math.abs(Number(point.y_mm)) / 1000);
  }
  for (const box of boxes) {
    for (const point of boxCorners(box)) {
      extent = Math.max(extent, Math.abs(point.x_mm) / 1000, Math.abs(point.y_mm) / 1000);
    }
  }
  extent = Math.max(extent, hlkRadius) * 1.15;
  const zoom = Math.max(0.4, Math.min(8, Number(state.topZoom) || 1));
  const scale = Math.min(canvas.width, canvas.height) * 0.42 / extent * zoom;
  const toScreen = (x, y) => ({
    x: canvas.width / 2 + x * scale + Number(state.topPanX || 0),
    y: canvas.height / 2 - y * scale + Number(state.topPanY || 0),
  });
  const toWorld = (screenX, screenY) => ({
    x: (screenX - canvas.width / 2 - Number(state.topPanX || 0)) / scale,
    y: -(screenY - canvas.height / 2 - Number(state.topPanY || 0)) / scale,
  });
  return { points, boxes, extent, scale, toScreen, toWorld };
}

function cloudTransform(canvas) {
  const points = state.points.filter(p => p.x_mm != null && p.y_mm != null && p.z_mm != null).map(scaledPoint);
  const boxes = visibleBoxes();
  const hlk = state.health?.esp?.sensors?.hlk;
  const hlkRadius = state.presence?.distance_cm
    ? Number(state.presence.distance_cm) / 100
    : (hlk?.valid ? Number(hlk.distance_cm || 0) / 100 : 0);
  const boxExtents = boxes.flatMap(box => boxCorners(box).map(p => Math.max(
    Math.abs(Number(p.x_mm)), Math.abs(Number(p.y_mm)), Math.abs(Number(p.z_mm))) / 1000));
  const maxRadius = Math.max(1.0, hlkRadius, ...points.map(p => Math.max(
    Math.abs(Number(p.x_mm)), Math.abs(Number(p.y_mm)), Math.abs(Number(p.z_mm))) / 1000), ...boxExtents);
  return { points, boxes, maxRadius };
}

function selectBoxAt(canvasId, point) {
  const canvas = $(canvasId);
  const boxes = visibleBoxes();
  const hits = [];
  if (canvasId === 'topdown') {
    const view = topDownTransform(canvas);
    for (const box of boxes) {
      const polygon = boxCorners(box).slice(0, 4).map(p =>
        view.toScreen(Number(p.x_mm) / 1000, Number(p.y_mm) / 1000));
      if (pointInPolygon(point, polygon)) hits.push(box);
    }
  } else {
    const view = cloudTransform(canvas);
    const faces = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4],
      [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]];
    for (const box of boxes) {
      const projected = boxCorners(box).map(p =>
        projectPoint(p, canvas.width, canvas.height, view.maxRadius));
      const isHit = faces.some(face => pointInPolygon(point, face.map(index => projected[index])));
      if (isHit) hits.push(box);
    }
  }
  if (!hits.length) return null;
  // Priors/manual boxes win over walls; among equals, the smallest footprint
  // wins so a door embedded in a wall is selectable. Clicking the same spot
  // again cycles through overlapping boxes.
  hits.sort((a, b) => (boxSelectionRank(a) - boxSelectionRank(b))
    || (boxFootprintArea(a) - boxFootprintArea(b)));
  const key = `${canvasId}:${Math.round(point.x)}:${Math.round(point.y)}`;
  let index = 0;
  if (state.lastBoxPick?.key === key) {
    const current = hits.findIndex(box => box.id === state.selectedBoxId);
    index = (current + 1) % hits.length;
  }
  state.lastBoxPick = { key, ids: hits.map(box => box.id) };
  const hit = hits[index];
  selectBoxById(hit.id);
  return hit;
}

function selectPointsInRect(canvasId, rect, mode = 'replace') {
  const canvas = $(canvasId);
  const selected = new Set(mode === 'replace' ? [] : (state.selectedPointIndices || []).map(Number));
  const x0 = Math.min(rect.x0, rect.x1), x1 = Math.max(rect.x0, rect.x1);
  const y0 = Math.min(rect.y0, rect.y1), y1 = Math.max(rect.y0, rect.y1);
  if (canvasId === 'topdown') {
    const view = topDownTransform(canvas);
    for (const point of view.points) {
      const screen = view.toScreen(Number(point.x_mm) / 1000, Number(point.y_mm) / 1000);
      if (screen.x < x0 || screen.x > x1 || screen.y < y0 || screen.y > y1) continue;
      const index = Number(point.point_index);
      if (!Number.isFinite(index)) continue;
      if (mode === 'subtract') selected.delete(index); else selected.add(index);
    }
  } else {
    const view = cloudTransform(canvas);
    for (const point of view.points) {
      const screen = projectPoint(point, canvas.width, canvas.height, view.maxRadius);
      if (screen.x < x0 || screen.x > x1 || screen.y < y0 || screen.y > y1) continue;
      if (!state.selectThrough
          && (screen.depth < Number(state.selectDepthMin)
              || screen.depth > Number(state.selectDepthMax))) continue;
      const index = Number(point.point_index);
      if (!Number.isFinite(index)) continue;
      if (mode === 'subtract') selected.delete(index); else selected.add(index);
    }
  }
  state.selectedPointIndices = Array.from(selected).sort((a, b) => a - b);
  updateSelectionStatus();
  drawCloud();
  drawTopDown();
}

function updateSelectionStatus() {
  const count = (state.selectedPointIndices || []).length;
  setText('selection-status', `${count} titik terpilih`);
}

function clearSelection() {
  state.selectedPointIndices = [];
  state.selectionRect = null;
  updateSelectionStatus();
  drawCloud();
  drawTopDown();
}

async function applyPointLabel() {
  const label = String($('point-label').value || '').trim();
  if (!label) {
    setText('selection-status', 'Isi label titik terlebih dahulu.');
    return;
  }
  const indices = (state.selectedPointIndices || []).map(Number);
  if (!indices.length) {
    setText('selection-status', 'Belum ada titik yang dipilih.');
    return;
  }
  const next = annotationsClone();
  if (!next.point_labels) next.point_labels = {};
  const chosen = new Set(indices);
  for (const key of Object.keys(next.point_labels)) {
    next.point_labels[key] = next.point_labels[key]
      .filter(index => !chosen.has(Number(index)));
  }
  next.point_labels[label] = Array.from(new Set([
    ...(next.point_labels[label] || []).map(Number),
    ...indices,
  ])).sort((a, b) => a - b);
  ensureLabelCatalog(next, label);
  try {
    await saveAnnotations(next, `${indices.length} titik → ${label}.`);
    state.selectedPointIndices = [];
    updateSelectionStatus();
  } catch (error) {
    setText('selection-status', `Gagal label titik: ${error.message}`);
  }
}

async function createBoxFromSelection() {
  const indices = new Set((state.selectedPointIndices || []).map(Number));
  if (indices.size < 3) {
    setText('selection-status', 'Pilih minimal 3 titik untuk membuat box.');
    return;
  }
  const points = state.points
    .filter(point => indices.has(Number(point.point_index)))
    .map(scaledPoint);
  if (!points.length) {
    setText('selection-status', 'Titik terpilih tidak ditemukan.');
    return;
  }
  const xs = points.map(point => Number(point.x_mm) / 1000);
  const ys = points.map(point => Number(point.y_mm) / 1000);
  const zs = points.map(point => Number(point.z_mm) / 1000);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const label = String($('point-label').value || $('box-label').value || 'object').trim() || 'object';
  const next = annotationsClone();
  if (!next.manual_boxes) next.manual_boxes = [];
  next.manual_boxes.push({
    id: `manual:${Date.now()}`,
    label,
    cx_m: (x0 + x1) / 2,
    cy_m: (y0 + y1) / 2,
    angle_deg: 0,
    length_m: Math.max(0.05, x1 - x0),
    width_m: Math.max(0.05, y1 - y0),
    z_bottom_m: 0,
    z_top_m: Math.max(0.05, Math.max(...zs)),
    source: 'manual',
  });
  ensureLabelCatalog(next, label);
  try {
    await saveAnnotations(next, `Box ${label} dibuat dari ${indices.size} titik.`);
    state.selectedPointIndices = [];
    updateSelectionStatus();
  } catch (error) {
    setText('selection-status', `Gagal membuat box: ${error.message}`);
  }
}

function bindCanvas() {
  const canvas = $('cloud');
  let mode = null;
  let lastX = 0;
  let lastY = 0;
  canvas.addEventListener('contextmenu', event => event.preventDefault());
  canvas.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    const point = canvasPoint(event, canvas);
    if (event.button === 2) {
      mode = 'orbit';
      lastX = event.clientX; lastY = event.clientY;
    } else if (event.button === 1) {
      mode = 'pan';
      lastX = event.clientX; lastY = event.clientY;
    } else if (event.button === 0) {
      mode = 'select';
      state.selectionRect = { canvas: 'cloud', x0: point.x, y0: point.y, x1: point.x, y1: point.y };
    }
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!mode) return;
    if (mode === 'orbit') {
      state.viewYaw += (event.clientX - lastX) * 0.01;
      state.viewPitch = Math.max(-1.2, Math.min(1.2,
        state.viewPitch + (event.clientY - lastY) * 0.008));
      lastX = event.clientX; lastY = event.clientY;
      drawCloud();
    } else if (mode === 'pan') {
      state.viewPanX += event.clientX - lastX;
      state.viewPanY += event.clientY - lastY;
      lastX = event.clientX; lastY = event.clientY;
      drawCloud();
    } else if (mode === 'select' && state.selectionRect) {
      const point = canvasPoint(event, canvas);
      state.selectionRect.x1 = point.x;
      state.selectionRect.y1 = point.y;
      drawCloud();
    }
  });
  canvas.addEventListener('pointerup', (event) => {
    if (mode === 'select' && state.selectionRect) {
      const rect = state.selectionRect;
      const width = Math.abs(rect.x1 - rect.x0);
      const height = Math.abs(rect.y1 - rect.y0);
      if (width < 4 && height < 4) {
        selectBoxAt('cloud', { x: rect.x1, y: rect.y1 });
      } else {
        selectPointsInRect('cloud', rect,
          event.shiftKey ? 'add' : (event.altKey ? 'subtract' : 'replace'));
      }
    }
    mode = null;
    state.selectionRect = null;
    drawCloud();
  });
  canvas.addEventListener('pointercancel', () => {
    mode = null;
    state.selectionRect = null;
    drawCloud();
  });
  canvas.addEventListener('wheel', (event) => {
    event.preventDefault();
    state.zoom = Math.max(0.25, Math.min(4, state.zoom * (event.deltaY > 0 ? 0.9 : 1.1)));
    drawCloud();
  }, { passive: false });
}

for (const button of document.querySelectorAll('[data-tab]')) {
  button.addEventListener('click', () => switchTab(button.dataset.tab));
}
function applyScanPreset(name) {
  const presets = {
    validation: { yawStep: 10, yawLimit: 10, tiltStep: 50, dwell: 250, samples: 3, interval: 150 },
    coarse: { yawStep: 10, yawLimit: 60, tiltStep: 50, dwell: 250, samples: 3, interval: 150 },
    fine: { yawStep: 5, yawLimit: 60, tiltStep: 25, dwell: 400, samples: 5, interval: 250 },
  };
  const preset = presets[name];
  if (!preset) return;
  $('yaw-step').value = String(preset.yawStep);
  $('yaw-limit').value = String(preset.yawLimit);
  $('tilt-step').value = String(preset.tiltStep);
  $('dwell').value = String(preset.dwell);
  $('samples').value = String(preset.samples);
  $('sample-interval').value = String(preset.interval);
  $('servo-delay').value = '0.1';
  $('cooldown').value = '0.5';
}
$('preset-validation').addEventListener('click', () => applyScanPreset('validation'));
$('preset-coarse').addEventListener('click', () => applyScanPreset('coarse'));
$('preset-fine').addEventListener('click', () => applyScanPreset('fine'));
$('start-scan').addEventListener('click', startScan);
$('stop-scan').addEventListener('click', stopScan);
$('ml-start').addEventListener('click', startMl);
$('ml-stop').addEventListener('click', stopMl);
$('capture-cal').addEventListener('click', captureCalibration);
$('reload-points').addEventListener('click', () => loadPoints($('scan-select').value));
$('view-both').addEventListener('click', () => { state.viewMode = 'both'; drawCloud(); drawTopDown(); });
$('view-blocks').addEventListener('click', () => { state.viewMode = 'blocks'; drawCloud(); drawTopDown(); });
$('view-points').addEventListener('click', () => { state.viewMode = 'points'; drawCloud(); drawTopDown(); });
$('view-top').addEventListener('click', () => {
  state.viewYaw = 0;
  state.viewPitch = 1.15;
  state.zoom = 1.4;
  state.viewPanX = 0;
  state.viewPanY = 0;
  drawCloud();
});
$('toggle-distances').addEventListener('click', () => {
  state.showDistances = !state.showDistances;
  $('toggle-distances').classList.toggle('active', state.showDistances);
  drawCloud();
  drawTopDown();
});
$('toggle-prior').addEventListener('click', () => {
  state.priorVisible = !state.priorVisible;
  $('toggle-prior').classList.toggle('active', state.priorVisible);
  drawCloud();
  drawTopDown();
});
$('box-select').addEventListener('change', () => {
  state.selectedBoxId = $('box-select').value;
  syncBoxLabel();
  syncPriorFields();
});
$('apply-label').addEventListener('click', applyBoxLabel);
$('hide-box').addEventListener('click', hideSelectedBox);
$('merge-boxes').addEventListener('click', mergeSelectedBoxes);
$('reset-annotations').addEventListener('click', resetAnnotations);
$('undo-annotations').addEventListener('click', undoLast);
$('save-scene').addEventListener('click', saveScene);
$('add-prior').addEventListener('click', addPrior);
$('delete-prior').addEventListener('click', deletePrior);
$('convert-prior').addEventListener('click', convertToPrior);
$('apply-prior').addEventListener('click', applyPriorFields);
['prior-x', 'prior-y', 'prior-z0', 'prior-z1', 'prior-length',
  'prior-width', 'prior-angle'].forEach(id => {
  $(id).addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      const field = event.target;
      applyPriorFields().finally(() => {
        if (document.activeElement === field) field.blur();
      });
    }
  });
});
document.querySelectorAll('[data-prior-nudge]').forEach(button => {
  button.addEventListener('click', () => nudgePrior(button.dataset.priorNudge, button));
});
window.addEventListener('keydown', event => {
  if (!(event.ctrlKey || event.metaKey) || event.shiftKey
      || String(event.key).toLowerCase() !== 'z') return;
  const target = event.target;
  if (target && (target.matches?.('input, textarea, select') || target.isContentEditable)) {
    return;
  }
  event.preventDefault();
  undoLast();
});
$('prior-edit-mode').addEventListener('change', () => {
  state.priorEditMode = $('prior-edit-mode').checked;
  setText('prior-status', state.priorEditMode
    ? 'Mode geser aktif: drag box prior di 2D.'
    : 'Mode geser nonaktif: drag 2D untuk seleksi titik.');
});
$('show-axis').addEventListener('change', () => {
  state.showAxis = $('show-axis').checked;
  drawCloud();
  drawTopDown();
});
$('export-run').addEventListener('click', exportDataset);
$('presence-clear').addEventListener('click', clearPresence);
$('block-filter').addEventListener('input', renderBlockList);
document.querySelectorAll('[data-sidebar-tab]').forEach(button => {
  button.addEventListener('click', () => setSidebarTab(button.dataset.sidebarTab));
});
$('block-sidebar-toggle').addEventListener('click', () => setSidebarOpen(true));
$('block-sidebar-close').addEventListener('click', () => setSidebarOpen(false));
$('apply-point-label').addEventListener('click', applyPointLabel);
$('clear-selection').addEventListener('click', clearSelection);
$('create-box').addEventListener('click', createBoxFromSelection);
$('select-depth-min').addEventListener('input', () => {
  state.selectDepthMin = Number($('select-depth-min').value) || -5;
});
$('select-depth-max').addEventListener('input', () => {
  state.selectDepthMax = Number($('select-depth-max').value) || 5;
});
$('select-through').addEventListener('change', () => {
  state.selectThrough = $('select-through').checked;
});
$('scan-select').addEventListener('change', () => loadPoints($('scan-select').value));
$('rotate-left').addEventListener('click', () => { state.viewYaw -= 0.2; drawCloud(); });
$('rotate-right').addEventListener('click', () => { state.viewYaw += 0.2; drawCloud(); });
$('pitch-up').addEventListener('click', () => { state.viewPitch = Math.min(1.2, state.viewPitch + 0.15); drawCloud(); });
$('pitch-down').addEventListener('click', () => { state.viewPitch = Math.max(-1.2, state.viewPitch - 0.15); drawCloud(); });
$('zoom-in').addEventListener('click', () => { state.zoom = Math.min(4, state.zoom * 1.2); drawCloud(); });
$('zoom-out').addEventListener('click', () => { state.zoom = Math.max(0.25, state.zoom / 1.2); drawCloud(); });
$('reset-view').addEventListener('click', () => {
  state.viewYaw = -0.65;
  state.viewPitch = 0.55;
  state.zoom = 1.4;
  state.viewPanX = 0;
  state.viewPanY = 0;
  drawCloud();
});
$('apply-yaw-scale').addEventListener('click', applyYawScale);
$('reset-yaw-scale').addEventListener('click', resetYawScale);
$('top-zoom-in').addEventListener('click', () => {
  state.topZoom = Math.min(8, (Number(state.topZoom) || 1) * 1.2);
  drawTopDown();
});
$('top-zoom-out').addEventListener('click', () => {
  state.topZoom = Math.max(0.4, (Number(state.topZoom) || 1) / 1.2);
  drawTopDown();
});
$('top-reset').addEventListener('click', () => {
  state.topZoom = 1.0;
  state.topPanX = 0;
  state.topPanY = 0;
  drawTopDown();
});

function bindTopDown() {
  const canvas = $('topdown');
  if (!canvas) return;
  let mode = null;
  let lastX = 0;
  let lastY = 0;
  let dragBox = null;
  let dragStart = null;
  let dragOrigin = null;
  let resizeState = null;
  let transform = null;
  const round3 = value => Math.round(Number(value) * 1000) / 1000;
  const cursorForHandle = handle => {
    if (!handle) return state.priorEditMode ? 'move' : 'crosshair';
    return handle.kind === 'corner' ? 'nwse-resize' : 'move';
  };
  canvas.addEventListener('contextmenu', event => event.preventDefault());
  canvas.addEventListener('pointerdown', async (event) => {
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    const point = canvasPoint(event, canvas);
    transform = topDownTransform(canvas);
    if (event.button === 2) {
      mode = 'pan';
      lastX = event.clientX; lastY = event.clientY;
    } else if (event.button === 0) {
      const box = selectedBox();
      if (box) {
        const handle = handleAtPoint(box, point, transform.toScreen);
        if (handle) {
          if (!isEditableBox(box)) {
            mode = 'promoting';
            try {
              const promoted = await promoteBoxToPrior(box);
              if (!promoted) {
                mode = null;
                return;
              }
              transform = topDownTransform(canvas);
              dragBox = promoted;
              resizeState = {
                su: handle.su,
                sv: handle.sv,
                cx: Number(promoted.cx_m),
                cy: Number(promoted.cy_m),
                angle: Number(promoted.angle_deg || 0) * Math.PI / 180,
                length: Number(promoted.length_m),
                width: Number(promoted.width_m),
              };
              mode = 'resize-prior';
            } catch (error) {
              mode = null;
              setText('prior-status', `Gagal menjadikan prior: ${error.message}`);
              showToast(`Gagal menjadikan prior: ${error.message}`, 'error', 4500);
            }
            canvas.style.cursor = cursorForHandle(handle);
            return;
          }
          mode = 'resize-prior';
          dragBox = box;
          resizeState = {
            su: handle.su,
            sv: handle.sv,
            cx: Number(box.cx_m),
            cy: Number(box.cy_m),
            angle: Number(box.angle_deg || 0) * Math.PI / 180,
            length: Number(box.length_m),
            width: Number(box.width_m),
          };
          canvas.style.cursor = cursorForHandle(handle);
          return;
        }
      }
      if (state.priorEditMode && box && isEditableBox(box)) {
        const world = transform.toWorld(point.x, point.y);
        if (pointInBoxFootprint(box, world.x, world.y)) {
          mode = 'move-prior';
          dragBox = box;
          dragStart = world;
          dragOrigin = { cx: Number(box.cx_m), cy: Number(box.cy_m) };
          return;
        }
      }
      mode = 'select';
      state.selectionRect = { canvas: 'topdown', x0: point.x, y0: point.y, x1: point.x, y1: point.y };
    }
  });
  canvas.addEventListener('pointermove', (event) => {
    const point = canvasPoint(event, canvas);
    if (!mode) {
      const box = selectedBox();
      const handle = box
        ? handleAtPoint(box, point, topDownTransform(canvas).toScreen) : null;
      canvas.style.cursor = cursorForHandle(handle);
      return;
    }
    if (mode === 'pan') {
      state.topPanX += event.clientX - lastX;
      state.topPanY += event.clientY - lastY;
      lastX = event.clientX; lastY = event.clientY;
      drawTopDown();
    } else if (mode === 'resize-prior' && dragBox && resizeState && transform) {
      const world = transform.toWorld(point.x, point.y);
      const rs = resizeState;
      const ca = Math.cos(rs.angle), sa = Math.sin(rs.angle);
      const du = (world.x - rs.cx) * ca + (world.y - rs.cy) * sa;
      const dv = -(world.x - rs.cx) * sa + (world.y - rs.cy) * ca;
      const minSize = 0.05;
      let u0 = -rs.length / 2, u1 = rs.length / 2;
      let v0 = -rs.width / 2, v1 = rs.width / 2;
      if (rs.su > 0) u1 = Math.max(u0 + minSize, du);
      else if (rs.su < 0) u0 = Math.min(u1 - minSize, du);
      if (rs.sv > 0) v1 = Math.max(v0 + minSize, dv);
      else if (rs.sv < 0) v0 = Math.min(v1 - minSize, dv);
      const uc = (u0 + u1) / 2;
      const vc = (v0 + v1) / 2;
      dragBox.length_m = round3(Math.max(minSize, u1 - u0));
      dragBox.width_m = round3(Math.max(minSize, v1 - v0));
      dragBox.cx_m = round3(rs.cx + uc * ca - vc * sa);
      dragBox.cy_m = round3(rs.cy + uc * sa + vc * ca);
      updatePriorFieldValues(dragBox);
      drawTopDown();
    } else if (mode === 'move-prior' && dragBox && transform) {
      const world = transform.toWorld(point.x, point.y);
      dragBox.cx_m = round3(dragOrigin.cx + (world.x - dragStart.x));
      dragBox.cy_m = round3(dragOrigin.cy + (world.y - dragStart.y));
      updatePriorFieldValues(dragBox);
      drawTopDown();
    } else if (mode === 'select' && state.selectionRect) {
      state.selectionRect.x1 = point.x;
      state.selectionRect.y1 = point.y;
      drawTopDown();
    }
  });
  canvas.addEventListener('pointerup', (event) => {
    if (mode === 'resize-prior' && dragBox) {
      const next = annotationsClone();
      const manual = (next.manual_boxes || [])
        .find(item => String(item.id) === String(dragBox.id));
      if (manual) {
        manual.cx_m = dragBox.cx_m;
        manual.cy_m = dragBox.cy_m;
        manual.length_m = dragBox.length_m;
        manual.width_m = dragBox.width_m;
      }
      const boxId = dragBox.id;
      dragBox = null;
      resizeState = null;
      saveAnnotations(next, 'Ukuran prior diubah; sisi lawan tetap.', boxId).catch(error => {
        setText('prior-status', `Gagal menyimpan resize: ${error.message}`);
        showToast(`Gagal menyimpan resize: ${error.message}`, 'error', 4500);
      });
    } else if (mode === 'move-prior' && dragBox) {
      const next = annotationsClone();
      const manual = (next.manual_boxes || [])
        .find(item => String(item.id) === String(dragBox.id));
      if (manual) {
        manual.cx_m = dragBox.cx_m;
        manual.cy_m = dragBox.cy_m;
      }
      const boxId = dragBox.id;
      dragBox = null;
      dragStart = null;
      dragOrigin = null;
      saveAnnotations(next, 'Prior digeser dengan drag.', boxId).catch(error => {
        setText('prior-status', `Gagal menyimpan drag: ${error.message}`);
      });
    } else if (mode === 'select' && state.selectionRect) {
      const rect = state.selectionRect;
      const width = Math.abs(rect.x1 - rect.x0);
      const height = Math.abs(rect.y1 - rect.y0);
      if (width < 4 && height < 4) {
        selectBoxAt('topdown', { x: rect.x1, y: rect.y1 });
      } else {
        selectPointsInRect('topdown', rect,
          event.shiftKey ? 'add' : (event.altKey ? 'subtract' : 'replace'));
      }
    }
    mode = null;
    state.selectionRect = null;
    canvas.style.cursor = state.priorEditMode ? 'move' : 'crosshair';
    drawTopDown();
  });
  canvas.addEventListener('pointercancel', () => {
    mode = null;
    dragBox = null;
    dragStart = null;
    dragOrigin = null;
    resizeState = null;
    state.selectionRect = null;
    drawTopDown();
  });
  canvas.addEventListener('wheel', (event) => {
    event.preventDefault();
    const factor = event.deltaY > 0 ? 0.9 : 1.1;
    state.topZoom = Math.max(0.4, Math.min(8, (Number(state.topZoom) || 1) * factor));
    drawTopDown();
  }, { passive: false });
}

bindCanvas();
bindTopDown();
try {
  setSidebarOpen(localStorage.getItem('mapping.sidebarOpen') === '1');
} catch (error) {
  setSidebarOpen(false);
}
renderLabelSuggestions();
updateSelectionStatus();
updateUndoButton();

(async () => {
  await refreshScans();
  await refreshHealth();
  await refreshScanStatus();
  await refreshCalibration();
  await refreshMlStatus();
  await refreshPresence();
  await refreshDatasetIndex();
  const latest = (state.scans || []).find(scan => !scan.error && (scan.points || 0) > 0) || (state.scans || [])[0];
  if (latest) {
    $('scan-select').value = latest.scan_id;
    await loadPoints(latest.scan_id);
  }
  setInterval(refreshScans, 3000);
  setInterval(refreshHealth, 2000);
  setInterval(refreshPresence, 1500);
  setInterval(refreshScanStatus, 1000);
  setInterval(refreshMlStatus, 1000);
})();

