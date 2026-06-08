# build-docker.ps1
# Builds the NCA SmPC & OD Portal Docker image from the project root.
# Usage:
#   .\build-docker.ps1                  # builds with default tag
#   .\build-docker.ps1 -Tag "v1.2"      # builds with a specific version tag
#   .\build-docker.ps1 -Push            # builds and pushes to registry
#   .\build-docker.ps1 -Tag "v1.2" -Push

param(
    [string]$Tag = "latest",
    [switch]$Push
)

$ErrorActionPreference = "Stop"

$REGISTRY   = "ncasmpcapp.azurecr.io"
$IMAGE_NAME = "$REGISTRY/nca-smpc-app"
$FULL_TAG   = "${IMAGE_NAME}:${Tag}"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  NCA SmPC & OD Portal - Docker Build"  -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Registry : $REGISTRY"
Write-Host "  Image    : $FULL_TAG"
Write-Host "  Push     : $Push"
Write-Host ""

# --- Verify Docker is running --------------------------------
if (-not (docker info 2>$null)) {
    Write-Host "ERROR: Docker is not running or not installed." -ForegroundColor Red
    exit 1
}

# --- Verify .env exists (needed for collectstatic during build) --
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "WARNING: No .env file found. Copying .env.example as a build-time placeholder." -ForegroundColor Yellow
    Copy-Item (Join-Path $PSScriptRoot ".env.example") $envFile
    $cleanupEnv = $true
} else {
    $cleanupEnv = $false
}

# --- Build ---------------------------------------------------
Write-Host "Building image..." -ForegroundColor Green
docker build `
    --tag $FULL_TAG `
    --file (Join-Path $PSScriptRoot "Dockerfile") `
    $PSScriptRoot

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker build failed (exit code $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Build succeeded: $FULL_TAG" -ForegroundColor Green

# --- Push (optional) -----------------------------------------
if ($Push) {
    Write-Host ""
    Write-Host "Pushing $FULL_TAG ..." -ForegroundColor Green
    az acr login --name ($REGISTRY -replace "\.azurecr\.io","")
    docker push $FULL_TAG
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Docker push failed (exit code $LASTEXITCODE)." -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "Push succeeded." -ForegroundColor Green
}

# --- Clean up placeholder .env if we created one -------------
if ($cleanupEnv) {
    Remove-Item $envFile -Force
}

# --- Summary -------------------------------------------------
Write-Host ""
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host "  Done."
Write-Host "  To run locally:"
Write-Host "    docker run --env-file .env -p 8000:8000 $FULL_TAG"
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host ""