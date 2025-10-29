@echo off
chcp 65001 >nul
echo ================================================================================
echo   🍌 Banana批量并发图像生成工具
echo ================================================================================
echo.

python run_batch.py

if errorlevel 1 (
    echo.
    echo ❌ 执行过程中出现错误
    pause
    exit /b 1
)

echo.
echo ✅ 执行完成！
pause
