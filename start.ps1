# start.ps1 — Forion LiteLLM Proxy launcher (Windows)
# Replaces: poetry run litellm --config forion_config.yaml --port 4000
#
# Why PYTHONPATH?
#   litellm.exe (pip-installed CLI) resolves imports at runtime.
#   Setting PYTHONPATH to THIS directory forces Python to use the LOCAL
#   litellm source (with ForionCustomLogger hooks) instead of the pip copy.

Set-Location $PSScriptRoot

Write-Host "🔧 Setting PYTHONPATH to local litellm source..." -ForegroundColor Cyan
$env:PYTHONPATH = $PSScriptRoot

# Load environment variables from .env (skip comments and blank lines)
Write-Host "📦 Loading .env..." -ForegroundColor Cyan
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line -match "^([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $key   = $matches[1]
            $value = $matches[2]
            [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
    Write-Host "  ✅ NVIDIA_API_KEY loaded: $($env:NVIDIA_API_KEY -ne $null -and $env:NVIDIA_API_KEY -ne '')" -ForegroundColor Green
    Write-Host "  ✅ LITELLM_MASTER_KEY:   $($env:LITELLM_MASTER_KEY)" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  No .env file found" -ForegroundColor Yellow
}

Write-Host "✅ Using: python run_proxy.py (local litellm source with Forion hooks)" -ForegroundColor Green
Write-Host ""
Write-Host "🚀 Starting Forion LiteLLM Proxy on port 4000..." -ForegroundColor Magenta
Write-Host "   Config: forion_config.yaml" -ForegroundColor Gray
Write-Host "   Primary model: kimi-k2-instruct (NVIDIA NIM)" -ForegroundColor Gray
Write-Host ""

# Run via python directly — this respects PYTHONPATH and uses the local litellm
# source (with ForionCustomLogger) instead of the pip-installed copy.
python run_proxy.py --config forion_config.yaml --port 4000
