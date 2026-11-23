@echo off
REM FastWeather City Cache Distribution Script
REM Run from the CityData\ directory.
REM Copies canonical cache files to all platform locations: iOS, webapp, windows.

echo ========================================
echo FastWeather Cache Distribution
echo ========================================
echo.

if not exist "international-cities-cached.json" (
    echo ERROR: international-cities-cached.json not found in CityData\
    echo Run build-international-cache.py first.
    pause
    exit /b 1
)

if not exist "us-cities-cached.json" (
    echo ERROR: us-cities-cached.json not found in CityData\
    echo Run build-city-cache.py first.
    pause
    exit /b 1
)

echo [1/3] iOS...
if not exist "..\iOS\FastWeather\Resources\" (
    echo   SKIPPED: iOS\FastWeather\Resources\ not found
) else (
    copy /Y international-cities-cached.json "..\iOS\FastWeather\Resources\"
    copy /Y us-cities-cached.json "..\iOS\FastWeather\Resources\"
    REM Places of the World is iOS-only for now
    if exist "places-of-the-world.json" copy /Y places-of-the-world.json "..\iOS\FastWeather\Resources\"
    echo   Done: iOS\FastWeather\Resources\
)
echo.

echo [2/3] Web/PWA...
if not exist "..\webapp\" (
    echo   SKIPPED: webapp\ not found
) else (
    copy /Y international-cities-cached.json "..\webapp\"
    copy /Y us-cities-cached.json "..\webapp\"
    echo   Done: webapp\
)
echo.

echo [3/3] Windows...
if not exist "..\windows\" (
    echo   SKIPPED: windows\ not found
) else (
    copy /Y international-cities-cached.json "..\windows\"
    copy /Y us-cities-cached.json "..\windows\"
    echo   Done: windows\
)
echo.

echo ========================================
echo Distribution Complete!
echo ========================================
echo.
echo Next steps:
echo   - iOS: rebuild in Xcode
echo   - Web: hard refresh (Ctrl+Shift+R)
echo   - Windows: run build.py to rebuild .exe
echo.
pause
