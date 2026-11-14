# Build a portable Windows folder (dist/LiveFloat/LiveFloat.exe) with PyInstaller.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path $python)) {
    Write-Error "没有找到 .venv，请先运行 start.bat 安装依赖。"
    exit 1
}

Write-Host "[1/3] 安装 PyInstaller ..."
& $python -m pip install --upgrade pyinstaller -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

Write-Host "[2/3] 打包（可能需要几分钟）..."
& $python -m PyInstaller `
    --noconfirm --clean --windowed `
    --name "LiveFloat" `
    --icon "assets\icon.ico" `
    --add-data "assets;assets" `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all onnxruntime `
    --collect-all soxr `
    --collect-all pyaudiowpatch `
    --collect-all sentencepiece `
    --hidden-import "app" `
    "run.py"

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/3] 完成：dist\LiveFloat\LiveFloat.exe"
