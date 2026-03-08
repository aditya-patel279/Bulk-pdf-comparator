@echo off
setlocal

echo ================================================
echo   Bulk PDF Comparator  ^|  EXE Build Script
echo ================================================
echo.

:: ── Step 1: install / upgrade PyInstaller ───────────────────────────────────
echo [1/3] Installing PyInstaller ...
pip install --upgrade pyinstaller
if %errorlevel% neq 0 (
    echo.
    echo ERROR: pip install failed. Make sure Python is on your PATH.
    pause
    exit /b 1
)

:: ── Step 2: clean previous build artefacts ──────────────────────────────────
echo.
echo [2/3] Cleaning previous build ...
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist

:: ── Step 3: run PyInstaller with the spec file ──────────────────────────────
echo.
echo [3/3] Building executable (this may take several minutes) ...
pyinstaller run_app.spec
if %errorlevel% neq 0 (
    echo.
    echo ERROR: PyInstaller build failed. See output above for details.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   BUILD COMPLETE
echo ================================================
echo.
echo   Executable folder:  dist\BulkPDFComparator\
echo   Launch file:        dist\BulkPDFComparator\BulkPDFComparator.exe
echo.
echo   To share with users:
echo     Zip the entire  dist\BulkPDFComparator\  folder.
echo     Users unzip it anywhere and double-click BulkPDFComparator.exe.
echo     No Python installation required on their machine.
echo.
pause
endlocal
