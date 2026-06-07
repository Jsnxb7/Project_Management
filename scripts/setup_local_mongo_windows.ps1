<#
One-time local MongoDB setup for AI PeopleOps HRMS on Windows.
Run from the project root:

    powershell -ExecutionPolicy Bypass -File scripts\setup_local_mongo_windows.ps1

What it does:
- Checks that mongod is installed and available.
- Creates local data/log folders.
- Starts a local mongod process on 127.0.0.1:27017 when one is not already running.
- Creates/updates .env with local Mongo defaults.
- Runs the Python Mongo health/index check.
#>

param(
    [string]$MongoPort = "27017",
    [string]$DatabaseName = "ai_hrms_local"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DataDir = Join-Path $ProjectRoot "data\mongo"
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "mongod.log"
$EnvFile = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"
$MongoUri = "mongodb://127.0.0.1:$MongoPort"

Write-Host "AI PeopleOps HRMS - one-time local MongoDB setup" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$MongodCmd = Get-Command mongod -ErrorAction SilentlyContinue
if (-not $MongodCmd) {
    $CommonPaths = @(
        "C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe",
        "C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe",
        "C:\Program Files\MongoDB\Server\6.0\bin\mongod.exe"
    )
    foreach ($Path in $CommonPaths) {
        if (Test-Path $Path) {
            $MongodCmd = @{ Source = $Path }
            break
        }
    }
}

if (-not $MongodCmd) {
    Write-Host "mongod was not found." -ForegroundColor Red
    Write-Host "Install MongoDB Community Server, then run this script again."
    Write-Host "Recommended installer: MongoDB Community Server for Windows."
    exit 1
}

$MongodPath = $MongodCmd.Source
Write-Host "mongod: $MongodPath"

$MongoRunning = $false
try {
    python -c "from pymongo import MongoClient; MongoClient('$MongoUri', serverSelectionTimeoutMS=2000).admin.command('ping')" | Out-Null
    $MongoRunning = $true
} catch {
    $MongoRunning = $false
}

if (-not $MongoRunning) {
    Write-Host "Starting local MongoDB on $MongoUri ..." -ForegroundColor Yellow
    Start-Process -FilePath $MongodPath -ArgumentList @(
        "--dbpath", $DataDir,
        "--bind_ip", "127.0.0.1",
        "--port", $MongoPort,
        "--logpath", $LogFile,
        "--logappend"
    ) -WindowStyle Minimized
    Start-Sleep -Seconds 4
} else {
    Write-Host "MongoDB is already running on $MongoUri" -ForegroundColor Green
}

if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
    } else {
        New-Item -ItemType File -Path $EnvFile | Out-Null
    }
}

$EnvText = Get-Content $EnvFile -Raw
if ($EnvText -match "(?m)^MONGO_URI=") {
    $EnvText = $EnvText -replace "(?m)^MONGO_URI=.*$", "MONGO_URI=$MongoUri"
} else {
    $EnvText += "`nMONGO_URI=$MongoUri"
}
if ($EnvText -match "(?m)^DB_NAME=") {
    $EnvText = $EnvText -replace "(?m)^DB_NAME=.*$", "DB_NAME=$DatabaseName"
} else {
    $EnvText += "`nDB_NAME=$DatabaseName"
}
Set-Content -Path $EnvFile -Value $EnvText -Encoding UTF8

Write-Host "Checking MongoDB and creating indexes ..." -ForegroundColor Yellow
python (Join-Path $ProjectRoot "scripts\check_local_mongo.py")

Write-Host "" 
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next commands:"
Write-Host "  .\.venv\Scripts\activate"
Write-Host "  python app.py"
Write-Host "Then open http://127.0.0.1:5000"
