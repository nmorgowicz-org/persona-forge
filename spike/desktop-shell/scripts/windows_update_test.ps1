# Spike 1B task 4: automated Windows update N -> N+1 on self-hosted-windows (no secrets).
# usage: windows_update_test.ps1 -Setup <0.1.0 setup.exe> -OutJson <path>
# Silent-installs N per-user, runs it with --ci-update, expects out.json phase "installing"
# (Tauri exits the app during a Windows install; contract §6.12), then waits for the uninstall
# registry entry's DisplayVersion to become 0.1.1. Always stops the app and uninstalls.
param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [Parameter(Mandatory = $true)][string]$OutJson
)
$ErrorActionPreference = 'Stop'
$Name = 'desktop-spike'
$UninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'

function Get-Entry {
    Get-ChildItem $UninstallKey -ErrorAction SilentlyContinue |
        ForEach-Object { Get-ItemProperty $_.PSPath } |
        Where-Object { $_.DisplayName -eq $Name } |
        Select-Object -First 1
}

function Get-InstalledExe($entry) {
    if ($entry.InstallLocation) {
        return Join-Path $entry.InstallLocation.Trim('"') "$Name.exe"
    }
    if ($entry.DisplayIcon) {
        # DisplayIcon is '"C:\...\desktop-spike.exe"' or 'C:\...\desktop-spike.exe,0'
        return ($entry.DisplayIcon -replace ',\d+$', '').Trim('"')
    }
    throw 'uninstall entry has neither InstallLocation nor DisplayIcon'
}

function Uninstall-Spike {
    $entry = Get-Entry
    if ($entry -and $entry.UninstallString) {
        $uninstaller = ($entry.UninstallString -replace '\s*/.*$', '').Trim('"')
        Start-Process -FilePath $uninstaller -ArgumentList '/S' -Wait | Out-Null
    }
}

try {
    Uninstall-Spike   # clean slate if an earlier run left one behind

    $p = Start-Process -FilePath $Setup -ArgumentList '/S' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "silent install exited $($p.ExitCode)" }
    $entry = Get-Entry
    if (-not $entry) { throw 'no uninstall entry after the silent install' }
    Write-Host "installed $($entry.DisplayVersion) at $($entry.InstallLocation)"
    if ($entry.DisplayVersion -ne '0.1.0') { throw "expected DisplayVersion 0.1.0, got $($entry.DisplayVersion)" }

    $exe = Get-InstalledExe $entry
    if (-not (Test-Path $exe)) { throw "installed exe not found: $exe" }
    if (Test-Path $OutJson) { Remove-Item $OutJson }

    # a GUI-subsystem exe does not block PowerShell unless started with -Wait
    $ci = Start-Process -FilePath $exe -ArgumentList @('--ci-update', $OutJson) -Wait -PassThru
    Write-Host "--ci-update exit code: $($ci.ExitCode)"
    if (-not (Test-Path $OutJson)) { throw 'out.json was not written' }
    $raw = Get-Content $OutJson -Raw
    Write-Host "out.json: $raw"
    $j = $raw | ConvertFrom-Json
    if ($j.phase -ne 'installing') { throw "expected phase 'installing', got '$($j.phase)' (error: $($j.error))" }

    $deadline = (Get-Date).AddSeconds(120)
    do {
        Start-Sleep -Seconds 2
        $version = (Get-Entry).DisplayVersion
    } until ($version -eq '0.1.1' -or (Get-Date) -gt $deadline)
    if ($version -ne '0.1.1') { throw "DisplayVersion is '$version' after 120 s (expected 0.1.1)" }
    Write-Host 'PASS: updated to 0.1.1 (registry DisplayVersion)'
}
finally {
    # Cleanup must never fail the job: the relaunched app runs in the interactive
    # session and NetworkService cannot kill it (access denied, PS 5.1 turns the
    # taskkill stderr into a terminating error under Stop).
    $ErrorActionPreference = 'Continue'
    Get-Process -Name $Name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    # taskkill failing leaves $LASTEXITCODE=1 and the runner's PowerShell wrapper
    # propagates it as the job exit code, even when the test passed
    taskkill /IM "$Name.exe" /F 2>$null | Out-Null
    Uninstall-Spike
}
exit 0
