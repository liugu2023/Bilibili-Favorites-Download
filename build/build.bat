@echo off
echo 正在检查并关闭旧程序...
taskkill /F /IM "B站收藏夹下载器.exe" 2>nul
timeout /t 2 /nobreak >nul

echo 清理旧文件...
rd /s /q dist 2>nul
rd /s /q build 2>nul

echo 开始构建...
python build.py

if errorlevel 1 (
    echo 构建失败，请检查错误信息
    pause
    exit /b 1
)

echo 构建完成！
pause 