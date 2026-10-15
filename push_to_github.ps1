# ============================================================
#  推送到 GitHub
#  用法（在本目录打开终端）：
#      pwsh -File push_to_github.ps1 https://github.com/你的用户名/仓库名.git
#  或双击 推送Github.bat
# ============================================================
param(
    [Parameter(Mandatory = $false, Position = 0)]
    [string]$RepoUrl,

    [string]$Branch = "main",
    [string]$Remote = "origin"
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "    $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "    $text" -ForegroundColor Yellow }

# ---------- 0. 检查 git ----------
Write-Step "检查环境"
try { $gitVersion = (git --version) } catch { throw "没有找到 git，请先安装 Git for Windows" }
Write-Ok $gitVersion

if (-not (Test-Path ".git")) { throw "当前目录不是 git 仓库：$PSScriptRoot" }

# ---------- 1. 设置 remote ----------
Write-Step "配置远程仓库"
$existing = (git remote 2>$null)
if ($RepoUrl) {
    if ($existing -contains $Remote) {
        git remote set-url $Remote $RepoUrl
        Write-Ok "已更新 $Remote -> $RepoUrl"
    } else {
        git remote add $Remote $RepoUrl
        Write-Ok "已添加 $Remote -> $RepoUrl"
    }
} elseif ($existing -contains $Remote) {
    Write-Ok "$Remote 已存在：$(git remote get-url $Remote)"
} else {
    Write-Host "请提供仓库地址，例如：" -ForegroundColor Yellow
    Write-Host "  pwsh -File push_to_github.ps1 https://github.com/用户名/仓库名.git"
    exit 1
}

# ---------- 2. 提交未保存的改动 ----------
Write-Step "检查工作区"
$dirty = (git status --porcelain)
if ($dirty) {
    Write-Warn "还有未提交的改动，先提交它们："
    $dirty | ForEach-Object { Write-Host "      $_" }
    git add -A
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    git commit -m "update $stamp" | Out-Null
    Write-Ok "已自动提交"
} else {
    Write-Ok "工作区干净"
}

# ---------- 3. 推送分支与 tag ----------
Write-Step "推送分支 $Branch"
git push -u $Remote $Branch
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n推送失败（退出码 $LASTEXITCODE）。常见原因：" -ForegroundColor Red
    Write-Host "  · 仓库地址写错了，或仓库还没在 GitHub 上创建" -ForegroundColor Yellow
    Write-Host "  · 没有登录：再执行一次会弹出 Git 凭据窗口，或用 PAT：https://<token>@github.com/用户/仓库.git" -ForegroundColor Yellow
    Write-Host "  · 网络/代理问题" -ForegroundColor Yellow
    exit 1
}
Write-Ok "分支推送完成"

Write-Step "推送 tag（v1.1.0）"
$tags = (git tag -l)
if ($tags) {
    git push $Remote --tags
    if ($LASTEXITCODE -ne 0) {
        Write-Host "tag 推送失败（退出码 $LASTEXITCODE），分支已推送成功。" -ForegroundColor Red
        exit 1
    }
    Write-Ok ("tag 推送完成：" + ($tags -join ", "))
} else {
    Write-Warn "本地没有 tag，跳过"
}

# ---------- 4. 收尾 ----------
Write-Step "完成"
Write-Ok "仓库地址：$(git remote get-url $Remote)"
Write-Host "`n在 GitHub 网页上可以直接看到 README（含界面截图）。" -ForegroundColor Gray
if ($Host.Name -eq "ConsoleHost") { Read-Host "`n按回车键关闭" | Out-Null }
