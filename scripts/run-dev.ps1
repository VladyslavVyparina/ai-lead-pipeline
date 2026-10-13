param(
    [ValidateSet("dev", "staging", "prod")]
    [string]$Environment = "dev"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command infisical -ErrorAction SilentlyContinue)) {
    throw "Infisical CLI is required. Install it, run 'infisical login', then 'infisical init' in this repository."
}

# Infisical injects only into this process. No secret is written to .env or Git.
& infisical run --env=$Environment -- py -3.10 run_api.py
exit $LASTEXITCODE
