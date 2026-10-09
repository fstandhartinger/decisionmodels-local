param([Parameter(ValueFromRemainingArguments = $true)][string[]]$RemainingArgs)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Repo = 'https://github.com/fstandhartinger/decisionmodels-local'
if ($env:DM_LOCAL_VERSION) {
  $Version = $env:DM_LOCAL_VERSION
  if (-not $Version.StartsWith('v')) { $Version = "v$Version" }
  $Release = "$Repo/releases/download/$Version"
} else {
  $Release = "$Repo/releases/latest/download"
}
$Temp = Join-Path ([IO.Path]::GetTempPath()) ("dm-local-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Temp | Out-Null
$Bin = Join-Path $env:LOCALAPPDATA 'DecisionModels\bin'
$Lib = Join-Path $env:LOCALAPPDATA 'DecisionModels\lib'
New-Item -ItemType Directory -Force -Path $Bin,$Lib | Out-Null
function Download($Url, $Path) { $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Path }
function Get-PinnedHash($SumFile, $Name) {
  $Line = Get-Content $SumFile | Where-Object { $_ -match ("\s\*?" + [regex]::Escape($Name) + '$') } | Select-Object -First 1
  if (-not $Line) { throw "Missing checksum for $Name." }
  return (($Line -split '\s+')[0])
}
function Verify-Hash($Path, $Expected) {
  $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
  if ($Actual -ne $Expected.ToLowerInvariant()) { throw "SHA-256 verification failed for $([IO.Path]::GetFileName($Path))." }
}
try {
  $Sums = Join-Path $Temp 'SHA256SUMS'
  $SumBundle = Join-Path $Temp 'SHA256SUMS.sigstore.json'
  Download "$Release/SHA256SUMS" $Sums
  Download "$Release/SHA256SUMS.sigstore.json" $SumBundle
  $Cosign = Get-Command cosign -ErrorAction SilentlyContinue
  if ($Cosign) { $CosignPath = $Cosign.Source }
  else {
    $CosignPath = Join-Path $Temp 'cosign.exe'
    Download 'https://github.com/sigstore/cosign/releases/download/v3.0.6/cosign-windows-amd64.exe' $CosignPath
    Verify-Hash $CosignPath '9b85a88ebff2d9dd30ff4984a6f61f2cedc232dd87d81fa7f2ff3c0ed96c241c'
  }
  & $CosignPath verify-blob --bundle $SumBundle --certificate-identity-regexp '^https://github.com/fstandhartinger/decisionmodels-local/\.github/workflows/release\.yml@refs/tags/v[0-9][^/]*$' --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' $Sums
  if ($LASTEXITCODE -ne 0) { throw 'Release manifest signature verification failed.' }
  $Pins = Join-Path $Temp 'pins.py'
  Download "$Release/pins.py" $Pins
  Verify-Hash $Pins (Get-PinnedHash $Sums 'pins.py')
  $PinText = Get-Content -Raw $Pins
  $UvVersion = [regex]::Match($PinText, 'UV_VERSION = "([^\"]+)"').Groups[1].Value
  $UvRelease = [regex]::Match($PinText, 'UV_RELEASE = "([^\"]+)"').Groups[1].Value
  if (-not $UvVersion -or -not $UvRelease) { throw 'Release does not contain uv pin metadata.' }

  $Python = $null
  foreach ($Probe in @('py','python','python3')) {
    try {
      if ($Probe -eq 'py') { & py -3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)' *> $null; $Prefix = @('-3') }
      else { & $Probe -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)' *> $null; $Prefix = @() }
      if ($LASTEXITCODE -eq 0) { $Python = @{ Exe = $Probe; Prefix = $Prefix }; break }
    } catch {}
  }
  if (-not $Python) {
    $Arch = if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq 'Arm64') { 'aarch64' } else { 'x86_64' }
    $UvFile = "uv-$Arch-pc-windows-msvc.zip"
    $UvKey = "$Arch-pc-windows-msvc"
    $UvPattern = '"' + [regex]::Escape($UvKey) + '"\s*:\s*\{\s*"file":\s*"[^"]+"\s*,\s*"sha256":\s*"([0-9a-f]{64})"'
    $UvHash = [regex]::Match($PinText, $UvPattern, [Text.RegularExpressions.RegexOptions]::Singleline).Groups[1].Value
    if (-not $UvHash) { throw "No uv pin for $UvKey." }
    $UvZip = Join-Path $Temp $UvFile
    Download "$UvRelease/$UvFile" $UvZip
    Verify-Hash $UvZip $UvHash
    Expand-Archive -LiteralPath $UvZip -DestinationPath (Join-Path $Temp 'uv') -Force
    $UvExe = Get-ChildItem -Path (Join-Path $Temp 'uv') -Filter 'uv.exe' -Recurse | Select-Object -First 1
    if (-not $UvExe) { throw 'Verified uv archive did not contain uv.exe.' }
    Copy-Item -LiteralPath $UvExe.FullName -Destination (Join-Path $Bin 'uv.exe') -Force
    & (Join-Path $Bin 'uv.exe') python install 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the pinned Python runtime with uv.' }
    $ManagedPython = & (Join-Path $Bin 'uv.exe') python find 3.12
    if ($LASTEXITCODE -ne 0 -or -not $ManagedPython) { throw 'Could not locate the installed Python runtime.' }
    $Python = @{ Exe = ([string]$ManagedPython).Trim(); Prefix = @() }
  }

  $PyZ = Join-Path $Temp 'dm-local.pyz'
  Download "$Release/dm-local.pyz" $PyZ
  Verify-Hash $PyZ (Get-PinnedHash $Sums 'dm-local.pyz')
  Copy-Item -LiteralPath $PyZ -Destination (Join-Path $Lib 'dm-local.pyz') -Force
  $PyzPath = Join-Path $Lib 'dm-local.pyz'
  $Cmd = Join-Path $Bin 'dm-local.cmd'
  $PyCommand = if ($Python.Exe -eq 'py') { 'py -3' } else { '"' + $Python.Exe + '"' }
  # Keep the success/failure exit on this same physical line: uninstall may delete
  # this batch file while Python runs, so cmd must not reopen it afterwards.
  @('@echo off', "$PyCommand `"%LOCALAPPDATA%\DecisionModels\lib\dm-local.pyz`" %* && exit /b 0 || exit /b 1") | Set-Content -Encoding ASCII $Cmd
  # Make the one-command install usable now and in future user terminals.
  $UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (($UserPath -split ';') -notcontains $Bin) {
    $UpdatedPath = if ($UserPath) { "$UserPath;$Bin" } else { $Bin }
    [Environment]::SetEnvironmentVariable('Path', $UpdatedPath, 'User')
  }
  if (($env:Path -split ';') -notcontains $Bin) { $env:Path = "$Bin;$env:Path" }
  Write-Host "Installed dm-local at $Cmd"
  Write-Host 'Next: dm-local doctor; dm-local list'
  Write-Host 'vLLM/SGLang variants need WSL2 and a current NVIDIA Windows driver. In an elevated PowerShell, run: wsl --install -d Ubuntu; then restart Windows, run wsl --update, and install the NVIDIA CUDA driver for WSL.'
  Write-Host 'llama.cpp variants run natively when a verified platform binary is available.'
  if ($RemainingArgs) { & $Cmd @RemainingArgs; if ($LASTEXITCODE -ne 0) { throw 'dm-local command failed.' } }
} finally {
  Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
}
