@echo off
title ngrok - WhatsApp Bot Tunnel
cd /d "%~dp0"
echo.
echo ========================================
echo ngrok Tunnel для WhatsApp бота
echo ========================================
echo.
echo Запуск ngrok на порту 8000...
echo.
ngrok.exe http 8000
pause

