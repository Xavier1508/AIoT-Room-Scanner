# AIoT ESP32-S3 — bring-up, diagnostik LAN, dan web OTA

Firmware pengujian **buzzer aktif, HLK-LD2410C, 28BYJ-48/ULN2003, dan SG90**.
Firmware berjalan terverifikasi saat ini: **0.2.3-park-pose**, termasuk pemilihan SSID dari
pemindaian radio ESP32-S3 (lihat status proyek untuk hasil terbaru).
Belum ada pemetaan 3D, TinyML, CSI, data ToF, atau pembacaan CDM324.
Status hasil aktual: [docs/project-state.md](docs/project-state.md) dan
[docs/test-report.md](docs/test-report.md). Jangan menyamakan build dengan lulus hardware.

## Keselamatan dan daya

- **USB laptop dan jack 9 V jangan digunakan bersama** sebelum proteksi backfeed diketahui.
- Upload/recovery awal: jack dicabut, semua modul/beban dilepas, satu USB data.
- Uji beban sambil USB: USB untuk board; motor/servo dari sumber sesuai rating,
  negatif disatukan ke GND ESP. Positif sumber beban **tidak** disambung ke 5V shield.
- Standalone: cabut USB **dahulu**, baru pasang adaptor jack. Sumber motor/servo
  tetap harus sesuai rating yang diverifikasi. Jangan berikan 9 V ke SG90.
- Kapasitas adaptor/regulator dan voltase rail belum diukur. Board menyala atau
  tidak reset **bukan** bukti suplai aman. Brownout log bukan voltmeter.
- Mode `PARKED` mempertahankan kumparan stepper dan PWM servo untuk menahan pose;
  `release_pose`/`stop` melepasnya sehingga beban dapat turun. Uji tanpa beban,
  dukung mekanik, dan siapkan pemutusan daya fisik. Software bukan emergency-stop fisik.
- Firmware tidak bisa membuktikan kontinuitas kabel, arus, tegangan, atau gerakan
  motor tanpa pengukuran/umpan balik tambahan. Jangan memasukkan 5/9 V ke GPIO.

## Wiring yang dipertahankan

Semua nomor adalah **GPIO**, bukan nomor urut header.

| Perangkat | Sambungan |
|---|---|
| HLK TX | ESP RX GPIO16 |
| HLK RX | ESP TX GPIO17 |
| HLK OUT (opsional) | GPIO18; raw dengan pull-down, koneksi belum diverifikasi |
| HLK VCC/GND | 5 V sesuai manual (>200 mA sumber modul), ground bersama |
| ULN2003 IN1/2/3/4 | GPIO4/5/6/7 |
| ULN2003 daya | Sumber sesuai **label motor 5 V atau 12 V**, negatif ke ground bersama |
| Motor | Konektor putih lima pin bawaan; jangan menebak jumper +/− |
| SG90 sinyal | GPIO15, 50 Hz |
| SG90 merah/cokelat | Suplai sesuai unit / GND bersama; bukan 9 V |
| Buzzer I/O/VCC/GND | GPIO21 / 3V3 / GND; LOW bunyi, HIGH diam |
| ToF cadangan | SDA8, SCL9; belum digunakan |
| CDM324 | **Tidak terhubung/tidak diberi daya**; GPIO1 hanya cadangan pengondisi |

Tidak menggunakan GPIO35/36/37, USB19/20, strapping0/3/45/46, atau console43/44.
Stepper memakai tabel half-step eksplisit bit IN1..IN4, bukan AccelStepper;
tidak ada perubahan urutan kabel. Pull-up buzzer eksternal 10 kΩ bisa membantu
saat reset, tetapi pemasangannya **belum dikonfirmasi**. Boot aman software baru
berlaku setelah aplikasi mulai, bukan jaminan level pin selama ROM/reset.

## Build yang terkunci

- PlatformIO Core teramati: 6.2.0.
- `espressif32@6.12.0`, Arduino-ESP32 **2.0.17**
  (`3.20017.241212+sha.dcc1105b`). Library WiFi/ESPmDNS/Preferences bawaan core.
