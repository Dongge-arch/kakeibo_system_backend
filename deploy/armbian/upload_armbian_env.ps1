param(
    [string]$HostAlias = "armbian@192.168.0.172",
    [string]$RemoteDir = "/home/armbian/home-kakeibo-batch",
    [string]$TempEnvPath = "$env:TEMP\home-kakeibo-batch.env",
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$configPath = Join-Path $repoRoot "src\common\config\application.yaml"

if (-not (Test-Path $configPath)) {
    throw "application.yaml was not found: $configPath"
}

$configText = Get-Content -Path $configPath -Raw -Encoding UTF8

function Get-YamlQuotedValue {
    param(
        [string]$Text,
        [string]$Key
    )
    $match = [regex]::Match($Text, "(?m)^\s*$([regex]::Escape($Key)):\s*`"([^`"]*)`"")
    if (-not $match.Success) {
        return ""
    }
    return $match.Groups[1].Value
}

$databaseUrl = Get-YamlQuotedValue -Text $configText -Key "url"
$geminiApiKey = Get-YamlQuotedValue -Text $configText -Key "gemini_api_key"
$geminiModel = Get-YamlQuotedValue -Text $configText -Key "gemini_model"
$apiKey = Get-YamlQuotedValue -Text $configText -Key "api_key"

if ([string]::IsNullOrWhiteSpace($databaseUrl)) {
    throw "database.cloud.url was not found in application.yaml"
}
if ($databaseUrl -match "USER:PASSWORD@HOST|replace-me") {
    throw "database.cloud.url is still a placeholder."
}

$envLines = @(
    "# 2026-07-15 Codex: Generated from local application.yaml for Armbian batch runtime.",
    "KAKEIBO_DATABASE_URL='$($databaseUrl.Replace("'", "'\''"))'",
    "KAKEIBO_DATABASE_INITIALIZE=false",
    "GEMINI_API_KEY='$($geminiApiKey.Replace("'", "'\''"))'",
    "GEMINI_MODEL='$($geminiModel.Replace("'", "'\''"))'",
    "KAKEIBO_API_KEY='$($apiKey.Replace("'", "'\''"))'"
)

# 2026-07-15 Codex: Write UTF-8 without BOM so bash can source the env file.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($TempEnvPath, (($envLines -join "`n") + "`n"), $utf8NoBom)

if ($ValidateOnly) {
    $uri = [System.Uri]$databaseUrl
    Write-Output "Env validation OK. Database host: $($uri.Host)"
    Remove-Item -LiteralPath $TempEnvPath -Force
    exit 0
}

scp -o ConnectTimeout=10 $TempEnvPath "${HostAlias}:/tmp/home-kakeibo-batch.env"
ssh -o ConnectTimeout=10 $HostAlias "mv /tmp/home-kakeibo-batch.env '$RemoteDir/.env' && chmod 600 '$RemoteDir/.env' && cd '$RemoteDir' && echo '.env uploaded' && grep -E '^(KAKEIBO_DATABASE_INITIALIZE|GEMINI_MODEL)=' .env && python3 - <<'PY'
from pathlib import Path
from urllib.parse import urlparse
line = next(value for value in Path('.env').read_text().splitlines() if value.startswith('KAKEIBO_DATABASE_URL='))
value = line.split('=', 1)[1].strip().strip(\"'\")
host = urlparse(value).hostname
print(f'DATABASE_HOST={host}')
PY"

Remove-Item -LiteralPath $TempEnvPath -Force -ErrorAction SilentlyContinue
