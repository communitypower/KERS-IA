$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentScript = Join-Path $projectRoot "kers_deepchat_acp.py"

function Test-PythonCandidate {
    param([string]$Candidate)

    if (-not $Candidate) {
        return $false
    }

    if (-not (Test-Path $Candidate)) {
        return $false
    }

    try {
        & $Candidate -c "import sys" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

$pythonCandidates = @(
    (Join-Path $projectRoot ".venv\\Scripts\\python.exe"),
    (Join-Path $projectRoot "venv\\Scripts\\python.exe")
)

foreach ($candidate in $pythonCandidates) {
    if (Test-PythonCandidate $candidate) {
        & $candidate $agentScript
        exit $LASTEXITCODE
    }
}

$pyCommand = Get-Command py -ErrorAction SilentlyContinue
if ($pyCommand -and $pyCommand.Source -notlike "*WindowsApps*") {
    & $pyCommand.Source -3 $agentScript
    exit $LASTEXITCODE
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand -and $pythonCommand.Source -notlike "*WindowsApps*") {
    & $pythonCommand.Source $agentScript
    exit $LASTEXITCODE
}

Write-Error "Nenhum interpretador Python valido foi encontrado para iniciar o agente ACP da KERS. Recrie a .venv com um Python real ou ajuste o comando do DeepChat."
exit 1
