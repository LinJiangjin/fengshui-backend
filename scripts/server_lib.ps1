#Requires -Version 5.1
<#
.SYNOPSIS
    后端服务进程管理公共函数，供 restart.ps1 / stop.ps1 共用。

.DESCRIPTION
    停止逻辑以「端口占用者」为准：

      1. 找出监听目标端口的进程（真正占用端口的人）
      2. 展开它的所有后代（uvicorn --reload 的 reloader 与 worker 子进程）
      3. 再按命令行特征兜底扫一遍 uvicorn / multiprocessing-fork

    只按命令行特征匹配会漏掉手工启动的实例（实测踩过：进程在跑、
    端口被占，但 CIM 查询没返回它），因此端口才是主判据。
#>

$Script:ServerDir = Split-Path -Parent $PSScriptRoot

function Write-Step {
    param([string]$Message, [string]$Tag = 'server')
    Write-Host "[$Tag] $Message" -ForegroundColor Cyan
}

function Test-PortListening {
    param([int]$Port)
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Get-PortOwnerPids {
    <# 监听指定端口的进程 PID（去重） #>
    param([int]$Port)
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
}

function Get-ServerProcesses {
    <#
    返回本服务相关的全部进程对象：端口占用者 + 其全部后代 + 特征匹配到的 python 进程。
    停止时必须一次拿全，否则先杀父进程会让子进程被重新收养、端口继续被占。
    #>
    param([int]$Port)

    $pids = [System.Collections.Generic.List[int]]::new()

    foreach ($ownerPid in (Get-PortOwnerPids -Port $Port)) {
        # 变量名不能叫 $pid：那是 PowerShell 只读的自动变量（当前进程 ID）
        if ($ownerPid -and -not $pids.Contains($ownerPid)) { $pids.Add($ownerPid) }
    }

    # 端口占用者的所有后代：--reload 的 reloader 与 multiprocessing worker
    $frontier = [System.Collections.Generic.List[int]]::new()
    $frontier.AddRange($pids)
    while ($frontier.Count -gt 0) {
        $next = [System.Collections.Generic.List[int]]::new()
        foreach ($parent in $frontier) {
            $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$parent" |
                Select-Object -ExpandProperty ProcessId
            foreach ($child in $children) {
                if ($child -and -not $pids.Contains($child)) {
                    $pids.Add($child)
                    $next.Add($child)
                }
            }
        }
        $frontier = $next
    }

    # 兜底：按命令行特征扫，覆盖端口查询偶发拿不到的情况
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $_.CommandLine -like '*uvicorn*' -or
            $_.CommandLine -like '*multiprocessing-fork*'
        } |
        ForEach-Object {
            if (-not $pids.Contains($_.ProcessId)) { $pids.Add($_.ProcessId) }
        }

    # 用一次查询拿到全部进程对象，避免逐个 Get-CimInstance
    if ($pids.Count -eq 0) { return @() }
    $filter = ($pids | ForEach-Object { "ProcessId=$_" }) -join ' OR '
    @(Get-CimInstance Win32_Process -Filter $filter | Sort-Object ProcessId)
}

function Stop-Server {
    <# 停止服务并等待端口释放；端口被非本服务进程占用时抛错 #>
    param(
        [int]$Port,
        [int]$WaitSeconds = 30
    )

    Write-Step "stopping server on port $Port ..."
    $procs = @(Get-ServerProcesses -Port $Port)
    if ($procs.Count -eq 0) {
        Write-Step 'no running server process found' -Tag 'server'
    }
    else {
        foreach ($p in $procs) {
            $cmd = $p.CommandLine
            if ($cmd.Length -gt 90) { $cmd = $cmd.Substring(0, 90) + '...' }
            Write-Step "killing PID $($p.ProcessId) -> $cmd"
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Test-PortListening -Port $Port) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 300
    }
    if (Test-PortListening -Port $Port) {
        $owner = (Get-PortOwnerPids -Port $Port) -join ', '
        throw "port $Port still held by PID $owner; it may not be this service, check manually"
    }
    Write-Step "port $Port is free"
}

function Start-Server {
    <#
    拉起服务并做启动自检。
    失败时打印进程退出码与日志尾部，便于定位是 import 报错、端口占用还是数据库不通。
    #>
    param(
        [int]$Port,
        [string]$BindHost = '0.0.0.0',
        [switch]$NoReload,
        [int]$WaitSeconds = 30
    )

    $LogDir = Join-Path $Script:ServerDir 'logs'
    if (-not (Test-Path -LiteralPath $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $outLog = Join-Path $LogDir 'uvicorn.out.log'
    $errLog = Join-Path $LogDir 'uvicorn.err.log'

    # 输出被重定向到文件时 Python 启用块缓冲，进程崩溃时日志可能还没落盘
    $env:PYTHONUNBUFFERED = '1'

    $reloadArg = if ($NoReload) { @() } else { @('--reload') }
    $argList = @(
        '-m', 'uvicorn', 'main:app',
        '--host', $BindHost, '--port', $Port
    ) + $reloadArg

    Write-Step "starting: python $($argList -join ' ')"
    $proc = Start-Process -FilePath 'python' `
        -ArgumentList $argList `
        -WorkingDirectory $Script:ServerDir `
        -WindowStyle Minimized `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru

    $healthUrl = "http://127.0.0.1:$Port/health"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    $resp = $null
    while ((Get-Date) -lt $deadline) {
        $proc.Refresh()
        # 进程已退出且还没通过探活，说明启动阶段就崩了，没必要继续等
        if ($proc.HasExited) { break }
        try {
            $candidate = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
            # 计算类接口不依赖数据库，库挂了允许降级启动，因此 degraded 也算就绪
            if ($candidate.status -eq 'ok' -or $candidate.status -eq 'degraded') {
                $resp = $candidate
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }

    if ($null -eq $resp) {
        Write-Step "startup failed after $($sw.Elapsed.TotalSeconds.ToString('N1'))s" -Tag 'server'
        if ($proc.HasExited) {
            Write-Host "[server] process exited with code $($proc.ExitCode)" -ForegroundColor Red
        }
        # 日志里含数据库连接串等敏感信息，只打最后几行，够定位即可
        foreach ($f in @($outLog, $errLog)) {
            if (Test-Path -LiteralPath $f) {
                Write-Host "[server] --- tail $f ---" -ForegroundColor Yellow
                Get-Content -LiteralPath $f -Tail 15 -ErrorAction SilentlyContinue
            }
        }
        throw "server did not become healthy: $healthUrl"
    }

    Write-Step "server is up in $($sw.Elapsed.TotalSeconds.ToString('N1'))s"
    return $resp
}
