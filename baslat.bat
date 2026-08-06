@echo off
REM ============================================================
REM  Windows baslatici: bu dosyaya CIFT TIKLAYINCA uygulamayi acar.
REM ============================================================

REM Bu dosyanin bulundugu klasore gec
cd /d "%~dp0"

echo ==============================================
echo  PDF Isim Cikarma - Uygulama baslatiliyor...
echo ==============================================
echo.

REM Python var mi kontrol et
python --version >nul 2>nul
if errorlevel 1 (
    echo [HATA] Python bulunamadi.
    echo Lutfen python.org adresinden Python kurun
    echo ve kurulumda "Add Python to PATH" kutusunu isaretleyin.
    echo.
    pause
    exit /b 1
)

REM Streamlit kurulu mu kontrol et; degilse bagimliliklari yukle
python -m streamlit --version >nul 2>nul
if errorlevel 1 (
    echo Bagimliliklar yukleniyor (ilk kurulum, biraz surebilir)...
    python -m pip install -r requirements.txt
    echo.
)

REM Uygulamayi baslat (tarayici otomatik acilir)
REM  'python -m streamlit', 'streamlit' komutu PATH'te olmasa da calisir
python -m streamlit run app.py

pause
