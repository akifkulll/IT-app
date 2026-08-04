@echo off
REM Windows başlatıcı: bu dosyaya ÇİFT TIKLAYINCA uygulamayı açar.

REM Bu dosyanın bulunduğu klasöre geç
cd /d "%~dp0"

echo ==============================================
echo  PDF Isim Cikarma - Uygulama baslatiliyor...
echo ==============================================

REM Streamlit kurulu degilse bagimliliklari yukle
where streamlit >nul 2>nul
if errorlevel 1 (
    echo Streamlit bulunamadi. Bagimliliklar yukleniyor...
    pip install -r requirements.txt
)

REM Uygulamayi baslat (tarayici otomatik acilir)
streamlit run app.py

pause
