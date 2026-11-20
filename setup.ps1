<#
.SYNOPSIS
    Zero-manual-setup launcher for J.A.R.V.I.S. on Windows.
    Installs Python dependencies, installs Ollama if missing, enables Intel Arc/iGPU
    Vulkan acceleration automatically when detected, pulls the local model,
    and launches the J.A.R.V.I.S. Web HUD (or voice-only mode with -VoiceOnly).
#>
param(
    [switch]$VoiceOnly
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Write-Step([string]$msg) {
    Write-Host "`n[J.A.R.V.I.S.] $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg) {
    Write-Host "  OK: $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "  WARN: $msg" -ForegroundColor Yellow
}

# 1. Locate Python 3
Write-Step "Checking Python installation..."
$pyCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pyCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pyCmd = "py"
}

if (-not $pyCmd) {
    Write-Warn "Python 3 not found. Attempting install via WinGet..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        if (Get-Command python -ErrorAction SilentlyContinue) { $pyCmd = "python" }
        elseif (Get-Command py -ErrorAction SilentlyContinue) { $pyCmd = "py" }
    }
}

if (-not $pyCmd) {
    Write-Host "  ERROR: Python 3 is required. Install it from https://www.python.org/downloads/ and re-run start.bat." -ForegroundColor Red
    exit 1
}
Write-Ok "Using Python command: $pyCmd"

# 2. Create/reuse virtual environment & install requirements
$venvDir = Join-Path $PSScriptRoot ".venv"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
$reqFile = if (Test-Path (Join-Path $PSScriptRoot "requirements-desktop.txt")) { Join-Path $PSScriptRoot "requirements-desktop.txt" } else { Join-Path $PSScriptRoot "requirements.txt" }
$stampFile = Join-Path $venvDir ".deps_hash"

if (-not (Test-Path $venvPy)) {
    Write-Step "Creating Python virtual environment (.venv)..."
    if ($pyCmd -eq "py") { & py -3 -m venv $venvDir } else { & python -m venv $venvDir }
}

if (Test-Path $reqFile) {
    $reqHash = (Get-FileHash $reqFile -Algorithm SHA256).Hash
    $savedHash = if (Test-Path $stampFile) { (Get-Content $stampFile -Raw).Trim() } else { "" }
    if ($reqHash -ne $savedHash) {
        Write-Step "Installing Python dependencies from requirements.txt..."
        & $venvPy -m pip install --upgrade pip --quiet
        & $venvPy -m pip install -r $reqFile
        Set-Content -Path $stampFile -Value $reqHash -NoNewline
        Write-Ok "Dependencies installed."
    } else {
        Write-Ok "Python dependencies already up to date."
    }
}

# 3. Ensure .env exists
$envFile = Join-Path $PSScriptRoot ".env"
$envExample = Join-Path $PSScriptRoot ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Ok "Created .env from .env.example."
}

# Read OLLAMA_MODEL from .env (default llama3.2:3b)
$ollamaModel = "llama3.2:3b"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*OLLAMA_MODEL\s*=\s*(.+?)\s*$') {
            $val = $Matches[1].Trim('"', "'", ' ')
            if ($val) { $ollamaModel = $val }
        }
    }
}

# 4. Auto-enable Ollama Vulkan + iGPU acceleration on Intel Arc / Intel GPU machines (without NVIDIA)
try {
    $gpus = (Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue).Name -join " | "
    if ($gpus -match "Intel" -and $gpus -notmatch "NVIDIA") {
        $env:OLLAMA_VULKAN = "1"
        $env:OLLAMA_IGPU_ENABLE = "1"
        if ([Environment]::GetEnvironmentVariable("OLLAMA_VULKAN", "User") -ne "1") {
            [Environment]::SetEnvironmentVariable("OLLAMA_VULKAN", "1", "User")
        }
        if ([Environment]::GetEnvironmentVariable("OLLAMA_IGPU_ENABLE", "User") -ne "1") {
            [Environment]::SetEnvironmentVariable("OLLAMA_IGPU_ENABLE", "1", "User")
        }
        Write-Ok "Intel GPU detected ($gpus) — enabled Ollama Vulkan GPU acceleration."
    }
} catch {}

# 5. Auto-install Ollama if not present
function Find-OllamaExe {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $localExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $localExe) { return $localExe }
    return $null
}

Write-Step "Checking Ollama local AI runtime..."
$ollamaExe = Find-OllamaExe
if (-not $ollamaExe) {
    Write-Warn "Ollama not found. Installing Ollama for Windows automatically..."
    try {
        Invoke-Expression (Invoke-RestMethod -Uri "https://ollama.com/install.ps1")
    } catch {
        Write-Warn "PowerShell installer failed ($($_.Exception.Message)). Trying WinGet..."
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
        }
    }
    $ollamaDir = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
    if (Test-Path $ollamaDir) { $env:Path += ";$ollamaDir" }
    $ollamaExe = Find-OllamaExe
}

if ($ollamaExe) {
    Write-Ok "Ollama ready: $ollamaExe"

    # 6. Start Ollama server if not already listening
    $ollamaUp = $false
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
        $ollamaUp = $true
    } catch {
        Write-Step "Starting Ollama background service..."
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 1
            try {
                $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
                $ollamaUp = $true
                break
            } catch {}
        }
    }

    if ($ollamaUp) {
        # Check if model is already pulled
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
        $installed = @()
        if ($tags -and $tags.models) {
            $installed = $tags.models | ForEach-Object { $_.name }
        }
        $hasModel = $false
        foreach ($m in $installed) {
            if ($m -eq $ollamaModel -or $m -like "$ollamaModel`:*") {
                $hasModel = $true
                break
            }
        }
        if (-not $hasModel) {
            Write-Step "Downloading local AI model '$ollamaModel' (one-time download)..."
            & $ollamaExe pull $ollamaModel
        } else {
            Write-Ok "Local AI model '$ollamaModel' is already installed."
        }
    } else {
        Write-Warn "Ollama did not start in time; Jarvis will fall back to Gemini if configured."
    }
} else {
    Write-Warn "Could not install Ollama automatically. Jarvis will still launch using Gemini/backup AI."
}

# 7. Launch Jarvis
if ($VoiceOnly) {
    Write-Step "Launching J.A.R.V.I.S. Voice Mode (main.py)..."
    & $venvPy (Join-Path $PSScriptRoot "main.py")
} else {
    Write-Step "Launching J.A.R.V.I.S. Touch Web HUD (server.py)..."
    & $venvPy (Join-Path $PSScriptRoot "server.py")
}
