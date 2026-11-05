$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'AIoT ESP32-S3 - Setup Wi-Fi lokal (jangan kirim password ke chat)'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$scratch = Join-Path $root ('.opencode-tmp\setup-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ'))
New-Item -ItemType Directory -Path $scratch | Out-Null
$previous = @{}
foreach ($name in @('TEMP', 'TMP', 'TMPDIR', 'PYTHONDONTWRITEBYTECODE')) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
Push-Location $root
$result = 1
try {
    $env:TEMP = $scratch; $env:TMP = $scratch; $env:TMPDIR = $scratch
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & (Join-Path $HOME '.platformio\penv\Scripts\python.exe') -B (Join-Path $PSScriptRoot 'device.py') setup
    $result = $LASTEXITCODE
    if ($result -ne 0) {
        Write-Host 'Setup belum selesai. Baca pesan ERROR di atas; jangan kirim password ke chat.'
        Write-Host 'USB tetap terpasang, adaptor jack tetap dilepas. Pesan error tidak boleh dianggap Wi-Fi/OTA berhasil.'
        Read-Host 'Tekan Enter untuk menutup; jalankan setup.ps1 lagi saat siap' | Out-Null
    }
} finally {
    Pop-Location
    foreach ($name in $previous.Keys) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
    if (Test-Path -LiteralPath $scratch) { Remove-Item -LiteralPath $scratch -Recurse -Force }
}
exit $result
