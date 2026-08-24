# 📄 Taranmış PDF'lerden İsim Çıkarma ve Otomatik Kaydetme

Taranmış (görüntü tabanlı) PDF belgelerinden, "isim" alanındaki kişi adını
OCR ile okuyup her belgeyi o isimle yeniden adlandırarak `cikti/` klasörüne
kaydeden bir **Streamlit** web uygulaması.

> 🔒 **Gizlilik:** Tüm işlem tamamen **offline** çalışır (Tesseract + Poppler).
> Hiçbir belge buluta gönderilmez.

## Özellikler

- Birden fazla PDF'i aynı anda yükleme
- Türkçe OCR (`lang="tur"`, 300 dpi)
- İsim etiketi varyasyonlarını tanıma: **Ad Soyad**, **İsim**, **Adı Soyadı**, **Name**
- Ham OCR metnini arayüzde gösterme (doğrulama için)
- Kaydetmeden önce isimleri tabloda **elle düzeltme** (`st.data_editor`)
- Dosya adı çakışmalarında otomatik `_1`, `_2` ekleme
- İsmi bulunamayan belgeleri `isim_bulunamadi` olarak raporlama
- Sonuç tablosu: orijinal ad, çıkarılan isim, yeni ad, durum

## Kurulum (Ubuntu 22.04)

### 1. Sistem bağımlılıkları

```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-tur poppler-utils
```

- `tesseract-ocr` — OCR motoru
- `tesseract-ocr-tur` — Türkçe dil paketi
- `poppler-utils` — PDF → görüntü dönüşümü (pdf2image için)

### 2. Python bağımlılıkları

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Kurulum (macOS)

```bash
# Homebrew ile sistem araçları (Türkçe dil paketi tesseract-lang içinde)
brew install tesseract tesseract-lang poppler
# Python bağımlılıkları
pip3 install -r requirements.txt
```

## Kurulum (Windows)

Windows'ta iki sistem programı (Tesseract ve Poppler) ayrıca gerekir.
Uygulama bunları **PATH'e eklemeye gerek olmadan** şu yerlerden otomatik
bulur: `POPPLER_PATH` / `TESSERACT_PATH` ortam değişkenleri, proje
klasöründeki `poppler` / `tesseract` klasörleri, veya bilinen kurulum
yolları.

### 1. Poppler (PATH'siz, taşınabilir)
- İndir: https://github.com/oschwartz10612/poppler-windows/releases
- ZIP'i aç ve içindeki klasörü proje köküne **`poppler`** adıyla koy.
  Sonuçta `poppler/Library/bin` yolu oluşmalı. Uygulama bunu kendi bulur.

### 2. Tesseract (Türkçe dil paketiyle)
- İndir: https://github.com/UB-Mannheim/tesseract/wiki
- Kurulumda **"Additional language data" → Turkish** seçili olsun.
- Varsayılan yere (`C:\Program Files\Tesseract-OCR`) kurulursa uygulama
  otomatik bulur. (Kuramıyorsan taşınabilir kopyayı proje köküne
  `tesseract` klasörü olarak koyabilirsin.)

### 3. Python bağımlılıkları
```powershell
python -m pip install -r requirements.txt
```

### 4. Çalıştır
`baslat.bat` dosyasına çift tıkla veya:
```powershell
python -m streamlit run app.py
```

## Çalıştırma

```bash
streamlit run app.py
```

Tarayıcıda `http://localhost:8501` adresi açılır.

## Kullanım

1. Bir veya birden fazla taranmış PDF yükleyin.
2. **🔍 OCR Başlat** düğmesine tıklayın.
3. Her belgenin ham OCR metnini ve çıkarılan ismi kontrol edin.
4. Gerekirse tabloda isimleri elle düzeltin.
5. **💾 Dosyaları Kaydet** düğmesine tıklayın — dosyalar
   `cikti/<temiz_isim>.pdf` olarak kaydedilir.

## Proje Yapısı

```
.
├── app.py            # Streamlit arayüzü (ana uygulama)
├── ocr_utils.py      # OCR ve dosya yardımcı fonksiyonları
├── requirements.txt  # Python bağımlılıkları
├── README.md
└── cikti/            # Kaydedilen PDF'ler (çalışma sırasında oluşur)
```

## Yardımcı Fonksiyonlar (`ocr_utils.py`)

| Fonksiyon | Görev |
|---|---|
| `metni_cikar(pdf_bytes)` | PDF'i 300 dpi görüntüye çevirir, Türkçe OCR uygular |
| `ismi_bul(metin)` | Etiket varyasyonlarıyla regex araması yapar |
| `temiz_isim(isim)` | Yasak karakterleri temizler, boşlukları `_` yapar |
| `benzersiz_ad(isim, kullanilanlar)` | Çakışmada `_1`, `_2` ekler |
| `kaydet(pdf_bytes, dosya_adi)` | `cikti/` klasörüne yazar |
| `pdf_isle(pdf_bytes)` | Tek PDF için tüm akışı hata yönetimiyle çalıştırır |
