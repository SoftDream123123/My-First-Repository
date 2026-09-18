# AI 智能面试助手 —— 一键启动（真正的逻辑在这里）
#
# 为什么逻辑不写在 .bat 里：cmd.exe 解析批处理时按「字节偏移」定位下一行，
# 文件里一旦出现多字节字符（中文），偏移就会错位 —— 表现为 `if errorlevel`
# 被读成 `orlevel`、`goto` 目标找不到。改成 GBK 编码也只是把问题挪个位置：
# 控制台代码页与文件编码只要不一致就复发。PowerShell 没有这个缺陷，
# 且它向真实控制台写中文走 Unicode API，任何代码页下都能正确显示。
#
# 本文件必须以 UTF-8 **带 BOM** 保存：Windows PowerShell 5.1 在没有 BOM 时
# 会按 ANSI(936) 解码，中文会变成乱码。

$ErrorActionPreference = 'Stop'

$Root       = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'
$DistIndex  = Join-Path $FrontendDir 'dist\index.html'
$BaseUrl    = 'http://127.0.0.1:8000'
$HealthUrl  = "$BaseUrl/api/health"
$BackendTitle = 'AI Interview Backend - DO NOT CLOSE'

Set-Location $Root

function Write-Head($text) {
    Write-Host ''
    Write-Host '============================================================'
    Write-Host "   $text"
    Write-Host '============================================================'
    Write-Host ''
}

function Write-Fail($lines) {
    Write-Host ''
    Write-Host '[错误] ' -ForegroundColor Red -NoNewline
    Write-Host $lines[0]
    foreach ($line in $lines[1..($lines.Count - 1)]) { Write-Host $line }
    Write-Host ''
    Write-Host '按任意键关闭本窗口 ...' -ForegroundColor DarkGray
    try {
        $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
    } catch {
        # 没有交互式控制台（比如输出被重定向）时读不到按键，直接退出即可
    }
    exit 1
}

function Test-BackendAlive {
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -TimeoutSec 2 -UseBasicParsing
        return ($r.StatusCode -eq 200 -and $r.Content -match 'ok')
    } catch {
        return $false
    }
}

function Test-MySqlPort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync('127.0.0.1', 3306)
        return $task.Wait(1500) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

Write-Head 'AI 智能面试助手 - 一键启动'
Write-Host "   工作目录：$Root"
Write-Host ''
Write-Host '   后端已配置为直接托管前端构建产物（frontend/dist），'
Write-Host '   所以整套应用只有一个进程、一个地址。'
Write-Host ''


# ---------- 1. 检查运行环境 ----------
Write-Host '[1/4] 检查运行环境 ...'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Fail @(
        '没找到 python 命令。',
        '       请安装 Python 3.11 或更高版本，安装时务必勾选',
        '       "Add python.exe to PATH"。',
        '       下载地址：https://www.python.org/downloads/'
    )
}

if (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Host '       正在构建前端 ...'
    Push-Location $FrontendDir
    try {
        $build = & npm run build 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host '       [警告] 前端构建失败，改用已有的 frontend\dist' -ForegroundColor Yellow
            Write-Host '              构建输出：' -ForegroundColor DarkGray
            $build | Select-Object -Last 5 | ForEach-Object { Write-Host "              $_" -ForegroundColor DarkGray }
        } else {
            Write-Host '       前端已重新构建。'
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host '       未找到 npm，跳过前端构建，直接使用已有的 frontend\dist。'
}

if (-not (Test-Path $DistIndex)) {
    Write-Fail @(
        '找不到前端构建产物 frontend\dist\index.html。',
        '       请在 frontend 目录下依次执行：',
        '           npm install',
        '           npm run build'
    )
}


# ---------- 2. 检查数据库 ----------
Write-Host '[2/4] 检查 MySQL (127.0.0.1:3306) ...'

if (-not (Test-MySqlPort)) {
    Write-Fail @(
        '连不上 MySQL（127.0.0.1:3306），后端没有数据库无法启动。',
        '',
        '       启动 MySQL 的两种方式（任选其一）：',
        '         方式一：按 Win+R 输入 services.msc，找到 MySQL 服务，右键「启动」',
        '         方式二：以管理员身份运行命令行，执行  net start mysql',
        '',
        '       若你的数据库账号或端口不是 root@127.0.0.1:3306，',
        '       请修改 backend\.env 里的 DATABASE_URL。'
    )
}
Write-Host '       连接正常。'


# ---------- 3. 启动后端 ----------
Write-Host '[3/4] 启动后端服务 ...'

if (Test-BackendAlive) {
    Write-Host '       检测到服务已在运行，跳过启动。'
} else {
    Start-Process -FilePath 'cmd.exe' `
        -ArgumentList '/k', 'python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1' `
        -WorkingDirectory $BackendDir `
        -WindowStyle Normal | Out-Null

    # ---------- 4. 等待就绪 ----------
    Write-Host '[4/4] 等待服务就绪 ...'
    $ready = $false
    for ($i = 1; $i -le 40; $i++) {
        Start-Sleep -Seconds 1
        if (Test-BackendAlive) { $ready = $true; break }
    }

    if (-not $ready) {
        Write-Fail @(
            '等了 40 秒服务仍未就绪。',
            "       请查看标题为 `"$BackendTitle`" 的那个窗口，",
            '       里面是真实的报错信息。',
            '',
            '       常见原因：',
            '         - 数据库密码不对  -> 改 backend\.env 里的 DATABASE_URL',
            '         - Python 依赖没装 -> pip install -r backend\requirements.txt'
        )
    }
    Write-Host '       服务已就绪。'
}


# ---------- 打开浏览器 ----------
Write-Head '已启动！浏览器马上自动打开'
Write-Host "   地址：$BaseUrl"
Write-Host '   账号：admin'
Write-Host '   密码：admin12345'
Write-Host ''
Write-Host "   - 关闭本窗口不影响服务"
Write-Host "   - 要停止服务，请关闭标题为 `"$BackendTitle`" 的窗口"
Write-Host ''

Start-Process $BaseUrl
Start-Sleep -Seconds 4
