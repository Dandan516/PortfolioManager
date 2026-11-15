param([string]$Distribution = 'Ubuntu')
$ErrorActionPreference = 'Stop'

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
	throw 'WSL is not installed. Install WSL2 first: wsl --install -d Ubuntu'
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$FullProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
if ($FullProjectRoot -notmatch '^([A-Za-z]):\\(.*)$') {
	throw "Unsupported project path for WSL: $FullProjectRoot"
}
$Drive = $Matches[1].ToLowerInvariant()
$PathRemainder = $Matches[2].Replace('\', '/')
$WslProjectRoot = "/mnt/$Drive/$PathRemainder"
$BashProjectRoot = "'" + $WslProjectRoot.Replace("'", "'\''") + "'"

function Invoke-Wsl {
	param([string[]]$Arguments)

	& wsl.exe -d $Distribution @Arguments
	if ($LASTEXITCODE -ne 0) {
		throw "WSL command failed for distribution '$Distribution': $($Arguments -join ' ')"
	}
}

Write-Host "Preparing the WSL environment in $Distribution..." -ForegroundColor Yellow
& wsl.exe -d $Distribution -- python3 -c 'import venv' 2>$null
$NeedsPythonVenv = $LASTEXITCODE -ne 0
& wsl.exe -d $Distribution -- bash -lc "dpkg-query -W libxcb-cursor0 >/dev/null 2>&1"
$NeedsXcbCursor = $LASTEXITCODE -ne 0
if ($NeedsPythonVenv -or $NeedsXcbCursor) {
	Invoke-Wsl -Arguments @('-u', 'root', '--', 'apt-get', 'update')
	$SystemPackages = @()
	if ($NeedsPythonVenv) {
		$SystemPackages += 'python3-venv'
	}
	if ($NeedsXcbCursor) {
		$SystemPackages += 'libxcb-cursor0'
	}
	Invoke-Wsl -Arguments (@('-u', 'root', '--', 'apt-get', 'install', '-y') + $SystemPackages)
}

$SetupCommand = "cd -- $BashProjectRoot && mkdir -p ~/.venvs && if [ ! -x ~/.venvs/portfolio-manager/bin/python ]; then python3 -m venv ~/.venvs/portfolio-manager; fi && ~/.venvs/portfolio-manager/bin/python -m pip install --upgrade pip && ~/.venvs/portfolio-manager/bin/python -m pip install -r requirements.txt"
Invoke-Wsl -Arguments @('--', 'bash', '-lc', $SetupCommand)

Write-Host 'WSL environment is ready.' -ForegroundColor Green
Write-Host 'Launch the application from PowerShell with:' -ForegroundColor Yellow
Write-Host 'python main.py'