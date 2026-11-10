'use strict';

const $ = (id) => document.getElementById(id);
const state = {
  health: null,
  scans: [],
  calibration: null,
  points: [],
  scanJob: null,
  loadedScan: null,
  reconstruction: null,
  annotations: null,
  selectedBoxId: null,
  presence: null,
  presenceError: null,
  presenceBusy: false,
  mlMetrics: null,
  showDistances: true,
  viewMode: 'both',
  viewYaw: -0.65,
  viewPitch: 0.48,
  zoom: 1.0,
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
  setText('health', `Overall ${health.overall || '—'} · ToF errors ${stats.tof_i2c_errors ?? '—'} · ${stats.tof_error_rate_per_min ?? '—'}/min · responsive ${tof.responsive ? 'yes' : 'no'}`);
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
      : `state ${presence.state} · ${presence.reason} · konfirmasi ${presence.confirm_frames}/${presence.confirm_required} frame · hold ${presence.hold_s}s`);
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

async function loadPoints(scanId) {
  if (!scanId) return;
  try {
    const data = await api(`/api/mapping/scans/${encodeURIComponent(scanId)}/points`);
    state.points = data.points || [];
    state.loadedScan = scanId;
    $('scan-select').value = scanId;
    let reconstruction = null;
    let annotations = { labels: {}, hidden: [], merges: [] };
    try {
      const rec = await api(`/api/mapping/scans/${encodeURIComponent(scanId)}/reconstruct`);
      reconstruction = rec.reconstruction;
      annotations = rec.annotations || annotations;
    } catch (error) {
      reconstruction = null;
    }
    state.reconstruction = reconstruction;
    state.annotations = annotations;
    state.selectedBoxId = null;
    const blocks = reconstruction?.boxes?.length ?? 0;
    setText('cloud-stats', `${scanId} · ${state.points.length} points · ${state.points.filter(p => p.range_mm != null).length} with range · ${blocks} estimated blocks · mount ${reconstruction?.mount_points ?? '—'} hidden`);
    renderBoxControls();
    drawCloud();
    drawTopDown();
  } catch (error) {
    setText('cloud-stats', `Gagal memuat point cloud: ${error.message}`);
  }
}

function boxColor(box) {
  const palette = {
    wall: [80, 150, 230],
    wall_edge: [130, 200, 255],
    fan: [255, 190, 80],
    bed: [170, 140, 255],
    wardrobe: [205, 130, 255],
    chair: [255, 150, 120],
    table: [255, 170, 90],
    mount: [150, 150, 150],
    object: [70, 210, 150],
  };
  return palette[box.label] || palette.object;
}

function boxName(box) {
  return `${box.label}${box.label_source === 'manual' ? '*' : ''}`;
}

function boxDistance(box) {
  const value = (box.label === 'wall' || box.label === 'wall_edge')
    ? box.nearest_m : box.distance_m;
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
    merges: source.merges || [],
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
  const annotations = state.annotations || {};
  const count = Object.keys(annotations.labels || {}).length
    + (annotations.hidden || []).length + (annotations.merges || []).length;
  setText('annotation-status', count ? `${count} anotasi manual aktif.` : 'Belum ada anotasi manual.');
  renderBlockList();
}

function renderBlockList() {
  const container = $('block-list');
  if (!container) return;
  container.replaceChildren();
  const boxes = currentBoxes();
  if (!boxes.length) {
    container.textContent = 'Tidak ada blok untuk ditampilkan.';
    return;
  }
  const table = document.createElement('table');
  const head = document.createElement('tr');
  for (const label of ['#', 'Warna', 'Label', 'Jarak', 'Ukuran', 'Tinggi', 'Titik', 'Sumber']) {
    const th = document.createElement('th');
    th.textContent = label;
    head.append(th);
  }
  table.append(head);
  boxes.forEach((box, index) => {
    const row = document.createElement('tr');
    const number = document.createElement('td');
    number.textContent = index + 1;
    row.append(number);
    const swatchCell = document.createElement('td');
    const swatch = document.createElement('span');
    swatch.className = 'swatch';
    const color = boxColor(box);
    swatch.style.background = `rgb(${color[0]},${color[1]},${color[2]})`;
    swatchCell.append(swatch);
    row.append(swatchCell);
    for (const value of [
      boxName(box),
      formatMeters(boxDistance(box)),
      `${Number(box.length_m).toFixed(2)}×${Number(box.width_m).toFixed(2)} m`,
      `${Number(box.z_top_m).toFixed(2)} m`,
      box.points,
      box.label_source === 'manual' ? 'manual' : 'auto',
    ]) {
      const cell = document.createElement('td');
      cell.textContent = value ?? '—';
      row.append(cell);
    }
    table.append(row);
  });
  container.append(table);
}

