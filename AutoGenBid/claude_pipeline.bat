@echo off
REM ============================================================
REM  标书自动生成 Pipeline — Windows 一键启动
REM ============================================================

cd /d "%~dp0"

echo.
echo   标书自动生成与参考文件制作 Pipeline
echo   ================================
echo.

REM 检查 Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] 未找到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

REM 检查依赖
python -c "import docx" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   [INFO] 正在安装依赖...
    pip install -r requirements.txt
)

REM 如果配置文件不存在，生成默认配置
if not exist "pipeline_config.yaml" (
    echo   [INFO] 生成默认配置文件...
    python bid_pipeline.py --init
    echo.
    echo   请编辑 pipeline_config.yaml 后重新运行此脚本。
    pause
    exit /b 0
)

REM 运行 Pipeline，传递所有参数
python bid_pipeline.py %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo   [FAIL] Pipeline 执行出错
    pause
    exit /b 1
)

echo.
echo   [DONE] 完成！
pause
