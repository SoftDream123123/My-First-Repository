@echo off
REM ---------------------------------------------------------------------
REM  Double-click this file to start the whole app.
REM
REM  This file is deliberately pure ASCII: cmd.exe locates the next line
REM  by byte offset, and any multi-byte character (Chinese) desyncs it.
REM  All real logic and all Chinese messages live in scripts\start.ps1,
REM  which PowerShell reads as UTF-8 and prints via the Unicode console API.
REM ---------------------------------------------------------------------

cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\start.ps1"

if errorlevel 1 (
    pause
)
