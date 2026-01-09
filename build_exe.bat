@echo off
echo Building Merchant Macro EXE...
echo.
echo Installing PyInstaller if not already installed...
pip install pyinstaller
echo.
echo Building EXE file...
pyinstaller --onefile --windowed --icon=NONE --name="MerchantMacro" MerchantGPO.py
echo.
echo Done! Check the 'dist' folder for MerchantMacro.exe
pause