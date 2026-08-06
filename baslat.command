#!/bin/bash
# macOS başlatıcı: Finder'da bu dosyaya ÇİFT TIKLAYINCA uygulamayı açar.
# İlk kullanımdan önce çalıştırma izni ver:  chmod +x baslat.command

# Bu betiğin bulunduğu klasöre geç (nereden açılırsa açılsın doğru yer)
cd "$(dirname "$0")" || exit 1

echo "=============================================="
echo " PDF İsim Çıkarma - Uygulama başlatılıyor..."
echo "=============================================="

# Streamlit kurulu değilse bağımlılıkları yükle
if ! command -v streamlit >/dev/null 2>&1; then
    echo "Streamlit bulunamadı. Bağımlılıklar yükleniyor (ilk kurulum)..."
    pip3 install -r requirements.txt
fi

# Uygulamayı başlat (tarayıcı otomatik açılır)
streamlit run app.py
