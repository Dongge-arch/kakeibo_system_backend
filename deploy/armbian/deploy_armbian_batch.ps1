param(
    [string]$HostAlias = "pi",
    [string]$RemoteDir = "/opt/home-kakeibo-batch",
    [string]$ArchivePath = "$env:TEMP\home-kakeibo-batch.tar.gz",
    [switch]$NoSudo
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot
$SshOptions = @("-o", "ConnectTimeout=10")
$SshTtyOptions = @("-tt", "-o", "ConnectTimeout=10")

if (Test-Path $ArchivePath) {
    Remove-Item -LiteralPath $ArchivePath -Force
}

# 2026-07-15 Codex: Package only the files required by the Armbian batch runtime.
& tar -czf $ArchivePath `
    src `
    lambda_api/requirements-layer.txt `
    deploy/armbian/install_batch.sh `
    deploy/armbian/install_batch_user.sh `
    deploy/armbian/home-kakeibo-batch.env.example `
    deploy/armbian/README.md

scp @SshOptions $ArchivePath "${HostAlias}:/tmp/home-kakeibo-batch.tar.gz"
if ($NoSudo) {
    ssh @SshOptions $HostAlias "mkdir -p '$RemoteDir' && tar -xzf /tmp/home-kakeibo-batch.tar.gz -C '$RemoteDir' && cd '$RemoteDir' && bash deploy/armbian/install_batch_user.sh"
    ssh @SshOptions $HostAlias "crontab -l | grep home-kakeibo-auto-input || true"
} else {
    ssh @SshTtyOptions $HostAlias "sudo mkdir -p '$RemoteDir' && sudo chown `$(id -un):`$(id -gn) '$RemoteDir' && tar -xzf /tmp/home-kakeibo-batch.tar.gz -C '$RemoteDir' && cd '$RemoteDir' && bash deploy/armbian/install_batch.sh"
    ssh @SshOptions $HostAlias "systemctl status home-kakeibo-auto-input.timer --no-pager; systemctl status home-kakeibo-auto-input.service --no-pager || true"
}
