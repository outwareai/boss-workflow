@echo off
REM Run load tests in sequence (Windows version)
echo Starting Boss Workflow Load Tests
echo ==================================
echo.

REM Check if LOAD_TEST_HOST is set
if "%LOAD_TEST_HOST%"=="" (
    echo LOAD_TEST_HOST not set, using default: http://localhost:8000
    set LOAD_TEST_HOST=http://localhost:8000
) else (
    echo Target: %LOAD_TEST_HOST%
)

echo.

REM Make reports directory
if not exist tests\load\reports mkdir tests\load\reports

REM Run benchmarks first
echo Running performance benchmarks...
python tests\load\benchmark.py %LOAD_TEST_HOST%

echo.
echo ==================================
echo Starting Load Test Scenarios
echo ==================================

REM Light load (warmup)
echo.
echo Running light load test (100 users)...
python tests\load\scenarios.py light

REM Medium load
echo.
echo Running medium load test (500 users)...
python tests\load\scenarios.py medium

REM Heavy load (target: 1000 req/min)
echo.
echo Running heavy load test (1000 users)...
python tests\load\scenarios.py heavy

REM Spike test
echo.
echo Running spike test (2000 users)...
python tests\load\scenarios.py spike

echo.
echo ==================================
echo Load tests complete!
echo ==================================
echo Reports available in tests\load\reports\
echo.
echo Generated files:
dir /b tests\load\reports\
