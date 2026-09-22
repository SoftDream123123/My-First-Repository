# AI 智能面试助手 —— 开发模式启动（后端 8000 + 前端 5173 两个进程）
#
# 与根目录「一键启动.bat」的区别：
#   一键启动.bat     生产形态。先 `npm run build` 出 frontend/dist，再由后端
#                    单进程托管，只有一个地址 8000。演示 / 交付用这个。
#   启动开发模式.bat  开发形态。后端跑纯 API（8000），前端跑 Vite 开发服务器
#                    （5173，自带热更新），页面请求经 Vite 代理打到后端。
#                    改前端代码即时生效，**联调用这个**。
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

$Root        = Split-Path -Parent $PSScriptRoot
$BackendDir  = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'

$BackendUrl  = 'http://127.0.0.1:8000'
$FrontendUrl = 'http://127.0.0.1:5173'
$HealthUrl   = "$BackendUrl/api/health"

# 标题只用 ASCII：它会被拼进 cmd.exe 的命令行，中文要跨越代码页边界。
$BackendTitle  = 'AI Interview Backend  8000  DO NOT CLOSE'
$FrontendTitle = 'AI Interview Frontend 5173  DO NOT CLOSE'

# ⚠️ 只有**后端**窗口的标题会真的生效。
#
# npm 会改写控制台标题（Node 的 process.title 在 Windows 上就是 SetConsoleTitle），
# 所以 `title X && npm run dev` 里的 X 会被覆盖回默认值。实测：把 npm 换成
# `node node_modules/vite/bin/vite.js` 标题就能保住 —— 但那样等于把 vite 的内部
# 路径写死在启动器里，项目哪天换了 dev 脚本它不会跟着变，得不偿失。
# 因此前端窗口**按内容识别**（它是唯一会打印 "VITE ... ready in" 的那个），
# 下面的提示文案据此措辞。

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

function Test-HttpOk($url) {
    try {
        $r = Invoke-WebRequest -Uri $url -TimeoutSec 2 -UseBasicParsing
        return ($r.StatusCode -eq 200)
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

function Test-PortBusy($port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync('127.0.0.1', $port)
        return $task.Wait(1000) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}


Write-Head 'AI 智能面试助手 - 开发模式启动'
Write-Host "   工作目录：$Root"
Write-Host ''
Write-Host "   后端 $BackendUrl  （纯 API，不开前端托管）"
Write-Host "   前端 $FrontendUrl  （Vite 开发服务器，改代码即时生效）"
Write-Host ''
Write-Host '   两者都会各开一个窗口，关掉窗口即停止对应服务。'
Write-Host ''


# ---------- 1. 检查运行环境 ----------
Write-Host '[1/5] 检查运行环境 ...'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Fail @(
        '没找到 python 命令。',
        '       请安装 Python 3.11 或更高版本，安装时务必勾选',
        '       "Add python.exe to PATH"。',
        '       下载地址：https://www.python.org/downloads/'
    )
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Fail @(
        '没找到 npm 命令。',
        '       请安装 Node.js 22 或更高版本。',
        '       下载地址：https://nodejs.org/'
    )
}

if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    Write-Fail @(
        '前端依赖没装（缺 frontend\node_modules）。',
        '       请先在 frontend 目录下执行 npm install：',
        "           cd `"$FrontendDir`"",
        '           npm install'
    )
}

Write-Host '       Python 与 Node 都在。'


# ---------- 2. 检查数据库 ----------
Write-Host '[2/5] 检查 MySQL (127.0.0.1:3306) ...'

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
Write-Host '[3/5] 启动后端服务 ...'

if (Test-HttpOk $HealthUrl) {
    Write-Host '       检测到后端已在运行，跳过启动。'
} elseif (Test-PortBusy 8000) {
    Write-Fail @(
        '端口 8000 被别的程序占着，但它不是本项目后端。',
        '       请先关掉占用 8000 的程序，再重新运行本脚本。',
        '',
        '       查看占用者：  netstat -ano | findstr :8000'
    )
} else {
    # --workers 1 是硬要求：刷题的限流计数是**进程内**的，多进程会各算一份
    # （见 backend\.env.example 的 PRACTICE_RATE_LIMIT_PER_MINUTE 说明）。
    Start-Process -FilePath 'cmd.exe' `
        -ArgumentList '/k', "title $BackendTitle && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1" `
        -WorkingDirectory $BackendDir `
        -WindowStyle Normal | Out-Null

    $ready = $false
    for ($i = 1; $i -le 40; $i++) {
        Start-Sleep -Seconds 1
        if (Test-HttpOk $HealthUrl) { $ready = $true; break }
    }

    if (-not $ready) {
        Write-Fail @(
            '等了 40 秒后端仍未就绪。',
            "       请查看标题为 `"$BackendTitle`" 的那个窗口，",
            '       里面是真实的报错信息。',
            '',
            '       常见原因：',
            '         - 数据库密码不对  -> 改 backend\.env 里的 DATABASE_URL',
            '         - Python 依赖没装 -> pip install -r backend\requirements.txt',
            '         - 数据库还没建表  -> 见 README 的「建库」一节'
        )
    }
    Write-Host '       后端已就绪。'
}


# ---------- 4. 启动前端 ----------
Write-Host '[4/5] 启动前端开发服务器 ...'

if (Test-HttpOk $FrontendUrl) {
    Write-Host '       检测到前端已在运行，跳过启动。'
} elseif (Test-PortBusy 5173) {
    Write-Fail @(
        '端口 5173 被别的程序占着，但它不是本项目的 Vite 服务。',
        '       请先关掉占用 5173 的程序，再重新运行本脚本。',
        '',
        '       查看占用者：  netstat -ano | findstr :5173'
    )
} else {
    Start-Process -FilePath 'cmd.exe' `
        -ArgumentList '/k', "title $FrontendTitle && npm run dev" `
        -WorkingDirectory $FrontendDir `
        -WindowStyle Normal | Out-Null

    $ready = $false
    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-HttpOk $FrontendUrl) { $ready = $true; break }
    }

    if (-not $ready) {
        Write-Fail @(
            '等了 30 秒前端仍未就绪。',
            '       请查看新弹出的那个前端窗口（它会打印 VITE 的输出；',
            '       标题会被 npm 改掉，所以认内容不认标题），',
            '       里面是真实的报错信息。'
        )
    }
    Write-Host '       前端已就绪。'
}


# ---------- 打开浏览器 ----------
Write-Head '已启动！浏览器马上自动打开'
Write-Host "   开发地址：$FrontendUrl   ← 日常改代码看这个"
Write-Host "   接口地址：$BackendUrl/api/health （健康检查）"
Write-Host ''
Write-Host '   账号：admin'
Write-Host '   密码：admin12345'
Write-Host ''
Write-Host "   - 关闭本窗口不影响服务"
Write-Host '   - 要停止服务，关掉刚才弹出的那两个窗口：'
Write-Host "       后端窗口标题为 `"$BackendTitle`"；"
Write-Host '       前端窗口标题会被 npm 改掉，认它打印的 VITE 输出即可。'
Write-Host ''

Start-Process $FrontendUrl
Start-Sleep -Seconds 2
