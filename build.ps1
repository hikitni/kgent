<#
.SYNOPSIS
    KgentV3 一键打包脚本 — 生成可分发的 ZIP 压缩包
.DESCRIPTION
    使用 PyInstaller 将项目打包为单个 .exe，连同配置模板、AI Prompt、
    启动说明和快捷启动脚本一起压缩为 KgentV3-发行包.zip。
.NOTES
    运行环境：Windows PowerShell 5.1+ / Python 3.10+
    用法：    在项目根目录执行  .\build.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------- 基础路径 ----------
$ProjectRoot  = $PSScriptRoot
$DistDir      = Join-Path $ProjectRoot "dist"
$BuildDir     = Join-Path $ProjectRoot "build"
$SpecFile     = Join-Path $ProjectRoot "KgentV3.spec"
$ReleaseDir   = Join-Path $DistDir "KgentV3"
$ZipName      = "KgentV3-release.zip"
$ZipPath      = Join-Path $DistDir $ZipName
$ExeName      = "KgentV3.exe"

# ---------- 颜色输出辅助 ----------
function Write-Step  { param([string]$msg) Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$msg) Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn  { param([string]$msg) Write-Host "    [WARN] $msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$msg) Write-Host "    [FAIL] $msg" -ForegroundColor Red }

# ========== 步骤 1：检查 / 安装 PyInstaller ==========
Write-Step "检查 PyInstaller ..."
$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $pyinstaller) {
    Write-Warn "未检测到 PyInstaller，正在自动安装 ..."
    pip install pyinstaller --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Err "PyInstaller 安装失败，请手动执行: pip install pyinstaller"
        exit 1
    }
    Write-Ok "PyInstaller 安装完成"
} else {
    Write-Ok "PyInstaller 已就绪: $($pyinstaller.Source)"
}

# ========== 步骤 2：清理旧产物 ==========
Write-Step "清理旧的打包产物 ..."
foreach ($dir in @($DistDir, $BuildDir)) {
    if (Test-Path $dir) {
        Remove-Item $dir -Recurse -Force
        Write-Ok "已删除 $dir"
    }
}
if (Test-Path $SpecFile) { Remove-Item $SpecFile -Force }

# ========== 步骤 3：PyInstaller 打包 ==========
Write-Step "使用 PyInstaller 打包 main.py -> $ExeName ..."

# 收集 --add-data 参数：静态资源、模板、AI prompt
$addDataArgs = @(
    "--add-data", "daily_reporter/web/static;daily_reporter/web/static",
    "--add-data", "daily_reporter/web/templates;daily_reporter/web/templates",
    "--add-data", "ai_report_prompt.md;."
)

# 收集 --hidden-import 参数：确保运行时能找到所有子模块
$hiddenImports = @(
    "--hidden-import", "daily_reporter",
    "--hidden-import", "daily_reporter.web",
    "--hidden-import", "daily_reporter.web.app",
    "--hidden-import", "daily_reporter.web.routes",
    "--hidden-import", "daily_reporter.web.routes.snapshots",
    "--hidden-import", "daily_reporter.web.routes.reports",
    "--hidden-import", "daily_reporter.web.routes.compare",
    "--hidden-import", "daily_reporter.ai",
    "--hidden-import", "daily_reporter.config",
    "--hidden-import", "daily_reporter.diff",
    "--hidden-import", "daily_reporter.reporter",
    "--hidden-import", "daily_reporter.snapshot",
    "--hidden-import", "daily_reporter.tasks",
    "--hidden-import", "daily_reporter.ui",
    "--hidden-import", "uvicorn",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.protocols",
    "--hidden-import", "uvicorn.protocols.http",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan",
    "--hidden-import", "uvicorn.lifespan.on"
)

$pyinstallerArgs = @(
    "--onefile",
    "--name", "KgentV3",
    "--console",
    "--noconfirm"
) + $addDataArgs + $hiddenImports + @("main.py")

Write-Host "    pyinstaller $($pyinstallerArgs -join ' ')" -ForegroundColor DarkGray
Push-Location $ProjectRoot
& pyinstaller @pyinstallerArgs
if ($LASTEXITCODE -ne 0) {
    Write-Err "PyInstaller 打包失败，请检查上方输出日志"
    Pop-Location
    exit 1
}
Pop-Location
Write-Ok "EXE 打包完成: dist/$ExeName"

# ========== 步骤 4：组装发行目录 ==========
Write-Step "组装发行目录 $ReleaseDir ..."

New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

# 4.1 复制 exe
Copy-Item (Join-Path $DistDir $ExeName) $ReleaseDir
Write-Ok "复制 $ExeName"

# 4.2 复制配置模板
Copy-Item (Join-Path $ProjectRoot "config.example.json") $ReleaseDir
Write-Ok "复制 config.example.json"

# 4.3 复制 AI Prompt 模板
Copy-Item (Join-Path $ProjectRoot "ai_report_prompt.md") $ReleaseDir
Write-Ok "复制 ai_report_prompt.md"

# 4.4 复制启动说明
$guidePath = Join-Path $ProjectRoot "启动说明.md"
if (Test-Path $guidePath) {
    Copy-Item $guidePath $ReleaseDir
    Write-Ok "复制 启动说明.md"
} else {
    Write-Warn "未找到 启动说明.md，跳过（请确认文件存在于项目根目录）"
}

# 4.5 生成 start-web.bat
$batContent = @"
@echo off
chcp 65001 >nul
echo ============================================
echo    KgentV3 - 文件变更监控 + AI 日报生成
echo ============================================
echo.
echo 正在启动 Web 管理界面 ...
echo 启动后将自动打开浏览器，如未自动打开请访问:
echo   http://localhost:7421
echo.
echo 按 Ctrl+C 可停止服务
echo ============================================
echo.
KgentV3.exe --web
pause
"@
$batPath = Join-Path $ReleaseDir "start-web.bat"
Set-Content -Path $batPath -Value $batContent -Encoding UTF8
Write-Ok "生成 start-web.bat"

# 4.6 生成 start-cli.bat（命令行交互菜单入口）
$cliBat = @"
@echo off
chcp 65001 >nul
echo 启动 KgentV3 命令行交互菜单 ...
KgentV3.exe
pause
"@
Set-Content -Path (Join-Path $ReleaseDir "start-cli.bat") -Value $cliBat -Encoding UTF8
Write-Ok "生成 start-cli.bat"

# ========== 步骤 5：压缩为 ZIP ==========
Write-Step "正在压缩为 $ZipName ..."

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path $ReleaseDir -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Ok "压缩完成: $ZipPath"

# ========== 步骤 6：输出结果 ==========
$zipSize = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Write-Step "打包完成！"
Write-Host ""
Write-Host "    发行包: $ZipPath" -ForegroundColor White
Write-Host "    大  小: ${zipSize} MB" -ForegroundColor White
Write-Host ""
Write-Host "    发行目录结构:" -ForegroundColor White
Get-ChildItem $ReleaseDir | ForEach-Object {
    Write-Host "      - $($_.Name)" -ForegroundColor Gray
}
Write-Host ""
Write-Host "    将 $ZipName 发送给使用者即可，解压后参照 启动说明.md 操作。" -ForegroundColor Green
Write-Host ""
