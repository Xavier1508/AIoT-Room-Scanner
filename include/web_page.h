#pragma once

#include <Arduino.h>

static const char webPage[] PROGMEM = R"HTML(<!doctype html>
<html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIoT ESP32-S3 · Bring-up</title>
<style>
:root{color-scheme:dark;font:16px system-ui;background:#101722;color:#e6edf6}body{max-width:1000px;margin:auto;padding:24px}h1{font-size:1.7rem}h2{font-size:1.1rem}.muted{color:#a8b8ca}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.card{background:#192434;padding:18px;border:1px solid #33465e;border-radius:12px;margin:14px 0}button{font:inherit;background:#285f94;color:white;border:0;border-radius:7px;padding:11px 15px;margin:5px;cursor:pointer}button:disabled{opacity:.4;cursor:not-allowed}.stop{background:#bc3434;font-weight:800;font-size:1.1rem;width:100%;margin:0;position:sticky;top:8px;z-index:1}.warn{border-left:4px solid #e0b151;padding-left:14px;color:#edcf91}pre{white-space:pre-wrap;word-break:break-word;font-size:13px;max-height:360px;overflow:auto}input{max-width:100%;margin:10px 0}progress{width:100%}.ok{color:#80d8a5}#result{min-height:24px}a{color:#95caff}
</style>
<h1>AIoT ESP32-S3 <span class="muted">/ bring-up</span></h1>
<p id="summary" class="muted">Menghubungkan…</p>
<button class="stop" id="stop">STOP · matikan keluaran &amp; disarm</button>
<p class="warn">Software stop bukan pemutus daya fisik. Pelepasan torsi dapat menjatuhkan beban.
Uji awal tanpa beban. Nilai GPIO/log bukan bukti tegangan, kontinuitas kabel, atau gerakan nyata.</p>
<div class="grid">
<section class="card"><h2>Buzzer &amp; radar</h2>
<button data-command="buzzer_test">3 beep</button><button data-command="hlk_start">Mulai HLK</button><button data-command="hlk_stop">Hentikan HLK</button>
<p class="muted">HLK pasif 256000 baud; tidak mengubah konfigurasi sensor.</p><pre id="hlk">Belum ada data valid.</pre></section>
<section class="card"><h2>Stepper</h2><button data-command="motor_arm">Arm motor · 30 dtk</button><button data-command="step_test">64 maju / 64 mundur</button><button data-command="step_test_long">512 maju / 512 mundur · panjang</button>
<p class="muted">Uji panjang sekitar 10 dtk, tetap terbatas dan bukan putaran kontinu. Rating motor, suplai, jumper, ground, dan mekanik harus Anda verifikasi dahulu. Langkah relatif, bukan sudut terkalibrasi.</p>
<h2>Servo</h2><button data-command="servo_arm">Arm servo · 30 dtk</button><button data-command="servo_test">Uji pulsa kecil</button><button data-command="servo_test_long">Uji pulsa kecil · panjang</button>
<p class="muted">Uji panjang sekitar 8 dtk, hanya 1450/1500/1550 µs berulang. Jangan beri 9 V. Uji tanpa beban.</p></section>
<section class="card"><h2>Pose parkir</h2>
<button data-command="park_pose">Park pose · servo 90° kanan + stepper 45° kanan</button>
<button data-command="release_pose">Release pose · lepas hold</button>
<p class="warn">Park pose adalah gerakan relatif nominal: servo memakai pulsa 2000 µs dan stepper 512 half-step. Tidak ada encoder/homing, jadi sudut absolut dan arah kanan harus Anda verifikasi. Pose mempertahankan PWM servo dan kumparan stepper; release/STOP melepas torsi dan dapat menjatuhkan lengan. Pastikan clearance, kabel tidak tertarik, dan siapkan pemutus daya fisik.</p></section>
</div>
<p id="result" role="status"></p>
<section class="card"><h2>Update firmware OTA</h2>
<p>Hanya pilih <b>firmware.bin aplikasi</b> hasil build proyek ini. Bukan bootloader, partitions, atau merged/factory image.
Firmware penerus wajib mempertahankan OTA. Jangan memutus daya selama update.</p>
<input id="firmware" type="file" accept=".bin"><button id="upload">Upload OTA</button><progress id="progress" max="100" value="0"></progress>
<p id="otaResult" class="muted">HTTP LAN berautentikasi, bukan HTTPS. Jangan buka port router. Rollback otomatis tidak disediakan.</p></section>
<section class="card"><h2>Diagnostik &amp; jejak peristiwa</h2><button data-command="selftest">Self-test parser &amp; safety (sintetis)</button><pre id="status"></pre></section>
<script>
'use strict';
let csrf='', state=null, uploading=false, polling=false;
const $=id=>document.getElementById(id);
async function session(){const r=await fetch('/api/session',{cache:'no-store'});if(!r.ok)throw Error('Autentikasi gagal: '+r.status);csrf=(await r.json()).csrf;}
async function command(name){
  if(uploading&&name!=='stop')return;
const warnings={motor_arm:'Konfirmasi: rating motor/suplai cocok, jumper teridentifikasi, ground benar, tidak ada beban dan kabel bebas. Arm motor?',servo_arm:'Konfirmasi: suplai servo sesuai rating (bukan 9 V), ground benar, horn tanpa beban dan siap menghentikan daya bila macet. Arm servo?',park_pose:'Konfirmasi: clearance mekanik aman, kabel/lengan tidak tertarik, stepper dan servo siap bergerak, serta Anda siap menekan STOP atau memutus daya fisik. Park pose nominal 90°/45° searah jarum jam dan menahan torsi?',release_pose:'Konfirmasi: melepas hold servo dan kumparan stepper dapat membuat lengan turun atau kabel berubah posisi. Lepaskan pose?'};
  if(warnings[name]&&!confirm(warnings[name]))return;
  try{const r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'text/plain','X-CSRF-Token':csrf},body:name});const data=await r.json();$('result').textContent=JSON.stringify(data);if(!r.ok)throw Error(data.message||r.status);setTimeout(refresh,250);}catch(e){$('result').textContent=e.message;}
}
function render(s){
  state=s;$('summary').textContent=s.version+' · '+s.mode+' · '+s.wifi.ip+' · uptime '+Math.floor(s.uptime_ms/1000)+' dtk';
  $('hlk').textContent=(s.hlk.valid?'VALID':s.hlk.stale?'STALE — jangan dipakai sebagai data terkini':'BELUM VALID')+'\n'+JSON.stringify(s.hlk.last_reading,null,2);
  $('status').textContent=JSON.stringify(s,null,2);
  for(const b of document.querySelectorAll('[data-command]')){const c=b.dataset.command;b.disabled=uploading||s.ota_active||(['step_test','step_test_long'].includes(c)&&!s.motor_armed)||(['servo_test','servo_test_long'].includes(c)&&!s.servo_armed)||(c==='park_pose'&&(s.mode!=='IDLE'||s.motor_armed||s.servo_armed||s.actuators.relative_half_steps!==0))||(c==='release_pose'&&s.mode!=='PARKED')||((s.mode!=='IDLE')&&['buzzer_test','motor_arm','servo_arm','step_test','step_test_long','servo_test','servo_test_long','park_pose','selftest'].includes(c));}
}
async function refresh(){if(uploading||polling)return;polling=true;try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const s=await r.json();render(s);}catch(e){$('summary').textContent='Tidak terhubung: '+e.message+' · periksa daya/Wi-Fi; tidak ada gerakan yang dijadwalkan ulang.';}finally{polling=false;}}
for(const b of document.querySelectorAll('[data-command]'))b.onclick=()=>command(b.dataset.command);
$('stop').onclick=()=>command('stop');
$('upload').onclick=async()=>{
  const file=$('firmware').files[0];if(!file||file.name!=='firmware.bin'){alert('Pilih file aplikasi dengan nama firmware.bin.');return;}
  if(!state||file.size>state.ota.next_slot_bytes){alert('Ukuran melebihi slot OTA atau status belum tersedia.');return;}
  if(!confirm('Aktuator akan dihentikan dan disarm. Upload aplikasi dan reboot ke IDLE?'))return;
  uploading=true;$('upload').disabled=true;if(state)render(state);$('otaResult').textContent='Mengirim; progres transfer belum membuktikan flash/update sukses.';
  const xhr=new XMLHttpRequest();xhr.open('POST','/api/ota');xhr.timeout=130000;
  xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-CSRF-Token',csrf);xhr.setRequestHeader('X-Firmware-Name','firmware.bin');
  xhr.upload.onprogress=e=>{if(e.lengthComputable)$('progress').value=100*e.loaded/e.total;};
  xhr.onload=()=>{uploading=false;$('upload').disabled=false;$('otaResult').textContent=xhr.responseText;if(xhr.status===200){$('otaResult').textContent+=' · Tunggu reboot, kemudian pastikan versi baru dan IDLE.';setTimeout(async()=>{try{await session();}catch(e){}await refresh();},5000);}else refresh();};
  xhr.onerror=xhr.ontimeout=()=>{uploading=false;$('upload').disabled=false;$('otaResult').textContent='Koneksi gagal. Jangan anggap OTA sukses; cek versi/status atau recovery USB.';};xhr.send(file);
};
(async()=>{try{await session();await refresh();}catch(e){$('summary').textContent=e.message;}})();setInterval(refresh,1500);
</script></html>)HTML";
