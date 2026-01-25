@echo off
REM ###############################################################################
REM # Pre-Deployment Smoke Tests (Windows Batch)
REM #
REM # This script runs critical smoke tests before deploying to production.
REM # If ANY critical test fails, deployment is BLOCKED.
REM #
REM # Usage:
REM #   pre_deploy_check.bat          # Run all smoke tests
REM #   pre_deploy_check.bat verbose  # Show detailed output
REM #
REM # Exit codes:
REM #   0 = All tests passed - safe to deploy
REM #   1 = One or more tests failed - BLOCKING deployment
REM ###############################################################################

setlocal enabledelayedexpansion

set VERBOSE=%1
set RED=[31m
set GREEN=[32m
set YELLOW=[33m
set NC=[0m

echo.
echo ==========================================
echo PRE-DEPLOYMENT SMOKE TESTS
echo ==========================================
echo.

REM Check if pytest is installed
pytest --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pytest not found
    echo Install with: pip install -r requirements.txt
    exit /b 1
)

REM Run critical intent tests
echo Running critical intent smoke tests...
echo.

set PYTEST_ARGS=-q --tb=short
if "%VERBOSE%"=="verbose" (
    set PYTEST_ARGS=-v --tb=short
)

pytest tests\smoke\test_critical_intents.py %PYTEST_ARGS%
set SMOKE_RESULT=%errorlevel%

echo.
echo ==========================================

if %SMOKE_RESULT% equ 0 (
    echo [32mCheckmark ALL CRITICAL TESTS PASSED[0m
    echo Status: Safe to deploy
    echo ==========================================
    exit /b 0
) else (
    echo [31mX CRITICAL TESTS FAILED[0m
    echo Status: BLOCKING DEPLOYMENT
    echo.
    echo Action required:
    echo 1. Review test output above
    echo 2. Fix failing tests
    echo 3. Run this script again
    echo 4. Once tests pass, deployment will proceed
    echo ==========================================
    exit /b 1
)