- GCC Xtensa/RISC-V `8.4.0+2021r2-patch5`, esptool **4.9.0**.
- ESP32-S3 rev0.2, flash quad **16 MB** terdeteksi via esptool.
  eFuse melaporkan embedded PSRAM8MB, **tidak diinisialisasi/digunakan**.
- Flash DIO80MHz memakai bootloader yang benar-benar disediakan SDK ini.
  SDK ini tidak menyediakan `bootloader_dio_40m.elf`.
- `default_16MB.csv` sama dengan tabel yang dibaca dari perangkat sebelum upload:
  app0 `0x10000`, app1 `0x650000`, masing-masing **0x640000 = 6.553.600 byte**.
  NVS `0x9000` dan SPIFFS `0xc90000` tidak dipindahkan.
- Board ID dasar masih menampilkan nama N8 di banner PlatformIO; override
  flash dan tabel partisi ada di `platformio.ini`, bukan bukti dari nama banner.

Di PowerShell dari root proyek:

```powershell
.\tools\ops\test.ps1
.\tools\ops\build.ps1
```

Wrapper memakai instalasi PlatformIO yang sudah ada di `$HOME\.platformio`,
memeriksa dependensi yang dibutuhkan sebelum build, menonaktifkan telemetri,
dan tidak menginstal dependency yang hilang. Bila belum tersedia, minta izin
instalasi terpisah. Output final berada di `analysis/platformio/build-<UTC>/`:
`firmware.bin`, `bootloader.bin`, `partitions.bin`, `boot_app0.bin`, `build.txt`,
`manifest.json` (hash sumber/binary dan ukuran slot), serta `usage.txt`.
Objek, cache, dan ELF disposable dihapus otomatis setelah build.

## Upload USB pertama / recovery

COM9 awalnya teridentifikasi sebagai native **USB Serial/JTAG** Espressif,
bukan converter USB-to-UART. Port dapat berubah setelah reset/recovery.
Tutup terminal serial sebelum upload. Deteksi port:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" -B .\tools\ops\device.py ports
```

Dengan kondisi daya aman, gunakan esptool yang terpasang. Ganti `<RUN>` dengan
folder build yang benar dan `<PORT>` dengan port hasil identifikasi, bukan tebakan:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" -B "$env:USERPROFILE\.platformio\packages\tool-esptoolpy\esptool.py" --chip esp32s3 --port <PORT> --baud 115200 --after hard_reset write_flash --flash_mode dio --flash_freq 80m --flash_size 16MB 0x0 <RUN>\bootloader.bin 0x8000 <RUN>\partitions.bin 0xe000 <RUN>\boot_app0.bin 0x10000 <RUN>\firmware.bin
```

Perintah ini mengganti bootloader/aplikasi dan menginisialisasi pemilihan OTA;
**tidak** melakukan `erase_flash` dan tidak menulis NVS/SPIFFS. Tabel harus tetap
cocok sebelum memakai perintah ini pada board lain. Tidak mengekstrak firmware
lama atau rahasia NVS. Simpan data pengguna secara terpisah bila memang diperlukan.

Jika download gagal: jack/beban tetap dilepas, tahan BOOT, tekan-lepas RESET/EN,
lepas BOOT, enumerasi ulang port, lalu ulangi. Tidak ada rollback otomatis.

## Konfigurasi Wi-Fi secara lokal — jangan kirim password ke chat

