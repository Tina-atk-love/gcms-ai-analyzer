# ============================================================
# GCMS AI Agent 一键安装脚本 (DeepSeek版)
# ============================================================
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  GCMS AI Agent - 环境安装 (DeepSeek API)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$python = "C:\Users\86150\AppData\Local\Programs\Python\Python312\python.exe"

# Step 1: Check Python
Write-Host "[1/3] 检查 Python..." -ForegroundColor Yellow
if (-not (Test-Path $python)) {
    Write-Host "ERROR: Python not found" -ForegroundColor Red
    pause; exit 1
}
& $python --version
Write-Host "Python OK" -ForegroundColor Green

# Step 2: Install dependencies
Write-Host ""
Write-Host "[2/3] 安装 Python 依赖..." -ForegroundColor Yellow
Write-Host "  使用清华镜像加速..."
& $python -m pip install openai pandas numpy matplotlib seaborn scipy scikit-learn openpyxl -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: 部分包安装失败，尝试默认源..." -ForegroundColor Yellow
    & $python -m pip install openai pandas numpy matplotlib seaborn scipy scikit-learn openpyxl
}
Write-Host "依赖安装完成" -ForegroundColor Green

# Step 3: Check API Key
Write-Host ""
Write-Host "[3/3] 配置 DeepSeek API Key..." -ForegroundColor Yellow
if ($env:DEEPSEEK_API_KEY) {
    Write-Host "DEEPSEEK_API_KEY 已设置" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "获取 DeepSeek API Key (国内直接访问，免费注册):" -ForegroundColor White
    Write-Host "  1. 打开 https://platform.deepseek.com" -ForegroundColor White
    Write-Host "  2. 注册账号（手机号即可）" -ForegroundColor White
    Write-Host "  3. 右上角 → API Keys → 创建新 Key" -ForegroundColor White
    Write-Host "  4. 复制 sk- 开头的 Key" -ForegroundColor White
    Write-Host ""
    Write-Host "  费用: 约￥1/百万tokens，一次分析约几分钱" -ForegroundColor DarkGray
    Write-Host ""
    $key = Read-Host "  粘贴 API Key (或按 Enter 跳过)"
    if ($key) {
        [Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", $key, "User")
        $env:DEEPSEEK_API_KEY = $key
        Write-Host "  API Key 已保存" -ForegroundColor Green
    } else {
        Write-Host "  跳过，使用前请手动设置:" -ForegroundColor Yellow
        Write-Host '    $env:DEEPSEEK_API_KEY = "sk-xxx"' -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  安装完成!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "启动 Agent:" -ForegroundColor White
Write-Host "  cd C:\Users\86150\gcms_analyzer" -ForegroundColor White
Write-Host "  python gcms_agent.py" -ForegroundColor White
Write-Host ""
pause
