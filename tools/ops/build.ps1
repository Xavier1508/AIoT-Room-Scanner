param([ValidateRange(1, 4)][int]$Jobs = 2)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$run = Join-Path $root "analysis\platformio\build-$stamp"
$scratch = Join-Path $root ".opencode-tmp\build-$stamp"
$python = Join-Path $HOME '.platformio\penv\Scripts\python.exe'
$platforms = Join-Path $HOME '.platformio\platforms'
$packages = Join-Path $HOME '.platformio\packages'
if (!(Test-Path -LiteralPath $python)) { throw 'Existing PlatformIO Python not found. Installation requires approval.' }
foreach ($name in @('framework-arduinoespressif32', 'tool-esptoolpy', 'tool-scons', 'toolchain-xtensa-esp32s3')) {
    if (!(Test-Path -LiteralPath (Join-Path $packages "$name\package.json"))) { throw "Missing installed package: $name. Do not auto-install." }
}
New-Item -ItemType Directory -Path $run | Out-Null
New-Item -ItemType Directory -Path $scratch | Out-Null
$names = @('TEMP','TMP','TMPDIR','PYTHONDONTWRITEBYTECODE','PLATFORMIO_CORE_DIR','PLATFORMIO_CACHE_DIR','PLATFORMIO_WORKSPACE_DIR','PLATFORMIO_PACKAGES_DIR','PLATFORMIO_PLATFORMS_DIR','PLATFORMIO_SETTING_ENABLE_TELEMETRY','PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL','PLATFORMIO_SETTING_CHECK_PRUNE_SYSTEM_THRESHOLD')
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
Push-Location $root
try {
    $env:TEMP = $scratch; $env:TMP = $scratch; $env:TMPDIR = $scratch
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PLATFORMIO_CORE_DIR = Join-Path $scratch 'pio-core'
    $env:PLATFORMIO_CACHE_DIR = Join-Path $scratch 'pio-cache'
    $env:PLATFORMIO_WORKSPACE_DIR = Join-Path $scratch 'pio-workspace'
    $env:PLATFORMIO_PACKAGES_DIR = $packages
    $env:PLATFORMIO_PLATFORMS_DIR = $platforms
    $env:PLATFORMIO_SETTING_ENABLE_TELEMETRY = 'false'
    $env:PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL = '36500'
    $env:PLATFORMIO_SETTING_CHECK_PRUNE_SYSTEM_THRESHOLD = '0'
    $freeBefore = (Get-PSDrive C).Free
    $preflight = @'
from platformio.platform.factory import PlatformFactory
from platformio.package.manager.core import get_core_package_dir
from platformio.project.config import ProjectConfig
p = PlatformFactory.from_env('bringup', autoinstall=False)
missing = [n for n, o in p.packages.items() if not o.get('optional') and not p.get_package_dir(n)]
if not get_core_package_dir('tool-scons', auto_install=False): missing.append('tool-scons')
if ProjectConfig.get_instance().get('env:bringup', 'lib_deps', []): missing.append('unreviewed lib_deps')
if missing: raise SystemExit('Missing/unreviewed dependencies; installation requires approval: ' + ', '.join(missing))
print('Offline dependency preflight passed; all required packages already installed.')
'@
    & $python -B -c $preflight
    if ($LASTEXITCODE -ne 0) { throw 'Dependency preflight refused this build; nothing installed.' }
    # Existing package reuse only. No library downloads are required by this project.
    $ErrorActionPreference = 'Continue'
    & $python -B -m platformio run -e bringup -j $Jobs 2>&1 | Tee-Object -FilePath (Join-Path $run 'build.txt')
    $exit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($exit -ne 0) { throw "Build failed (exit $exit). See $run\build.txt" }
    $build = Join-Path $env:PLATFORMIO_WORKSPACE_DIR 'build\bringup'
    foreach ($name in @('firmware.bin', 'bootloader.bin', 'partitions.bin')) {
        Copy-Item -LiteralPath (Join-Path $build $name) -Destination (Join-Path $run $name)
    }
    Copy-Item -LiteralPath (Join-Path $packages 'framework-arduinoespressif32\tools\partitions\boot_app0.bin') -Destination (Join-Path $run 'boot_app0.bin')
    $firmware = Get-Item -LiteralPath (Join-Path $run 'firmware.bin')
    $slot = 0x640000
    if ($firmware.Length -gt $slot) { throw 'Firmware exceeds the OTA application slot.' }
    $files = @(Get-ChildItem -LiteralPath $run -File | ForEach-Object {
        [ordered]@{name=$_.Name; bytes=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    })
    $sourcePaths = @('platformio.ini') + @(Get-ChildItem include, src -File -Recurse | ForEach-Object { $_.FullName.Substring($root.Length + 1) })
    $sources = @($sourcePaths | ForEach-Object { [ordered]@{path=$_; sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()} })
    $version = [regex]::Match((Get-Content include\config.h -Raw), 'version\[\]\s*=\s*"([^"]+)"').Groups[1].Value
    [ordered]@{version=$version; utc=$stamp; platform='espressif32@6.12.0'; arduino='2.0.17'; flash_bytes=16777216; psram_enabled=$false; ota_slot_bytes=$slot; firmware_bytes=$firmware.Length; ota_headroom_bytes=($slot-$firmware.Length); free_bytes_before=$freeBefore; artifacts=$files; sources=$sources} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $run 'manifest.json') -Encoding UTF8
    @"
USB ONLY: bootloader.bin @ 0x0; partitions.bin @ 0x8000; boot_app0.bin @ 0xe000; firmware.bin @ 0x10000.
WEB OTA ONLY: firmware.bin. Never upload any other binary to /api/ota.
Slots: ota_0 @ 0x10000, ota_1 @ 0x650000; each 0x640000 bytes.
16 MB physical flash verified; layout matches the table read before flashing.
No credentials are compiled into these images. Provision NVS locally via device.py setup.
"@ | Set-Content -LiteralPath (Join-Path $run 'usage.txt') -Encoding UTF8
    Write-Output "Build artifact directory: $run"
    Write-Output "Application: $($firmware.Length) bytes / $slot bytes per OTA slot"
} finally {
    Pop-Location
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
    if (Test-Path -LiteralPath $scratch) {
        $size = (Get-ChildItem -LiteralPath $scratch -File -Recurse -Force | Measure-Object Length -Sum).Sum
        Remove-Item -LiteralPath $scratch -Recurse -Force
        Write-Output "Purged owned build scratch: $size bytes"
    }
}
