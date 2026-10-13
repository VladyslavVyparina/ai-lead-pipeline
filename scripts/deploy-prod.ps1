param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command infisical -ErrorAction SilentlyContinue)) {
    throw "Infisical CLI is required on the deployment host."
}

$composeArgs = @("compose", "-f", "docker-compose.prod.yml", "up", "-d")
if ($Build) { $composeArgs += "--build" }

# The CLI injects prod secrets into Docker Compose for interpolation. Containers
# receive only the application variables, not an Infisical access token.
& infisical run --env=prod -- docker @composeArgs
exit $LASTEXITCODE
