@echo off

if exist venv (
    echo Virtual environment already exists.
) else (
    echo Creating Python 3.10 virtual environment...
    py -3.10 -m venv venv
)

call venv\Scripts\activate.bat

echo.
echo Virtual environment is active.
cmd /k