# Desktop bundle smoke test for Windows (execution plan Phase 4, Gate 4).
#
# Usage (from the workflow, after NSIS install and registry lookup):
#   pwsh/powershell -File scripts/smoke_desktop.ps1 -Exe <persona-forge-desktop.exe> `
#     -SmokeJson <out-path>
#
# Runs the installed exe in smoke mode against a fresh PERSONA_FORGE_HOME
# (set by the caller), asserts the smoke JSON reports ok, then runs it with
# --bogus and asserts exit code 2. Fails closed: prints the smoke JSON on every
# outcome, and never leaves a server behind (final Win32_Process scan must find
# no persona_forge.app:app).
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$SmokeJson
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Exe)) {
    throw "FAIL: exe is missing: $Exe"
}
if (-not $env:PERSONA_FORGE_HOME) {
    throw "FAIL: PERSONA_FORGE_HOME must be set to a fresh state dir before calling"
}

function Assert-NoServerLeftBehind {
    $left = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'persona_forge\.app:app' }
    if ($left) {
        throw "FAIL: a persona_forge.app:app server process survived the smoke run"
    }
}

try {
    Write-Host "--- smoke run: --smoke-test $SmokeJson"
    $p = Start-Process -FilePath $Exe -ArgumentList '--smoke-test', $SmokeJson -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Write-Host "FAIL: --smoke-test exited with $($p.ExitCode); server/bootstrap logs:"
        Get-ChildItem (Join-Path $env:PERSONA_FORGE_HOME 'desktop\logs') -Filter '*.log' -ErrorAction SilentlyContinue |
            ForEach-Object {
                Write-Host "===== $($_.Name) ====="
                Get-Content -LiteralPath $_.FullName -Tail 120 | Write-Host
            }
        throw "FAIL: --smoke-test exited with $($p.ExitCode)"
    }

    Write-Host "--- smoke JSON:"
    Get-Content -LiteralPath $SmokeJson | Write-Host
    $report = Get-Content -LiteralPath $SmokeJson -Raw | ConvertFrom-Json
    if ($report.ok -ne $true) {
        throw "FAIL: smoke report did not report ok"
    }

    Write-Host "--- smoke run: --bogus (must exit 2)"
    $p = Start-Process -FilePath $Exe -ArgumentList '--bogus' -Wait -PassThru
    if ($p.ExitCode -ne 2) {
        throw "FAIL: --bogus exited with $($p.ExitCode), expected 2"
    }

    Write-Host "PASS: smoke (windows)"
}
finally {
    try { Assert-NoServerLeftBehind } catch { Write-Host $_.Exception.Message; exit 1 }
}
