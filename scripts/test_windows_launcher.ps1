# Native regression: evaluate the EXACT installer template, not a similar batch.
$ErrorActionPreference = 'Stop'
$source = Get-Content (Join-Path $PSScriptRoot '../install/install.ps1') -Raw
$template = @($source -split "`n" | Where-Object { $_ -match 'Set-Content -Encoding ASCII \$Cmd' })
if ($template.Count -ne 1) { throw 'Expected one launcher template.' }
$originalLocalAppData = $env:LOCALAPPDATA
function Invoke-NativeCmd([string]$commandLine) {
  # Pass CMD's command line verbatim; PowerShell 5.1 native marshalling rewrites
  # embedded quotes in /c strings containing metacharacters.
  $start = New-Object System.Diagnostics.ProcessStartInfo
  $start.FileName = $env:ComSpec
  $start.Arguments = $commandLine
  $start.UseShellExecute = $false
  $process = [System.Diagnostics.Process]::Start($start)
  $process.WaitForExit()
  $code = $process.ExitCode
  $process.Dispose()
  return $code
}
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('dm-launcher ! space-' + [guid]::NewGuid().ToString('N'))
try {
  $env:LOCALAPPDATA = $testRoot
  $PyCommand = '"' + (Get-Command python).Source + '"'
  foreach ($expected in @(0, 37)) {
    foreach ($delete in @($false, $true)) {
      foreach ($mode in @('powershell', 'cmd', 'call')) {
        $appRoot = Join-Path $testRoot 'DecisionModels'
        New-Item -ItemType Directory -Force (Join-Path $appRoot 'bin'),(Join-Path $appRoot 'lib') | Out-Null
        $Cmd = Join-Path $appRoot 'bin/dm-local.cmd'
        $pyz = Join-Path $appRoot 'lib/dm-local.pyz'
        $receipt = Join-Path $testRoot 'argv.json'
        $argument = Join-Path $testRoot 'quoted ! argument & (literal).txt'
        @(
          'import json,pathlib,shutil,sys',
          'root = pathlib.Path(__file__).parent.parent',
          'pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]), encoding="utf-8")',
          'if sys.argv[3] == "True": shutil.rmtree(root)',
          'raise SystemExit(int(sys.argv[4]))'
        ) | Set-Content -Encoding ASCII $pyz
        Invoke-Expression $template[0]
        $deleteText = [string]$delete
        if ($mode -eq 'powershell') {
          & $Cmd $receipt $argument $deleteText $expected
          $actual = $LASTEXITCODE
        } elseif ($mode -eq 'cmd') {
          $actual = Invoke-NativeCmd "/d /v:off /s /c `"`"$Cmd`" `"$receipt`" `"$argument`" $deleteText $expected`""
        } else {
          # CALL must return to its caller and leave the caller's environment alone.
          $caller = Join-Path $testRoot 'caller.cmd'
          @(
            '@echo off',
            'set "DM_LAUNCHER_CALLER=still-present"',
            "call `"$Cmd`" `"$receipt`" `"$argument`" $deleteText $expected",
            'set "result=%errorlevel%"',
            'if not "%DM_LAUNCHER_CALLER%"=="still-present" exit /b 99',
            "echo returned> `"$(Join-Path $testRoot 'returned.txt')`"",
            'exit /b %result%'
          ) | Set-Content -Encoding ASCII $caller
          $actual = Invoke-NativeCmd "/d /v:off /s /c `"`"$caller`"`""
        }
        if ($actual -ne $expected) { throw "$mode delete=$delete returned $actual, expected $expected" }
        # Windows PowerShell 5.1 emits the JSON array as one pipeline object.
        # Assign it directly; @(...pipeline...) would create a nested array.
        $arguments = Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
        if ($arguments.Count -ne 3 -or $arguments[0] -cne $argument -or $arguments[1] -cne $deleteText -or $arguments[2] -cne [string]$expected) {
          throw "Launcher changed arguments: $(Get-Content -LiteralPath $receipt -Raw)"
        }
        if ($delete -and (Test-Path -LiteralPath $appRoot)) { throw 'Synchronous deletion left installer state.' }
        if ($mode -eq 'call') {
          $returned = Join-Path $testRoot 'returned.txt'
          if (-not (Test-Path -LiteralPath $returned)) { throw 'Launcher did not return to caller.' }
          Remove-Item -LiteralPath $returned
        }
        Write-Host "PASS $mode delete=$delete exit=$expected; arguments intact"
        Remove-Item -LiteralPath $receipt
        if (Test-Path -LiteralPath $appRoot) { Remove-Item -LiteralPath $appRoot -Recurse -Force }
      }
    }
  }
} finally {
  $env:LOCALAPPDATA = $originalLocalAppData
  if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
}
