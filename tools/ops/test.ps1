$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$scratch = Join-Path $root ".opencode-tmp\tests-$stamp"
$run = Join-Path $root "analysis\gcc\tests-$stamp"
New-Item -ItemType Directory -Path $scratch | Out-Null
New-Item -ItemType Directory -Path $run | Out-Null
$oldPath = $env:PATH
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldTmpDir = $env:TMPDIR
Push-Location $root
try {
    $env:TEMP = $scratch; $env:TMP = $scratch; $env:TMPDIR = $scratch
    $compiler = Get-Command g++ -ErrorAction Stop
    $env:PATH = (Split-Path $compiler.Source -Parent) + ';' + $env:PATH
    $exe = Join-Path $scratch 'test-core.exe'
    & $compiler.Source -std=c++11 -Wall -Wextra -Werror -I include src/hlk_protocol.cpp src/wifi_scan.cpp src/selftest.cpp tests/test-core.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'C++ tests did not compile.' }
    & $exe | Tee-Object -FilePath (Join-Path $run 'tests.txt')
    if ($LASTEXITCODE -ne 0) { throw 'C++ tests failed.' }
    $ErrorActionPreference = 'Continue'
    $testCode = 'import sys, unittest; sys.stderr = sys.stdout; unittest.main(module=None, argv=[''unittest'', ''discover'', ''-s'', ''tests'', ''-p'', ''test_*.py''])'
    & (Join-Path $HOME '.platformio\penv\Scripts\python.exe') -B -c $testCode 2>&1 | Tee-Object -FilePath (Join-Path $run 'python-tests.txt')
    $exit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($exit -ne 0) { throw 'Python tests failed.' }
    Write-Output "Test results: $run"
} finally {
    Pop-Location
    $env:PATH = $oldPath; $env:TEMP = $oldTemp; $env:TMP = $oldTmp; $env:TMPDIR = $oldTmpDir
    if (Test-Path -LiteralPath $scratch) { Remove-Item -LiteralPath $scratch -Recurse -Force }
}
