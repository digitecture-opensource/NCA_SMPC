# deploy-azure.ps1
# Builds, pushes, and deploys the NCA SmPC & OD Portal to Azure App Service.
#
# Prerequisites:
#   - Docker Desktop running
#   - Azure CLI installed and logged in  (az login)
#   - .env file present at project root
#
# Usage:
#   .\deploy-azure.ps1                  # build, push and deploy :latest
#   .\deploy-azure.ps1 -Tag "v1.0"      # use a specific version tag
#   .\deploy-azure.ps1 -SkipBuild       # push/deploy a tag already built locally

param(
    [string]$Tag       = "latest",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Continue"

# --- Config --------------------------------------------------
$REGISTRY       = "ncasmpcapp.azurecr.io"
$IMAGE_NAME     = "nca-smpc-app"
$FULL_IMAGE     = "${REGISTRY}/${IMAGE_NAME}:${Tag}"

$RESOURCE_GROUP = "IDMP_Base"
$APP_PLAN       = "ASP-IDMPBase-9e32"
$APP_NAME       = "NCA-SMPC-app"
$LOCATION       = "uksouth"
# -------------------------------------------------------------

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  NCA SmPC & OD Portal - Azure Deployment"  -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Registry  : $REGISTRY"
Write-Host "  Image     : $FULL_IMAGE"
Write-Host "  App       : $APP_NAME"
Write-Host "  Plan      : $APP_PLAN  (B1 Linux)"
Write-Host "  RG        : $RESOURCE_GROUP"
Write-Host ""

# --- Verify tools --------------------------------------------
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Azure CLI not found. Install from https://aka.ms/installazurecliwindows" -ForegroundColor Red
    exit 1
}
if (-not (docker info 2>$null)) {
    Write-Host "ERROR: Docker is not running or not installed." -ForegroundColor Red
    exit 1
}

# --- Azure login check ---------------------------------------
$account = az account show --query "id" -o tsv 2>$null
if (-not $account) {
    Write-Host "Not logged in to Azure. Running az login..." -ForegroundColor Yellow
    az login
}

# --- Step 0: Create ACR if it does not exist -----------------
Write-Host "[0/4] Checking ACR '$REGISTRY'..." -ForegroundColor Green
$acrExists = (az acr show --name ($REGISTRY -replace "\.azurecr\.io","") --query "name" -o tsv 2>$null) 2>$null
if (-not $acrExists) {
    Write-Host "      ACR not found - creating ncasmpcapp in $RESOURCE_GROUP ($LOCATION)..." -ForegroundColor Yellow
    az acr create `
        --resource-group $RESOURCE_GROUP `
        --name ($REGISTRY -replace "\.azurecr\.io","") `
        --sku Basic `
        --location $LOCATION
    Write-Host "      ACR created: $REGISTRY" -ForegroundColor Green
} else {
    Write-Host "      ACR already exists." -ForegroundColor Green
}

