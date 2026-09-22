@echo off
REM ---------------------------------------------------------------------
REM  Double-click this file to start the app in DEVELOPMENT mode.
REM
REM    backend  -> http://127.0.0.1:8000  (API only)
REM    frontend -> http://127.0.0.1:5173  (Vite dev server, hot reload)
REM
REM  For the single-process PRODUCTION-style start (build frontend/dist,
REM  serve everything from the backend on port 8000), use the OTHER .bat
REM  file sitting next to this one - the one whose name is NOT ASCII.
REM
REM  This file is deliberately pure ASCII: cmd.exe locates the next line
REM  by byte offset, and any multi-byte character (Chinese) desyncs it.
REM  All real logic and all Chinese messages live in scripts\start-dev.ps1,
REM  which PowerShell reads as UTF-8 and prints via the Unicode console API.
REM ---------------------------------------------------------------------

cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\start-dev.ps1"

if errorlevel 1 (
    pause
)
