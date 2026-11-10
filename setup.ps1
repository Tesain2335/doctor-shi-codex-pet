[CmdletBinding()]
param(
    [switch]$RegisterStartup,
    [switch]$NoShortcut
)

$ErrorActionPreference = 'Stop'
$uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue
if (-not $uv) {
    throw 'Install uv and reopen PowerShell before running setup.'
}

$runtime = Join-Path $PSScriptRoot 'runtime'
$runtimePython = Join-Path $runtime 'Scripts/python.exe'
$requirements = Join-Path $PSScriptRoot 'requirements.txt'
$launcher = Join-Path $PSScriptRoot 'launch.py'
$icon = Join-Path $PSScriptRoot 'assets/doctor-shortcut.ico'

& $uv.Source venv --managed-python --python 3.13 --allow-existing $runtime
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare the Python runtime.' }

& $uv.Source pip install --python $runtimePython -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Failed to install the desktop pet dependencies.' }

if (-not $NoShortcut) {
    $runtimeConfig = Get-Content -LiteralPath (Join-Path $runtime 'pyvenv.cfg') -Encoding UTF8
    $homeLine = $runtimeConfig | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
    if (-not $homeLine) { throw 'The Windows Python runtime location was not found.' }
    $basePythonw = Join-Path (($homeLine -replace '^home\s*=\s*', '').Trim()) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $basePythonw -PathType Leaf)) {
        throw 'The Windows Python launcher was not found.'
    }

    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    $shortcutPath = Join-Path $desktop 'Doctor-shi.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $basePythonw
    $shortcut.Arguments = '"' + $launcher + '"'
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.IconLocation = "$icon,0"
    $shortcut.Description = 'Start the Doctor-shi desktop pet'
    $shortcut.Save()
    Write-Output "Desktop shortcut: $shortcutPath"
}

if ($RegisterStartup) {
    & $runtimePython (Join-Path $PSScriptRoot 'install.py')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to register or start the sign-in task.' }
}