# --- Step 1: Build -------------------------------------------
if (-not $SkipBuild) {
    Write-Host "[1/4] Building Docker image..." -ForegroundColor Green
    & "$PSScriptRoot\build-docker.ps1" -Tag $Tag -Push
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "[1/4] Skipping build (SkipBuild flag set)." -ForegroundColor Yellow
    Write-Host "      Logging in to ACR and pushing existing local image..." -ForegroundColor Green
    az acr login --name ($REGISTRY -replace "\.azurecr\.io","")
    docker push $FULL_IMAGE
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# --- Step 2: Create Web App if it doesn't exist --------------
Write-Host "[2/4] Checking Web App '$APP_NAME'..." -ForegroundColor Green
$exists = (az webapp show --resource-group $RESOURCE_GROUP --name $APP_NAME --query "name" -o tsv 2>$null) 2>$null

if (-not $exists) {
    Write-Host "      Web App not found - creating..." -ForegroundColor Yellow
    az webapp create `
        --resource-group $RESOURCE_GROUP `
        --plan $APP_PLAN `
        --name $APP_NAME `
        --deployment-container-image-name $FULL_IMAGE
    Write-Host "      Web App created." -ForegroundColor Green
} else {
    Write-Host "      Web App already exists." -ForegroundColor Green
}

# --- Step 3: Configure ACR access (managed identity) ---------
Write-Host "[3/4] Configuring ACR pull access via managed identity..." -ForegroundColor Green

az webapp identity assign `
    --resource-group $RESOURCE_GROUP `
    --name $APP_NAME | Out-Null

$principalId = az webapp identity show `
    --resource-group $RESOURCE_GROUP `
    --name $APP_NAME `
    --query "principalId" -o tsv

$acrId = az acr show `
    --name ($REGISTRY -replace "\.azurecr\.io","") `
    --query "id" -o tsv

az role assignment create `
    --assignee $principalId `
    --role AcrPull `
    --scope $acrId | Out-Null

az resource update `
    --ids (az webapp show --resource-group $RESOURCE_GROUP --name $APP_NAME --query "id" -o tsv) `
    --set properties.acrUseManagedIdentityCreds=true | Out-Null

Write-Host "      ACR pull via managed identity configured." -ForegroundColor Green

# --- Step 4: Set container image and app settings ------------
Write-Host "[4/4] Updating container image and app settings..." -ForegroundColor Green

az webapp config container set `
    --resource-group $RESOURCE_GROUP `
    --name $APP_NAME `
    --container-image-name $FULL_IMAGE `
    --container-registry-url "https://$REGISTRY" | Out-Null

# --- Parse .env and build app settings -----------------------
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "ERROR: .env file not found at $envFile" -ForegroundColor Red
    exit 1
}

# Keys that are local-machine paths or pipeline-only - skip for Azure
$skipKeys = @(
    "PFX_PATH", "PFX_PASS", "LOG_DIR", "MHRA_ORPHAN_DIR",
    "MHRA_ORPHAN_CURRENT_CSV", "MHRA_ORPHAN_EXPIRED_CSV",
    "EMA_INPUT_ORG_DIR", "EMA_INPUT_ORG_FILE",
    "SMPC_STEPS", "SMPC_PDF_DIR", "SMPC_OUT_JSON", "SMPC_OUT_XLSX",
    "COMMIT_SUGGESTIONS", "FLASK_ENV", "FLASK_DEBUG", "FLASK_SECRET_KEY",
    "SECRET_KEY", "ORG_DB",
    "server", "database", "SQlUSer", "password", "driver"
)

$settings = @(
    "WEBSITES_PORT=8000",
    "DJANGO_DEBUG=0"
)

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }

    $eqIdx = $line.IndexOf("=")
    if ($eqIdx -lt 1) { return }

    $key   = $line.Substring(0, $eqIdx).Trim()
    $value = $line.Substring($eqIdx + 1).Trim().Trim('"').Trim("'")

    if ($skipKeys -contains $key) { return }

    $settings += "$key=$value"
}

$appUrl = az webapp show --resource-group $RESOURCE_GROUP --name $APP_NAME --query "defaultHostName" -o tsv
$settings += "DJANGO_ALLOWED_HOSTS=$appUrl"
$settings += "DJANGO_CSRF_TRUSTED_ORIGINS=https://$appUrl"

Write-Host "      Applying $($settings.Count) app settings from .env..." -ForegroundColor Green

az webapp config appsettings set `
    --resource-group $RESOURCE_GROUP `
    --name $APP_NAME `
    --settings @settings | Out-Null

Write-Host "      Container image and app settings applied." -ForegroundColor Green

# --- Restart to pick up new image ----------------------------
Write-Host "      Restarting Web App..." -ForegroundColor Green
az webapp restart --resource-group $RESOURCE_GROUP --name $APP_NAME | Out-Null

# --- Summary -------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Deployment complete."
Write-Host "  URL : https://$appUrl"
Write-Host ""
Write-Host "  $($settings.Count) app settings applied from .env"
Write-Host "  Skipped local-only keys: PFX_PATH, LOG_DIR, MHRA_ORPHAN_DIR etc."
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""