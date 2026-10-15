#Requires -Version 5.1
<#
.SYNOPSIS
    重启风水装修后端服务（uvicorn main:app）。

.DESCRIPTION
    按命令行特征匹配并终止 uvicorn 主进程及其 --reload 派生的子进程，
    等待端口释放后重新拉起服务，最后调用 /health 做启动自检。

    注意：uvicorn --reload 会通过 multiprocessing fork 出子进程，
    只杀主进程会残留子进程继续占用端口，因此这里一并清理。

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

$ServerDir = Split-Path -Parent $PSScriptRoot

function Write-Step {
    param([string]$Message)
    Write-Host "[restart] $Message" -ForegroundColor Cyan
}

function Get-ServerProcesses {
    <# 按命令行特征找出本项目启动的 uvicorn 进程及 reload 子进程 #>
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $_.CommandLine -like '*uvicorn*' -or
            $_.CommandLine -like '*multiprocessing-fork*'
        }
}

function Test-PortListening {
    param([int]$Port)
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

# ---------------------------------------------------------------- 1. 停止
Write-Step "stopping existing server on port $Port ..."
$procs = @(Get-ServerProcesses)
if ($procs.Count -eq 0) {
    Write-Host "[restart] no running uvicorn process found" -ForegroundColor DarkGray
}
else {
    foreach ($p in $procs) {
        Write-Host "[restart] killing PID $($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

# ------------------------------------------------- 2. 等待端口释放
$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Test-PortListening -Port $Port) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 300
}
if (Test-PortListening -Port $Port) {
    $owner = (Get-NetTCPConnection -LocalPort $Port -State Listen |
        Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
    throw "port $Port still held by PID $owner; aborting before start"
}
Write-Step "port $Port is free"

# ------------------------------------------------- 3. 启动（新窗口，不阻塞）
# 输出落到日志文件：偶发启动失败时才有现场可查，而不是只看到一句健康检查超时。
$LogDir = Join-Path $ServerDir 'logs'
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$outLog = Join-Path $LogDir 'uvicorn.out.log'
$errLog = Join-Path $LogDir 'uvicorn.err.log'

# 输出被重定向到文件时 Python 会启用块缓冲，进程若崩溃则日志可能还没落盘。
# 关掉缓冲，保证失败时能看到最后几行。
$env:PYTHONUNBUFFERED = '1'

$reloadArg = if ($NoReload) { @() } else { @('--reload') }
$argList = @(
    '-m', 'uvicorn', 'main:app',
    '--host', $BindHost, '--port', $Port
) + $reloadArg

Write-Step "starting: python $($argList -join ' ')"
$proc = Start-Process -FilePath 'python' `
    -ArgumentList $argList `
    -WorkingDirectory $ServerDir `
    -WindowStyle Minimized `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru

# ------------------------------------------------- 4. 健康检查
$healthUrl = "http://127.0.0.1:$Port/health"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$ok = $false
while ((Get-Date) -lt $deadline) {
    $proc.Refresh()
    # 进程已退出且还没通过探活，说明启动阶段就崩了，没必要继续等
    if ($proc.HasExited) {
        break
    }
    try {
        $resp = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        if ($resp.status -eq 'ok' -or $resp.status -eq 'degraded') {
            $ok = $true
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}

if (-not $ok) {
    Write-Host "[restart] startup failed after $($sw.Elapsed.TotalSeconds.ToString('N1'))s" -ForegroundColor Red
    if ($proc.HasExited) {
        Write-Host "[restart] process exited with code $($proc.ExitCode)" -ForegroundColor Red
    }
    # 日志里含数据库连接串等敏感信息，只打最后几行，够定位即可
    foreach ($f in @($outLog, $errLog)) {
        if (Test-Path -LiteralPath $f) {
            Write-Host "[restart] --- tail $f ---" -ForegroundColor Yellow
            Get-Content -LiteralPath $f -Tail 15 -ErrorAction SilentlyContinue
        }
    }
    throw "server did not become healthy: $healthUrl"
}

Write-Host "[restart] server is up in $($sw.Elapsed.TotalSeconds.ToString('N1'))s" -ForegroundColor Green
$resp | ConvertTo-Json -Depth 5
