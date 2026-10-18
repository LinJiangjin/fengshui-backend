#Requires -Version 5.1
<#
.SYNOPSIS
    重启风水装修后端服务（uvicorn main:app）。

.DESCRIPTION
    停止 -> 等待端口释放 -> 启动 -> /health 自检。

    停止逻辑以端口占用者为主判据（含其全部子进程），
    命令行特征匹配仅作兜底；详见 scripts/server_lib.ps1。

.PARAMETER Port
    服务监听端口，默认 8000。

.PARAMETER BindHost
    服务监听地址，默认 0.0.0.0。

.PARAMETER NoReload
    关闭热重载（生产环境建议）。

.PARAMETER WaitSeconds
    等待端口释放与 /health 就绪的最长秒数，默认各 30 秒。

.EXAMPLE
    .\scripts\restart.ps1
    .\scripts\restart.ps1 -Port 8001
    .\scripts\restart.ps1 -NoReload
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    # 不能用 $Host：那是 PowerShell 只读的自动变量
    [string]$BindHost = '0.0.0.0',
    [switch]$NoReload,
    [int]$WaitSeconds = 30
)

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'server_lib.ps1')

Stop-Server -Port $Port -WaitSeconds $WaitSeconds

$health = Start-Server -Port $Port -BindHost $BindHost -NoReload:$NoReload -WaitSeconds $WaitSeconds
$health | ConvertTo-Json -Depth 5