Firmware tidak mempunyai SSID/password default, AP darurat, atau `admin/admin`.
Tanpa konfigurasi, board tetap IDLE dan web belum tersedia.
Dengan USB masih terpasang, jalankan di terminal Anda sendiri:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" -B .\tools\ops\device.py setup
```

Alternatif dengan pengaturan scratch otomatis: `.\tools\ops\setup.ps1`.
Tutup monitor serial lain; hanya satu proses boleh menggunakan COM perangkat.
Jika ada error, jendela wrapper tetap terbuka sampai Enter agar pesannya terbaca.
Catatan otomatis hanya menyimpan tahap dan jenis error, bukan input/password.
Jangan menganggap jendela tertutup berarti konfigurasi atau OTA sukses.

ESP melakukan **scan beacon pasif 2,4 GHz** dan PowerShell menampilkan pilihan
bernomor: SSID, RSSI, kanal, dan keamanan. Pilih nomor jaringan milik Anda/yang
diizinkan, lalu isi password Wi-Fi dan password web unik 16–64 karakter.
Tidak perlu mengetik SSID biasa. Pilihan `R` mengulang scan, `Q` membatalkan,
dan `M` hanya untuk SSID tersembunyi/manual. ESP32-S3 tidak dapat melihat jaringan
5 GHz murni; beacon tersembunyi juga tidak membocorkan nama SSID secara ajaib.
Daftar menggabungkan SSID+keamanan yang sama, mengurutkan sinyal terkuat, dan
dibatasi 48 pilihan (8 halaman × 6) agar transfer USB tetap kecil. SSID diperlakukan
sebagai data, di-hex pada protokol dan di-escape untuk tampilan terminal.
Ini **bukan** scan IP/port, brute force, atau bukti jaringan itu milik Anda.
Password tidak di-echo/dicetak. Konfigurasi disimpan sebagai satu
blob NVS; firmware tidak menulis konfigurasi HLK. Wi-Fi password tidak disimpan
di PC. Akses web disimpan lokal di `tools/ops/device.local.json` untuk otomasi;
file ini gitignored, **tidak terenkripsi**, dan tidak boleh dibagikan/dimasukkan
ke laporan atau Git. Contoh tanpa rahasia: `tools/ops/secrets.example.json`.
NVS juga tidak diklaim terenkripsi atau tahan ekstraksi fisik.

Jangan cabut USB sebelum status menunjukkan Wi-Fi tersambung dan web siap.
Username web: `admin`; password adalah yang **Anda** tentukan, tanpa default.
Ganti Wi-Fi/password web dengan menjalankan `setup` ulang saat USB-only; tidak
perlu flash ulang. Arm tidak disimpan dalam NVS dan tidak ikut pulih setelah reboot.

## Diagnostik dan pengujian

```powershell
$python = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
& $python -B .\tools\ops\device.py serial status
& $python -B .\tools\ops\device.py verify-usb
& $python -B .\tools\ops\device.py status
& $python -B .\tools\ops\device.py lan-test
& $python -B .\tools\ops\device.py open
```

`verify-usb`/`lan-test` hanya memeriksa safe state, penolakan perintah tanpa arm,
parser/safety sintetis, dan proteksi HTTP (LAN). Tidak menyalakan aktuator.
Uji sintetis **tidak** mengisi data radar live. Laporan pin/keluaran adalah status
software, bukan pengukuran tegangan atau bukti beban terhubung.

Console USB menerima baris perintah pada 115200, respons `AIOT <JSON>`.
Native USB memakai HWCDC bawaan core, RX 1024/TX 2048 byte, maksimum satu
paket TX per loop dan timeout TX terbatas 2 ms. SDK log sekunder dimatikan agar
tidak mencampuri framing diagnostik. Nomor baud adalah
konfigurasi terminal, bukan pengaturan clock USB. Host tidak mengulang otomatis
perintah gerak yang timeout. Revisi penuh chip berasal dari esptool; telemetry
`revision_major_core_api` hanya melaporkan major revision dari core Arduino.
Host memberi jeda konservatif 250 ms antarperintah USB. Rangkaian cepat pernah
mengalami paket parsial/timeout; hasil console yang dilaporkan berlaku pada
pacing ini, bukan jaminan throughput tinggi. Detail ada di docs/known-issues.md.
Perintah yang sama tersedia di web dan `device.py command <perintah>`:

| Perintah | Perilaku |
|---|---|
| help / status | Daftar perintah / snapshot diagnostik (console) |
| buzzer_test | 3 × 150 ms, jeda 350 ms, akhirnya OFF |
| hlk_start / hlk_stop | Mulai/hentikan UART pasif, tanpa perintah konfigurasi |
| motor_arm / step_test | Arm 30 detik, satu uji 64 half-step maju lalu mundur ~100/s |
| servo_arm / servo_test | Arm 30 detik, satu uji 1500/1450/1500/1550/1500 µs |
| step_test_long / servo_test_long | Uji bounded: 512 half-step maju/mundur atau pulsa kecil berulang; bukan putaran/sweep kontinu |
| park_pose | Dari referensi stepper relatif 0, gerak nominal: servo 2000 µs dan stepper 512 half-step dengan tanda arah yang dikonfigurasi; lalu tahan keduanya |
| release_pose | Hanya dari `PARKED`; lepas hold dan kembali IDLE |
| stop | Batalkan jadwal/antrean, buzzer OFF, kumparan LOW, detach, disarm |
| selftest | Fixture parser/safety terisolasi; tidak menguji sensor fisik |
| wifi_scan | Hentikan/disarm aktuator; mulai scan SSID pasif asynchronous |
| wifi_scan_results | Metadata scan, jumlah, dan halaman; tanpa mencoba koneksi |
| wifi_scan_page_0 … wifi_scan_page_7 | Enam pilihan SSID per halaman, dalam hex dan metadata |
| wifi_scan_cancel | Batalkan scan; tidak mengganti kredensial |

Perintah tidak dikenal tidak menggerakkan perangkat. Arm dikonsumsi satu uji
dan hilang setelah stop, timeout, reboot, OTA, atau putus Wi-Fi yang terdeteksi.
Setelah Wi-Fi dikonfigurasi, kegagalan koneksi juga menolak arm/uji aktuator;
console diagnostik dan pembacaan radar tetap dapat digunakan.
Selama scan berjalan, arm/uji aktuator ditolak; stop membatalkan scan dan OTA
membatalkan scan sebelum menerima image. Tanpa konfigurasi, radio dimatikan lagi
setelah scan, tidak membuka AP, dan tidak mencoba password jaringan sekitar.

Uji scan tanpa kredensial/menampilkan SSID ke log agen:

```powershell
& $python -B .\tools\ops\device.py scan --summary
```

Tanpa `--summary`, CLI menampilkan hasil metadata scan. Menu interaktif tetap
berada di `setup`. WEP/WPA1/Enterprise tidak didukung alur password sederhana ini;
gunakan jaringan WPA2/WPA3 Personal yang sesuai atau OPEN yang sengaja diizinkan
(dengan peringatan). Tidak mengubah jaringan Wi-Fi laptop atau router.
Stepper mempunyai soft limit ±128 langkah untuk uji pendek dan ±1024 langkah
untuk uji panjang/pose relatif dari boot, bukan homing, encoder, atau sudut
absolut. `park_pose` memperkirakan 45° dengan 512 half-step pada varian
4096 half-step/rev; arah clockwise dan sudut aktual harus diverifikasi secara
fisik. Jangan putar horizontal searah terus-menerus.
OUT HLK bersifat raw/unverified; presence live hanya boleh ditafsirkan dari frame
valid dan belum stale. Batas stale 2 detik, timeout frame parsial 100 ms.
Jarak HLK bukan koordinat manusia atau bukti objek mendekat.

## Web dan OTA tanpa USB

Web berada pada IP dari status, atau `http://aiot-room.local` bila mDNS tersedia.
Wi-Fi station, retry 15 detik tanpa loop tunggu koneksi; tidak membuka AP otomatis.
Halaman menampilkan versi, uptime, status suplai **tidak diukur**, reset/brownout,
memori, status perangkat, radar valid/stale, arm/test/stop, dan upload firmware.
HTTP berjalan pada task terpisah dari loop perangkat.

