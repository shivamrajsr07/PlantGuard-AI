$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendUrl = "http://127.0.0.1:8000/health"

function Test-Backend {
    try {
        $response = Invoke-RestMethod -Uri $backendUrl -TimeoutSec 2
        return $response.status -eq "ok"
    }
    catch {
        return $false
    }
}

if (-not (Test-Backend)) {
    $backendLog = Join-Path $root "backend.log"
    $backendErr = Join-Path $root "backend.err.log"
    Start-Process `
        -FilePath "python" `
        -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $root `
        -RedirectStandardOutput $backendLog `
        -RedirectStandardError $backendErr `
        -WindowStyle Hidden

    $ready = $false
    foreach ($attempt in 1..30) {
        Start-Sleep -Milliseconds 500
        if (Test-Backend) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        Write-Error "Backend did not become ready at $backendUrl. Check backend.err.log."
    }
}

npm --prefix (Join-Path $root "frontend") run dev -- --host 127.0.0.1 --port 5173 --open
