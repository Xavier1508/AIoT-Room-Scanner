param(
    [string]$HostAddress = '127.0.0.1',
    [int]$Port = 8001
)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$python = Join-Path $HOME '.platformio\penv\Scripts\python.exe'
$server = Join-Path $root 'tools\mapping\mapping_server.py'
if (!(Test-Path -LiteralPath $python)) { throw "PlatformIO Python not found: $python" }
if (!(Test-Path -LiteralPath $server)) { throw "Mapping server not found: $server" }
Write-Output "Mapping supervisor: http://${HostAddress}:$Port/"
Write-Output "Keep this window open. The server restarts automatically if it exits."
while ($true) {
    try {
        & $python -B $server --host $HostAddress --port $Port
    } catch {
        Write-Output ("Mapping server exited: " + $_.Exception.Message)
    }
    Start-Sleep -Seconds 3
}