function syncBoxLabel() {
  const box = currentBoxes().find(item => item.id === $('box-select').value);
  if (box) $('box-label').value = box.label;
}

async function saveAnnotations(annotations, message) {
  if (!state.loadedScan) return;
  const data = await api(`/api/mapping/scans/${encodeURIComponent(state.loadedScan)}/annotations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ annotations }),
  });
  state.annotations = data.annotations || annotations;
  state.reconstruction = data.reconstruction;
  state.selectedBoxId = null;
  renderBoxControls();
  drawCloud();
  drawTopDown();
  const blocks = data.reconstruction?.boxes?.length ?? 0;
  setText('cloud-stats', `${state.loadedScan} · ${state.points.length} points · ${blocks} estimated blocks · mount ${data.reconstruction?.mount_points ?? '—'} hidden`);
  setText('annotation-status', message || 'Anotasi disimpan.');
}

async function applyBoxLabel() {
  const box = currentBoxes().find(item => item.id === $('box-select').value);
  if (!box) return;
  const next = annotationsClone();
  next.labels[box.id] = $('box-label').value;
  try {
    await saveAnnotations(next, `Label ${box.label} → ${$('box-label').value}.`);
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
    await saveAnnotations(next, `Blok ${box.label} disembunyikan.`);
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
    await saveAnnotations(next, 'Dua blok digabung menjadi satu bounding box.');
  } catch (error) {
    setText('annotation-status', `Gagal menggabung blok: ${error.message}`);
  }
}

async function resetAnnotations() {
  try {
    await saveAnnotations({ labels: {}, hidden: [], merges: [] }, 'Anotasi direset.');
  } catch (error) {
    setText('annotation-status', `Gagal reset anotasi: ${error.message}`);
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
  const y2 = y1 * sp - z * cp;
  const depth = y1 * cp + z * sp;
  const scale = Math.min(width, height) * 0.72 * state.zoom / (2 * radius + 0.6);
  return { x: width / 2 + x1 * scale, y: height / 2 + y2 * scale, depth };
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

function drawBoxes3D(ctx, width, height, radius) {
  const boxes = state.reconstruction?.boxes || [];
  const faces = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]];
  for (const [boxIndex, box] of boxes.entries()) {
    const projected = boxCorners(box).map(point => projectPoint(point, width, height, radius));
    const color = boxColor(box);
    const ordered = faces.map(indices => ({
      indices,
      depth: indices.reduce((sum, index) => sum + projected[index].depth, 0) / indices.length,
    })).sort((a, b) => a.depth - b.depth);
    for (const face of ordered) {
      const [a, b, c, d] = face.indices.map(index => projected[index]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.lineTo(c.x, c.y); ctx.lineTo(d.x, d.y); ctx.closePath();
      ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.18)`;
      ctx.fill();
      ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},0.9)`;
      ctx.lineWidth = box.label === 'wall' ? 1.6 : 1.2;
      if (box.label === 'wall_edge') ctx.setLineDash([5, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    const top = projectPoint({
      x_mm: Number(box.cx_m) * 1000, y_mm: Number(box.cy_m) * 1000,
      z_mm: (Number(box.z_top_m) + 0.08) * 1000,
    }, width, height, radius);
    const distance = state.showDistances ? ` · ${formatMeters(boxDistance(box))}` : '';
    const dimensions = `${Number(box.length_m).toFixed(1)}×${Number(box.width_m).toFixed(1)} m`;
    if (state.selectedBoxId === box.id) {
      const text = `${boxName(box)} ${dimensions}${distance}`;
      ctx.font = '12px system-ui';
      ctx.lineWidth = 3;
      ctx.strokeStyle = 'rgba(10,17,28,0.85)';
      ctx.strokeText(text, top.x + 12, top.y - 4);
      ctx.fillStyle = `rgb(${color[0]},${color[1]},${color[2]})`;
      ctx.fillText(text, top.x + 12, top.y - 4);
    } else {
      ctx.beginPath();
      ctx.arc(top.x, top.y, 9, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.92)`;
      ctx.fill();
      ctx.fillStyle = '#0a111c';
      ctx.font = 'bold 10px system-ui';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(boxIndex + 1), top.x, top.y);
      ctx.textAlign = 'start';
      ctx.textBaseline = 'alphabetic';
    }
  }
}

