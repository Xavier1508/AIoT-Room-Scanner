#pragma once

#include <Arduino.h>

static const char webPage[] PROGMEM = R"HTML(<!doctype html>
<html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIoT ESP32-S3 · Control &amp; Mapping</title>
<style>
:root{color-scheme:dark;font:16px system-ui;background:#0d1420;color:#e6edf6}*{box-sizing:border-box}body{max-width:1100px;margin:auto;padding:18px}h1{font-size:1.55rem;margin:0 0 4px}h2{font-size:1.05rem;margin:0 0 10px}h3{font-size:.95rem;margin:14px 0 6px}.muted{color:#9fb1c7}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}.card{background:#172335;padding:16px;border:1px solid #2d425c;border-radius:12px;margin:12px 0}button{font:inherit;background:#285f94;color:white;border:0;border-radius:7px;padding:9px 12px;margin:4px;cursor:pointer}button:hover{filter:brightness(1.12)}button:disabled{opacity:.35;cursor:not-allowed}button.alt{background:#35516f}button.warnbtn{background:#8a5a1f}button.danger{background:#bc3434}.stop{background:#bc3434;font-weight:800;font-size:1.05rem;width:100%;margin:8px 0;position:sticky;top:0;z-index:5}.warn{border-left:4px solid #e0b151;padding-left:12px;color:#edcf91}.ok{color:#80d8a5}.bad{color:#ff8b8b}.mid{color:#f0c674}pre{white-space:pre-wrap;word-break:break-word;font-size:12px;max-height:300px;overflow:auto;background:#0d1420;padding:10px;border-radius:8px}input{max-width:100%;margin:6px 0;padding:8px;border-radius:6px;border:1px solid #36506d;background:#0d1420;color:#e6edf6}progress{width:100%;height:14px}.tabs{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0}.tabs button{background:#1b2a3e;border:1px solid #36506d}.tabs button.active{background:#285f94}.tab{display:none}.tab.active{display:block}.sensor{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:end}.big{font-size:1.9rem;font-weight:750;line-height:1.1}.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.75rem;font-weight:700;background:#26384e}.badge.OK{background:#1d5b3c;color:#9cf0c1}.badge.DEGRADED,.badge.STALE{background:#6a4a17;color:#ffe0a3}.badge.FAULT,.badge.ABSENT,.badge.INIT_FAILED,.badge.NO_DATA{background:#6d2525;color:#ffb4b4}.badge.OFF{background:#3a4657;color:#c5d0dd}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.small{font-size:.82rem}a{color:#95caff}.note{font-size:.85rem;color:#9fb1c7}.pill{background:#0d1420;border:1px solid #2d425c;border-radius:8px;padding:6px 9px;font-size:.85rem}
</style>
<h1>AIoT ESP32-S3 <span class="muted">/ control &amp; mapping</span></h1>
<p id="summary" class="muted">Menghubungkan…</p>
<button class="stop" id="stop">STOP · matikan keluaran, sensor, scan &amp; disarm</button>
<p class="warn">Software stop bukan pemutus daya fisik. Hold servo/stepper dapat panas; release/STOP dapat menjatuhkan arm. Uji tanpa beban, dukung mekanik, dan siapkan pemutus daya fisik.</p>

<div class="tabs">
<button data-tab="manual" class="active">Manual</button>
<button data-tab="sensors">Sensors</button>
<button data-tab="calibration">Calibration</button>
<button data-tab="scan">Scan</button>
<button data-tab="mapping">Mapping</button>
<button data-tab="ota">OTA</button>
<button data-tab="diagnostics">Diagnostics</button>
</div>

<section id="tab-manual" class="tab active">
<div class="grid">
<section class="card"><h2>Sensor suite</h2>
<button data-command="sensors_start">Nyalakan semua sensor</button><button data-command="sensors_stop">Hentikan semua sensor</button>
<button data-command="hlk_alert_on">HLK alert ON</button><button data-command="hlk_alert_off">HLK alert OFF</button>
<p class="note">HC-SR04 TRIG10/ECHO11 dengan divider; VL53L1X I2C8/9. Pembacaan tidak menggerakkan axis.</p>
<div class="sensor"><div><div class="muted">HC-SR04</div><div id="hc-value" class="big">—</div></div><span id="hc-health" class="badge">—</span></div>
<div class="sensor"><div><div class="muted">VL53L1X</div><div id="tof-value" class="big">—</div></div><span id="tof-health" class="badge">—</span></div>
<div class="sensor"><div><div class="muted">HLK-LD2410C</div><div id="hlk-value" class="big">—</div></div><span id="hlk-health" class="badge">—</span></div>
<p id="health-line" class="note">—</p>
</section>
<section class="card"><h2>Buzzer &amp; radar</h2>
<button data-command="buzzer_test">3 beep test</button><button data-command="hlk_start">Mulai HLK</button><button data-command="hlk_stop">Hentikan HLK</button>
<p class="note">HLK dipakai presence/proximity; blind zone &lt;30 cm. Buzzer parkir: diam di &gt;75 cm, lambat di 75 cm, makin cepat sampai 30 cm. Mute saat scan mode/gerakan; aktif setelah arm diam &gt;1 detik. Konfirmasi 3 frame + energy threshold.</p>
<pre id="hlk">Belum ada data valid.</pre></section>
<section class="card"><h2>Axis X · Stepper horizontal</h2>
<button data-command="motor_arm">Arm motor · 30 dtk</button><button data-command="step_test">64 maju / 64 mundur</button><button data-command="step_test_long">512 maju / 512 mundur</button>
<button data-command="park_stepper">Hold posisi sekarang</button><button data-command="stepper_left_10">Kiri 10°</button><button data-command="stepper_right_10">Kanan 10°</button><button data-command="stepper_left_5">Kiri 5°</button><button data-command="stepper_right_5">Kanan 5°</button><button data-command="release_stepper">Release stepper</button><button data-command="zero_stepper_here">Set referensi 0</button>
<p class="note">5° = 57 half-step nominal. Scan limit ±513 half-step (45,1°). Referensi relatif/NVS, bukan encoder/homing.</p></section>
<section class="card"><h2>Axis Y · Servo elevasi</h2>
<button data-command="servo_arm">Arm servo · 30 dtk</button><button data-command="servo_test">Uji pulsa kecil</button><button data-command="servo_test_long">Uji pulsa panjang</button>
<button data-command="park_servo">Hold base 800</button><button data-command="servo_up_200">+200 µs</button><button data-command="servo_down_200">−200 µs</button><button data-command="servo_up_50">+50 µs</button><button data-command="servo_down_50">−50 µs</button><button data-command="servo_up_25">+25 µs</button><button data-command="servo_down_25">−25 µs</button><button data-command="release_servo">Release servo</button><button data-command="save_servo_here">Simpan base</button>
<p class="note">500 µs = atas, 950 µs = bawah. Scan mode membatasi 500–950 µs; manual tetap 500–1400 µs. Boot tetap detached.</p></section>
</div>
<div class="card"><h2>Pose &amp; keselamatan</h2><button data-command="release_pose">Release kedua axis</button>
<p class="warn">Kedua axis dapat ditahan bersamaan. Hold mempertahankan PWM/kumparan dan dapat panas; release/STOP melepas torsi sehingga arm dapat turun.</p></div>
</section>

<section id="tab-sensors" class="tab">
<div class="grid">
<section class="card"><h2>HC-SR04</h2><div id="hc-card" class="big">—</div><p id="hc-detail" class="note">—</p></section>
<section class="card"><h2>VL53L1X</h2><div id="tof-card" class="big">—</div><p id="tof-detail" class="note">—</p></section>
<section class="card"><h2>HLK-LD2410C</h2><div id="hlk-card" class="big">—</div><p id="hlk-detail" class="note">—</p></section>
</div>
<section class="card"><h2>Health &amp; statistik</h2><pre id="sensor-health-json">—</pre></section>
<section class="card"><h2>Raw sensors JSON</h2><pre id="sensors">—</pre></section>
</section>

<section id="tab-calibration" class="tab">
<div class="grid">
<section class="card"><h2>Fine jog</h2>
<button data-command="stepper_left_5">Stepper kiri 5°</button><button data-command="stepper_right_5">Stepper kanan 5°</button><button data-command="servo_up_25">Servo +25 µs</button><button data-command="servo_down_25">Servo −25 µs</button>
<p class="note">Gunakan scan mode agar limit ±45° dan 500–950 µs aktif.</p></section>
<section class="card"><h2>Scan mode</h2>
<button data-command="scan_mode_start">Aktifkan scan mode</button><button data-command="scan_mode_stop">Matikan scan mode</button>
<p class="note">Scan mode membatasi jog dan mengaktifkan sequential power guard: servo tidak boleh attach saat stepper bergerak; stepper tidak boleh bergerak saat servo attached. PC mapping menjalankan grid dan detach servo antar-kolom.</p><pre id="scan-json">—</pre></section>
<section class="card"><h2>Calibration</h2>
<p class="note">Gunakan HC sebagai referensi. Offset awal: HC 0 mm, ToF +50 mm (lensa ToF ~5 cm lebih maju). Kalibrasi final dilakukan di PC mapping.</p><pre id="calibration-json">—</pre></section>
</div>
<section class="card"><h2>Panduan singkat</h2>
<ol class="note"><li>Nyalakan sensor, hadapkan HC/ToF ke target yang sama.</li><li>Aktifkan scan mode.</li><li>Jalankan <code>tools/mapping/calibrate.py</code> di PC untuk setiap jarak ukur.</li><li>Setelah offset stabil, jalankan scan coarse 10°/50 µs.</li><li>Periksa point cloud di dashboard PC sebelum scan fine 5°/25 µs.</li></ol></section>
</section>

<section id="tab-scan" class="tab">
<div class="grid">
<section class="card"><h2>Envelope scan</h2><p class="note">Yaw −45°…+45° (step 5°/10°), tilt 500…950 µs (step 25/50 µs). Limit ini dipaksakan firmware saat scan mode aktif.</p><pre id="scan-limits">—</pre></section>
<section class="card"><h2>PC mapping dashboard</h2>
<label class="note" for="mapping-url">URL dashboard PC</label><input id="mapping-url" placeholder="http://127.0.0.1:8000/">
<div class="row"><button id="save-mapping-url" class="alt">Simpan URL</button><a id="open-mapping" class="pill" href="http://127.0.0.1:8000/" target="_blank" rel="noopener">Buka dashboard</a></div>
<p class="note">Dashboard PC menjalankan scan, kalibrasi, point cloud 3D isometrik, dan visualisasi. ESP32 tetap kontrol real-time/safety.</p></section>
</div>
<section class="card"><h2>Status scan</h2><pre id="scan-status">Belum ada scan.</pre></section>
</section>

<section id="tab-mapping" class="tab">
<section class="card"><h2>Mapping &amp; deep learning</h2>
<p class="note">Web ini sengaja dipisah dari dashboard diagnostik ESP32. Dashboard mapping berjalan di PC (Python standard library + canvas), membaca API ESP32, menyimpan scan ke <code>research/mapping/scans/</code>, lalu menampilkan point cloud 3D isometrik. Training deep learning dilakukan di PC setelah dataset terkumpul; ESP32 tidak menjalankan training.</p>
<div class="row"><a id="open-mapping-2" class="pill" href="http://127.0.0.1:8000/" target="_blank" rel="noopener">Buka mapping dashboard</a><a class="pill" href="/api/status" target="_blank">Raw ESP32 status</a></div>
<p class="warn">Jangan port-forward dashboard ke internet. Dashboard PC default hanya bind 127.0.0.1; jika bind LAN, gunakan jaringan tepercaya.</p></section>
</section>

<section id="tab-ota" class="tab">
<section class="card"><h2>Update firmware OTA</h2>
<p>Hanya pilih <b>firmware.bin aplikasi</b> hasil build proyek ini. Bukan bootloader, partitions, atau merged/factory image. Jangan memutus daya selama update.</p>
<input id="firmware" type="file" accept=".bin"><button id="upload">Upload OTA</button><progress id="progress" max="100" value="0"></progress>
<p id="otaResult" class="muted">HTTP LAN berautentikasi, bukan HTTPS. Rollback otomatis tidak disediakan.</p></section>
</section>

<section id="tab-diagnostics" class="tab">
<section class="card"><h2>Diagnostik</h2><button data-command="selftest">Self-test parser &amp; safety (sintetis)</button><pre id="status">—</pre></section>
</section>

<p id="result" role="status"></p>
<script>
'use strict';
let csrf='', state=null, uploading=false, polling=false;
const $=id=>document.getElementById(id);
const poseCommands=['park_stepper','stepper_left_10','stepper_right_10','stepper_left_5','stepper_right_5','park_servo','servo_up_200','servo_down_200','servo_up_50','servo_down_50','servo_up_25','servo_down_25','zero_stepper_here','save_servo_here','release_stepper','release_servo','release_pose'];
const warnings={
 sensors_start:'Konfirmasi: HC-SR04 memakai divider ECHO, VL53L1X diberi suplai sesuai label, ground bersama, dan axis diam?',
 scan_mode_start:'Aktifkan limit scan ±45° dan 500–950 µs? Ini tidak menggerakkan axis.',
 hlk_alert_on:'Aktifkan buzzer proximity HLK (≤30 cm + energy + cooldown)?',
 motor_arm:'Konfirmasi: rating motor/suplai cocok, jumper teridentifikasi, ground benar, tanpa beban. Arm motor?',
 servo_arm:'Konfirmasi: suplai servo sesuai rating (bukan 9 V), horn aman. Arm servo?',
 park_stepper:'Konfirmasi: mekanik stepper aman. Beri arus hold pada posisi sekarang?',
 stepper_left_10:'Konfirmasi clearance; geser kiri 10° nominal?', stepper_right_10:'Konfirmasi clearance; geser kanan 10° nominal?',
 stepper_left_5:'Konfirmasi clearance; geser kiri 5° nominal?', stepper_right_5:'Konfirmasi clearance; geser kanan 5° nominal?',
 park_servo:'Terapkan hold base tersimpan?', servo_up_200:'Geser +200 µs dan hold?', servo_down_200:'Geser −200 µs dan hold?',
 servo_up_50:'Geser +50 µs dan hold?', servo_down_50:'Geser −50 µs dan hold?', servo_up_25:'Geser +25 µs dan hold?', servo_down_25:'Geser −25 µs dan hold?',
 release_stepper:'Melepas stepper dapat membuat axis jatuh.', release_servo:'Melepas servo dapat membuat arm turun.',
 release_pose:'Melepas kedua hold dapat membuat arm turun.', zero_stepper_here:'Jadikan posisi sekarang referensi 0?', save_servo_here:'Simpan pulse servo sekarang sebagai base?'
};
async function session(){const r=await fetch('/api/session',{cache:'no-store'});if(!r.ok)throw Error('Autentikasi gagal: '+r.status);csrf=(await r.json()).csrf;}
async function command(name){
  if(uploading&&name!=='stop')return;
  if(warnings[name]&&!confirm(warnings[name]))return;
  try{const r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'text/plain','X-CSRF-Token':csrf},body:name});const data=await r.json();$('result').textContent=JSON.stringify(data);if(!r.ok)throw Error(data.message||r.status);setTimeout(refresh,250);}catch(e){$('result').textContent=e.message;}
}
function badge(id,value){const e=$(id);e.textContent=value||'—';e.className='badge '+(value||'');}
function render(s){
  state=s;
  $('summary').textContent=s.version+' · '+s.mode+' · '+s.wifi.ip+' · uptime '+Math.floor(s.uptime_ms/1000)+' dtk';
  const sensors=s.sensors||{}, hc=sensors.hc_sr04||{}, tof=sensors.vl53l1x||{}, hlk=sensors.hlk||s.hlk||{}, health=sensors.health||{}, scan=s.scan||{}, alert=s.hlk_alert||{};
  $('hc-value').textContent=hc.valid?((hc.distance_cal_cm??hc.distance_cm)+' cm'):'—';
  $('tof-value').textContent=tof.valid?((tof.distance_cal_cm??tof.distance_cm)+' cm'):'—';
  $('hlk-value').textContent=hlk.valid?(hlk.distance_cm+' cm'):'—';
  badge('hc-health',health.hc_sr04); badge('tof-health',health.vl53l1x); badge('hlk-health',health.hlk);
  $('health-line').textContent='Overall: '+(health.overall||'—')+' · ToF errors '+(sensors.stats?sensors.stats.tof_i2c_errors:'—')+' · rate '+(sensors.stats?sensors.stats.tof_error_rate_per_min:'—')+'/min';
  $('hc-card').textContent=hc.valid?((hc.distance_cal_cm??hc.distance_cm)+' cm'):'—';
  $('tof-card').textContent=tof.valid?((tof.distance_cal_cm??tof.distance_cm)+' cm'):'—';
  $('hlk-card').textContent=hlk.valid?(hlk.distance_cm+' cm'):'—';
  $('hc-detail').textContent='raw '+hc.distance_mm+' mm · cal '+hc.distance_cal_mm+' mm · valid '+hc.valid_samples+' · timeout '+hc.timeouts;
  $('tof-detail').textContent='raw '+tof.distance_mm+' mm · cal '+tof.distance_cal_mm+' mm · '+tof.status+' · responsive '+tof.responsive+' · errors '+(sensors.stats?sensors.stats.tof_i2c_errors:'—');
  $('hlk-detail').textContent='energy '+hlk.energy+' · target '+hlk.target_state+' · frames '+hlk.frames+' · min range '+hlk.min_range_cm+' cm';
  $('sensors').textContent=JSON.stringify(sensors,null,2);
  $('sensor-health-json').textContent=JSON.stringify({health:health,stats:sensors.stats,calibration:sensors.calibration},null,2);
  $('scan-json').textContent=JSON.stringify(scan,null,2);
  $('scan-limits').textContent=JSON.stringify(scan,null,2);
  $('calibration-json').textContent=JSON.stringify(sensors.calibration||{},null,2);
  $('hlk').textContent=(s.hlk.valid?'VALID':s.hlk.stale?'STALE':'BELUM VALID')+' · alert '+(alert.enabled?'ON':'OFF')+' · '+(alert.min_cm||30)+'–'+(alert.max_cm||75)+' cm · '+(alert.state||'idle')+' · '+(alert.mute_reason||'—')+' · count '+(alert.count||0)+'\n'+JSON.stringify(s.hlk.last_reading,null,2);
  $('status').textContent=JSON.stringify(s,null,2);
  const mappingUrl=localStorage.getItem('mappingUrl')||'http://127.0.0.1:8000/';
  if(document.activeElement!==$('mapping-url'))$('mapping-url').value=mappingUrl;
  $('open-mapping').href=mappingUrl; $('open-mapping-2').href=mappingUrl;
  $('scan-status').textContent=JSON.stringify(scan,null,2);
  for(const b of document.querySelectorAll('[data-command]')){
    const c=b.dataset.command;
    const isPose=poseCommands.includes(c);
    const scanMode=!!scan.mode;
    b.disabled=uploading||s.ota_active||
      (isPose&&(s.mode!=='IDLE'&&s.mode!=='PARKED'))||
      (['sensors_start','sensors_stop','scan_mode_start'].includes(c)&&(s.mode!=='IDLE'&&s.mode!=='PARKED'))||
      (c==='scan_mode_stop'&&!scanMode)||
      (c==='scan_mode_start'&&!sensors.enabled)||
      (['hlk_alert_on'].includes(c)&&!s.hlk.enabled)||
      (['step_test','step_test_long'].includes(c)&&!s.motor_armed)||
      (['servo_test','servo_test_long'].includes(c)&&!s.servo_armed)||
      (['park_stepper','stepper_left_10','stepper_right_10','stepper_left_5','stepper_right_5','zero_stepper_here'].includes(c)&&s.actuators.stepper_energized&&!s.actuators.stepper_holding)||
      (c==='release_stepper'&&!s.actuators.stepper_holding)||
      (['release_servo','save_servo_here'].includes(c)&&!s.actuators.servo_holding)||
      (c==='release_pose'&&s.mode!=='PARKED')||
      ((s.mode!=='IDLE')&&['buzzer_test','motor_arm','servo_arm','step_test','step_test_long','servo_test','servo_test_long','selftest'].includes(c));
  }
}
async function refresh(){if(uploading||polling)return;polling=true;try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);render(await r.json());}catch(e){$('summary').textContent='Tidak terhubung: '+e.message+' · tidak ada gerakan yang dijadwalkan ulang.';}finally{polling=false;}}
for(const b of document.querySelectorAll('[data-command]'))b.onclick=()=>command(b.dataset.command);
for(const b of document.querySelectorAll('[data-tab]'))b.onclick=()=>{for(const t of document.querySelectorAll('[data-tab]'))t.classList.toggle('active',t===b);for(const s of document.querySelectorAll('.tab'))s.classList.toggle('active',s.id==='tab-'+b.dataset.tab);};
$('stop').onclick=()=>command('stop');
$('save-mapping-url').onclick=()=>{const value=$('mapping-url').value.trim()||'http://127.0.0.1:8000/';localStorage.setItem('mappingUrl',value);$('open-mapping').href=value;$('open-mapping-2').href=value;};
$('upload').onclick=async()=>{
  const file=$('firmware').files[0];if(!file||file.name!=='firmware.bin'){alert('Pilih file aplikasi dengan nama firmware.bin.');return;}
  if(!state||file.size>state.ota.next_slot_bytes){alert('Ukuran melebihi slot OTA atau status belum tersedia.');return;}
  if(!confirm('Aktuator akan dihentikan dan disarm. Upload aplikasi dan reboot ke IDLE?'))return;
  uploading=true;$('upload').disabled=true;if(state)render(state);$('otaResult').textContent='Mengirim; progres transfer belum membuktikan flash/update sukses.';
  const xhr=new XMLHttpRequest();xhr.open('POST','/api/ota');xhr.timeout=130000;
  xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-CSRF-Token',csrf);xhr.setRequestHeader('X-Firmware-Name','firmware.bin');
  xhr.upload.onprogress=e=>{if(e.lengthComputable)$('progress').value=100*e.loaded/e.total;};
  xhr.onload=()=>{uploading=false;$('upload').disabled=false;$('otaResult').textContent=xhr.responseText;if(xhr.status===200){$('otaResult').textContent+=' · Tunggu reboot, lalu pastikan versi baru dan IDLE.';setTimeout(async()=>{try{await session();}catch(e){}await refresh();},5000);}else refresh();};
  xhr.onerror=xhr.ontimeout=()=>{uploading=false;$('upload').disabled=false;$('otaResult').textContent='Koneksi gagal. Jangan anggap OTA sukses; cek versi/status atau recovery USB.';};xhr.send(file);
};
(async()=>{try{await session();await refresh();}catch(e){$('summary').textContent=e.message;}})();setInterval(refresh,1500);
</script></html>)HTML";
