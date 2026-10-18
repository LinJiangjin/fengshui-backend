#Requires -Version 5.1
<#
.SYNOPSIS
    停止风水装修后端服务（uvicorn main:app）。

.DESCRIPTION
    与 restart.ps1 共用 scripts/server_lib.ps1：以端口占用者为主判据，
    连带清理 --reload 派生的子进程，然后等待端口真正释放，
    最后确认 /health 不再响应。

.PARAMETER Port
    服务监听端口，默认 8000。

.PARAMETER WaitSeconds
    等待端口释放的最长秒数，默认 30 秒。

.EXAMPLE
    .\scripts\stop.ps1
    .\scripts\stop.ps1 -Port 8001
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [int]$WaitSeconds = 30
)

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'server_lib.ps1')

Stop-Server -Port $Port -WaitSeconds $WaitSeconds

# 端口释放后再确认一次：有些进程会在退出前仍短暂应答请求
# 不指定异常类型——不同 PowerShell 版本对连接被拒抛出的异常类型不一致，
# 用「有没有请求成功」来判断更稳。
$stillResponding = $true
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3 | Out-Null
}
catch {
    $stillResponding = $false
}

if ($stillResponding) {
    throw "service is still responding on port $Port; stop may have failed"
}
Write-Host '[server] service stopped (connection refused)' -ForegroundColor Green
