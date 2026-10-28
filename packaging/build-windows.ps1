$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Build the Windows package on Windows.' }
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne [System.Runtime.InteropServices.Architecture]::X64) {
    throw 'This release targets Windows x64; use a Windows x64 build machine.'
}
$repoDir = Split-Path -Parent $PSScriptRoot
Push-Location $repoDir
try {
    & py -3.13 -c 'import sys; assert sys.version_info[:2] == (3,13)'
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.13 with the Python launcher for the maintainer build.' }
    & py -3.13 -m venv .build\venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create build environment.' }
    & .\.build\venv\Scripts\python.exe -B packaging\prepare.py windows
    if ($LASTEXITCODE -ne 0) { throw 'Runtime/dependency preparation failed; no release produced.' }
    & .\.build\venv\Scripts\python.exe -B packaging\build_packages.py windows
    if ($LASTEXITCODE -ne 0) { throw 'Package build failed.' }
} finally {
    Pop-Location
}