function drawTag(ctx, x, y, text, color) {
  ctx.font = '11px system-ui';
  const width = ctx.measureText(text).width + 8;
  ctx.fillStyle = 'rgba(10,17,28,0.80)';
  ctx.fillRect(x - width / 2, y - 9, width, 17);
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

function drawHumanTopDown(ctx, toScreen, origin, scale) {
  const presence = state.presence;
  if (!presence || !['present', 'holding'].includes(presence.state)) return;
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
    `rgb(${color[0]},${color[1]},${color[2]})`);
}

function drawTopDown() {
  const canvas = $('topdown');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const width = canvas.width, height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  const points = state.points.filter(p => p.x_mm != null && p.y_mm != null);
  const boxes = currentBoxes();
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
  const scale = Math.min(width, height) * 0.42 / extent;
  const toScreen = (x, y) => ({ x: width / 2 + x * scale, y: height / 2 - y * scale });
  ctx.lineWidth = 1;
  const start = -Math.ceil(extent * 2) / 2;
  for (let value = start; value <= extent; value += 0.5) {
    const p1 = toScreen(value, -extent), p2 = toScreen(value, extent);
    const p3 = toScreen(-extent, value), p4 = toScreen(extent, value);
    ctx.strokeStyle = Math.abs(value) < 0.01 ? '#2c4562' : '#1a2a3d';
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(p3.x, p3.y); ctx.lineTo(p4.x, p4.y); ctx.stroke();
  }
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
  if (state.showDistances) {
    for (const [boxIndex, box] of boxes.entries()) {
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
        `rgb(${color[0]},${color[1]},${color[2]})`);
    }
  }
  if (state.viewMode !== 'blocks') {
    for (const point of points) {
      const screen = toScreen(Number(point.x_mm) / 1000, Number(point.y_mm) / 1000);
      ctx.fillStyle = point.range_source === 'tof' ? 'rgba(80,220,255,0.85)' : 'rgba(255,170,60,0.85)';
      ctx.beginPath(); ctx.arc(screen.x, screen.y, 2.2, 0, Math.PI * 2); ctx.fill();
    }
  }
  if (state.viewMode !== 'points') {
    for (const [boxIndex, box] of boxes.entries()) {
      const corners = boxCorners(box).slice(0, 4).map(point => toScreen(Number(point.x_mm) / 1000, Number(point.y_mm) / 1000));
      const color = boxColor(box);
      ctx.beginPath(); ctx.moveTo(corners[0].x, corners[0].y);
      for (const corner of corners.slice(1)) ctx.lineTo(corner.x, corner.y);
      ctx.closePath();
      ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.22)`;
      ctx.fill();
      ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},0.95)`;
      ctx.lineWidth = box.label === 'wall' ? 2.2 : 1.6;
      if (box.label === 'wall_edge') ctx.setLineDash([5, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
      const label = toScreen(Number(box.cx_m), Number(box.cy_m));
      if (box.label === 'wall' || box.label === 'wall_edge') {
        ctx.beginPath();
        ctx.arc(label.x, label.y, 9, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.92)`;
        ctx.fill();
        ctx.fillStyle = '#0a111c';
        ctx.font = 'bold 10px system-ui';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(boxIndex + 1), label.x, label.y);
        ctx.textAlign = 'start';
        ctx.textBaseline = 'alphabetic';
      } else {
        const text = `#${boxIndex + 1} ${boxName(box)}`;
        ctx.font = '12px system-ui';
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgba(10,17,28,0.85)';
        ctx.strokeText(text, label.x + 4, label.y - 4);
        ctx.fillStyle = `rgb(${color[0]},${color[1]},${color[2]})`;
        ctx.fillText(text, label.x + 4, label.y - 4);
      }
    }
  }
  drawHumanTopDown(ctx, toScreen, origin, scale);
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
    const yaw = Number(state.health?.esp?.scan?.yaw_deg_nominal || 0) * Math.PI / 180;
    const screen = toScreen(hlkRadius * Math.cos(yaw), hlkRadius * Math.sin(yaw));
    ctx.fillStyle = 'rgba(255,80,200,0.28)';
    ctx.strokeStyle = 'rgba(255,120,220,0.85)';
    ctx.beginPath(); ctx.arc(screen.x, screen.y, 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = '#ff9be0'; ctx.font = '11px system-ui';
    ctx.fillText(`HLK ${hlkRadius.toFixed(2)} m`, screen.x + 6, screen.y - 6);
  }
}