Dashboard menyediakan tes panjang yang tetap bounded: stepper 512 half-step
maju lalu 512 mundur, serta pengulangan pulsa servo kecil sekitar 8 detik.
Tes tersebut bukan putaran kontinu atau sweep absolut dan tidak dijalankan
otomatis setelah OTA. Lakukan hard-refresh browser setelah OTA untuk memuat
tombol baru.

Dashboard juga menyediakan `park_pose` untuk merapikan posisi dari referensi
stepper relatif 0: servo diberi pulsa nominal 2000 µs dan stepper bergerak 512
half-step searah tanda clockwise yang dikonfigurasi, lalu keduanya tetap
menahan posisi. Ini bukan posisi absolut;
tidak ada encoder/homing dan firmware tidak melakukan park otomatis saat boot
atau OTA. Gunakan `release_pose` atau tombol STOP untuk melepas hold setelah
mekanik sudah aman.

Dashboard utama adalah root URL:

```text
http://<IP-ESP>/
```

Contoh saat ini: `http://192.168.1.200/`. Endpoint `/api/status` dan
`/api/session` memang menampilkan JSON; jika browser menampilkan JSON, hapus
bagian `/api/status` dari URL dan buka root `/`.

Seluruh halaman/API memakai HTTP Basic; POST kontrol/update juga membutuhkan
token CSRF per boot, Host yang cocok, dan penolakan Origin lintas situs.
**Autentikasi bukan enkripsi**: LAN HTTP dapat disadap/manipulasi di jaringan
tidak tepercaya. Ini bukan HTTPS, secure boot, atau firmware signing. Jangan
port-forward router atau mempublikasikan kontrol ke internet.

