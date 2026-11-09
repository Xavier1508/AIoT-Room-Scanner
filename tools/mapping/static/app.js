'use strict';

const $ = (id) => document.getElementById(id);
const state = {
  health: null,
  scans: [],
  calibration: null,
  points: [],
  scanJob: null,
  loadedScan: null,
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
  if (name === 'cloud') drawCloud();
}

async function refreshHealth() {
  try {
    const data = await api('/api/mapping/health');
    state.health = data;
    state.scans = data.scans || [];
    state.calibration = data.calibration || {};
    renderHealth();
    renderScans();
    renderCalibration();
  } catch (error) {
    setText('summary', `ESP32 belum terhubung: ${error.message}`);
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
  if (document.getElementById('tab-cloud').classList.contains('active')) drawCloud();
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
  for (const label of ['Scan', 'Points', 'Valid', 'ToF', 'HC', 'Status']) {
    const th = document.createElement('th');
    th.textContent = label;
    head.append(th);
  }
  table.append(head);
  for (const scan of scans.slice(0, 20)) {
    const row = document.createElement('tr');
    for (const value of [scan.scan_id, scan.points, scan.valid_points, scan.tof_points,
                         scan.hc_points, scan.error ? 'ERROR' : 'OK']) {
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
  const latest = scans[0];
  setText('last-scan', `${latest.scan_id} · ${latest.points} points · ${latest.valid_points} valid · ${latest.tof_points} ToF · ${latest.hc_points} HC`);
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
      tilt_step_us: Number($('tilt-step').value),
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
    setText('cloud-stats', `${scanId} · ${state.points.length} points · ${state.points.filter(p => p.range_mm != null).length} with range`);
    drawCloud();
  } catch (error) {
    setText('cloud-stats', `Gagal memuat point cloud: ${error.message}`);
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

function drawCloud() {
  const canvas = $('cloud');
  const ctx = canvas.getContext('2d');
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  const points = state.points.filter(p => p.x_mm != null && p.y_mm != null && p.z_mm != null);
  const hlk = state.health?.esp?.sensors?.hlk;
  const hlkRadius = hlk?.valid ? Number(hlk.distance_cm || 0) / 100 : 0;
  const maxRadius = Math.max(1.0, hlkRadius, ...points.map(p => Math.max(
    Math.abs(Number(p.x_mm)), Math.abs(Number(p.y_mm)), Math.abs(Number(p.z_mm))) / 1000));
  drawGrid(ctx, width, height, maxRadius);
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
  if (hlkRadius > 0) {
    const yawDeg = Number(state.health?.esp?.scan?.yaw_deg_nominal || 0);
    const yaw = yawDeg * Math.PI / 180;
    const marker = projectPoint({
      x_mm: hlkRadius * 1000 * Math.cos(yaw),
      y_mm: hlkRadius * 1000 * Math.sin(yaw),
      z_mm: 0,
    }, width, height, maxRadius);
    const markerRadius = 8 + Math.min(18, Number(hlk.energy || 0) / 6);
    ctx.fillStyle = 'rgba(255,80,200,0.22)';
    ctx.strokeStyle = 'rgba(255,120,220,0.95)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(marker.x, marker.y, markerRadius, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = '#ffb8e8';
    ctx.font = '12px system-ui';
    ctx.fillText(`HLK ${hlk.distance_cm} cm`, marker.x + markerRadius + 4, marker.y - 4);
  }
  if (!points.length) {
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
$('start-scan').addEventListener('click', startScan);
$('stop-scan').addEventListener('click', stopScan);
$('capture-cal').addEventListener('click', captureCalibration);
$('reload-points').addEventListener('click', () => loadPoints($('scan-select').value));
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
  await refreshHealth();
  await refreshScanStatus();
  await refreshCalibration();
  const latest = (state.scans || [])[0];
  if (latest) {
    $('scan-select').value = latest.scan_id;
    await loadPoints(latest.scan_id);
  }
  setInterval(refreshHealth, 2000);
  setInterval(refreshScanStatus, 1000);
})();