function drawHuman3D(ctx, width, height, radius) {
  const presence = state.presence;
  if (!presence || !['present', 'holding'].includes(presence.state)) return;
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
  ctx.font = '12px system-ui';
  ctx.lineWidth = 3;
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
  const points = state.points.filter(p => p.x_mm != null && p.y_mm != null && p.z_mm != null);
  const boxes = currentBoxes();
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
  if (state.viewMode !== 'blocks') {
    const projected = points.map(point => ({
      point,
      screen: projectPoint(point, width, height, maxRadius),
    })).sort((a, b) => a.screen.depth - b.screen.depth);
    for (const item of projected) {
      const source = item.point.range_source;
      const base = source === 'tof' ? [80, 220, 255] : [255, 170, 60];
      const z = Number(item.point.z_mm) || 0;
      const alpha = Math.max(0.35, Math.min(1, 0.55 + z / (maxRadius * 2000)));
      ctx.fillStyle = `rgba(${base[0]},${base[1]},${base[2]},${alpha})`;
      ctx.beginPath();
      ctx.arc(item.screen.x, item.screen.y, source === 'tof' ? 2.6 : 2.2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  if (state.viewMode !== 'points') drawBoxes3D(ctx, width, height, maxRadius);
  drawHuman3D(ctx, width, height, maxRadius);
  if (hlkRadius > 0 && !(presence && ['present', 'holding'].includes(presence.state))) {
    const yawDeg = Number(state.health?.esp?.scan?.yaw_deg_nominal || 0);
    const yaw = yawDeg * Math.PI / 180;
    const marker = projectPoint({
      x_mm: hlkRadius * 1000 * Math.cos(yaw),
      y_mm: hlkRadius * 1000 * Math.sin(yaw),
      z_mm: 0,
    }, width, height, maxRadius);
    const markerRadius = 8 + Math.min(18, Number(hlk?.energy || 0) / 6);
    ctx.fillStyle = 'rgba(255,80,200,0.22)';
    ctx.strokeStyle = 'rgba(255,120,220,0.95)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(marker.x, marker.y, markerRadius, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = '#ffb8e8';
    ctx.font = '12px system-ui';
    ctx.fillText(`HLK ${hlk?.distance_cm ?? '—'} cm`, marker.x + markerRadius + 4, marker.y - 4);
  }
  if (!points.length && !boxes.length) {
    ctx.fillStyle = '#9fb1c7';
    ctx.font = '16px system-ui';
    ctx.fillText('Belum ada point cloud. Jalankan scan atau pilih scan.', 24, 36);
  }
}

function bindCanvas() {
  const canvas = $('cloud');
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  canvas.addEventListener('pointerdown', (event) => {
    dragging = true; lastX = event.clientX; lastY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!dragging) return;
    state.viewYaw += (event.clientX - lastX) * 0.01;
    state.viewPitch = Math.max(-1.2, Math.min(1.2, state.viewPitch + (event.clientY - lastY) * 0.008));
    lastX = event.clientX; lastY = event.clientY;
    drawCloud();
  });
  canvas.addEventListener('pointerup', () => { dragging = false; });
  canvas.addEventListener('pointercancel', () => { dragging = false; });
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
$('toggle-distances').addEventListener('click', () => {
  state.showDistances = !state.showDistances;
  $('toggle-distances').classList.toggle('active', state.showDistances);
  drawCloud();
  drawTopDown();
});
$('box-select').addEventListener('change', () => {
  state.selectedBoxId = $('box-select').value;
  syncBoxLabel();
});
$('apply-label').addEventListener('click', applyBoxLabel);
$('hide-box').addEventListener('click', hideSelectedBox);
$('merge-boxes').addEventListener('click', mergeSelectedBoxes);
$('reset-annotations').addEventListener('click', resetAnnotations);
$('scan-select').addEventListener('change', () => loadPoints($('scan-select').value));
$('rotate-left').addEventListener('click', () => { state.viewYaw -= 0.2; drawCloud(); });
$('rotate-right').addEventListener('click', () => { state.viewYaw += 0.2; drawCloud(); });
$('pitch-up').addEventListener('click', () => { state.viewPitch = Math.min(1.2, state.viewPitch + 0.15); drawCloud(); });
$('pitch-down').addEventListener('click', () => { state.viewPitch = Math.max(-1.2, state.viewPitch - 0.15); drawCloud(); });
$('zoom-in').addEventListener('click', () => { state.zoom = Math.min(4, state.zoom * 1.2); drawCloud(); });
$('zoom-out').addEventListener('click', () => { state.zoom = Math.max(0.25, state.zoom / 1.2); drawCloud(); });
$('reset-view').addEventListener('click', () => {
  state.viewYaw = -0.65; state.viewPitch = 0.48; state.zoom = 1.0; drawCloud();
});
bindCanvas();

(async () => {
  await refreshScans();
  await refreshHealth();
  await refreshScanStatus();
  await refreshCalibration();
  await refreshMlStatus();
  await refreshPresence();
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
