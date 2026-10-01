$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvActivate = Join-Path $ProjectRoot 'venv\Scripts\Activate.ps1'
if (-not (Test-Path $VenvActivate)) {
	python -m venv venv
}

. $VenvActivate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt