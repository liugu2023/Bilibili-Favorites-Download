@echo off
chcp 65001 > nul

::echo 正在检查并安装依赖...
::pip install you-get pyinstaller

::echo 正在下载ffmpeg...
::powershell -Command "& {Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile 'ffmpeg.zip'}"
::powershell -Command "& {Expand-Archive -Path 'ffmpeg.zip' -DestinationPath 'temp' -Force}"
::copy "temp\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe" "ffmpeg.exe"
::rmdir /s /q temp
::del ffmpeg.zip

echo 正在打包程序...
pyinstaller --clean Bilibili_fav_downloader.spec

::echo 清理临时文件...
::del ffmpeg.exe

echo 打包完成！ 