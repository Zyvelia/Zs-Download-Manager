# Prints the first existing Inno Setup compiler path; does not search the whole disk.
$ErrorActionPreference = 'SilentlyContinue'
$candidates = @()
if ($env:ISCC_PATH) { $candidates += $env:ISCC_PATH.Trim('"') }
$command = Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($command) { $candidates += $command.Source }
foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, "$env:LOCALAPPDATA\Programs", $env:LOCALAPPDATA)) {
    if ($base) {
        foreach ($name in @('Inno Setup 6', 'Inno Setup 7')) {
            $candidates += (Join-Path $base "$name\ISCC.exe")
        }
    }
}
# An installation at a custom location normally appears in Add or Remove Programs.
$uninstallRoots = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
foreach ($entry in @(Get-ItemProperty $uninstallRoots | Where-Object { $_.DisplayName -match '^Inno Setup (6|7)(\D|$)' })) {
    if ($entry.InstallLocation) { $candidates += (Join-Path $entry.InstallLocation 'ISCC.exe') }
    foreach ($value in @($entry.DisplayIcon, $entry.UninstallString)) {
        if ($value -match '^\s*"([^"]+\.exe)"|^\s*([^,]+?\.exe)') {
            $exe = if ($Matches[1]) { $Matches[1] } else { $Matches[2] }
            $candidates += (Join-Path (Split-Path $exe -Parent) 'ISCC.exe')
        }
    }
}
foreach ($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe')) {
    $app = Get-Item $key
    if ($app) { $candidates += $app.GetValue('') }
}
foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        (Resolve-Path -LiteralPath $candidate).Path
        exit 0
    }
}
exit 1