Setelah akses LAN diuji: **cabut USB dahulu**, baru gunakan adaptor jack.
Jalankan `device.py status` lagi untuk membuktikan akses standalone. Bila DHCP
mengganti IP, gunakan mDNS atau status USB-only setelah mematikan jack; jangan
melakukan scan jaringan. Konfigurasi IP CLI lokal boleh diperbarui ke IP teramati.

Untuk OTA nyata, ubah `config::version` pada `include/config.h`, pertahankan
kode OTA, build lagi, lalu pilih **hanya `firmware.bin`** dari run baru di halaman
web. Alternatif CLI yang sekaligus memverifikasi versi baru:

```powershell
& $python -B .\tools\ops\device.py ota <RUN-BARU>\firmware.bin --expect-version <VERSI-BARU>
```

OTA menghentikan/disarm aktuator sebelum menerima image, menolak gerak selama
update, memeriksa jenis aplikasi ESP32-S3 dan ukuran slot, memvalidasi image lewat
IDF, lalu reboot. Kegagalan meninggalkan aktuator OFF/disarmed. Saat transfer,
handler HTTP upload sibuk, tetapi loop perangkat/console tetap berjalan; web
lain dapat menunggu/timeout dan tidak boleh dianggap sukses. Jangan mematikan daya.
Progres transfer 100% atau respons upload **bukan** bukti versi baru sudah boot.
Pastikan versi baru, koneksi kembali, IDLE, dan kedua arm false.

**Bootloader, partitions, boot_app0, merged/factory image tidak boleh lewat OTA.**
Perubahan tabel partisi bukan update aplikasi biasa. Firmware penerus wajib
mempertahankan web OTA. Jalur ESPOTA PlatformIO tidak diaktifkan; web/CLI HTTP
adalah jalur praktis tunggal agar tidak menambah port layanan lain.
Recovery bila OTA/network gagal memakai USB sesuai bagian di atas.

## Struktur dan bukti

`include/` dan `src/`: pin, batas, parser, safety, controller, console, NVS,
Wi-Fi/web/OTA. `tests/`: fixture sintetis. `tools/ops/`: build/test/provisioning
yang dapat dipakai ulang. `docs/openapi.json` adalah kontrak HTTP lokal.
`analysis/<tool>/<run>/`: firmware, output dan manifest per run, gitignored.
`research/`: observasi/evidence/audit melalui CLI riset global, bukan edit SQL.
Scratch `.opencode-tmp/` dibersihkan setelah dipakai.

Repository lokal boleh diinisialisasi. Remote/push menunggu konfirmasi platform,
nama, dan visibilitas; tidak ada token/password Git yang dibaca dari credential store.
