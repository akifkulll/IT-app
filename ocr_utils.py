# -*- coding: utf-8 -*-
"""
ocr_utils.py — Taranmış PDF'lerden OCR ile isim çıkarma yardımcı fonksiyonları.

Tüm işlem tamamen offline çalışır (Tesseract + Poppler), bulut OCR kullanılmaz.
"""

import io
import re
import unicodedata
from pathlib import Path

import pytesseract
from pdf2image import convert_from_bytes

# PDF → görüntü dönüşümünde kullanılacak çözünürlük (dpi)
DPI = 300

# Tesseract için Türkçe dil paketi
OCR_DIL = "tur"

# İsim alanını yakalamak için denenecek etiket varyasyonları.
# Etiketten sonra ":" veya boşluk gelebilir; isim aynı satırda aranır.
ISIM_ETIKETLERI = [
    r"Adı\s*Soyadı",
    r"Ad[ıi]\s*[-/]?\s*Soyad[ıi]",
    r"Ad\s*Soyad",
    r"İsim",
    r"Isim",
    r"Name",
]

# Bulunamayan isimler için kullanılacak yer tutucu
ISIM_BULUNAMADI = "isim_bulunamadi"


def metni_cikar(pdf_bytes: bytes) -> str:
    """PDF baytlarını görüntüye çevirir ve OCR ile ham metni döndürür.

    Args:
        pdf_bytes: Yüklenen PDF dosyasının ham baytları.

    Returns:
        Tüm sayfaların OCR metni (sayfalar arasında boş satır ile).
    """
    sayfalar = convert_from_bytes(pdf_bytes, dpi=DPI)
    metinler = []
    for sayfa in sayfalar:
        metin = pytesseract.image_to_string(sayfa, lang=OCR_DIL)
        metinler.append(metin)
    return "\n\n".join(metinler)


def ismi_bul(metin: str) -> str | None:
    """OCR metninde isim alanını etiket varyasyonlarıyla arar.

    Etiket satırındaki isim kısmını döndürür; bulamazsa None döner.
    """
    for etiket in ISIM_ETIKETLERI:
        # Etiket + isteğe bağlı ":" / "=" + aynı satırdaki isim
        desen = rf"{etiket}\s*[:=\-]?\s*(?P<isim>[^\n\r]+)"
        eslesme = re.search(desen, metin, flags=re.IGNORECASE)
        if eslesme:
            aday = eslesme.group("isim").strip()
            # OCR gürültüsünü ayıkla: sadece harf, boşluk ve tire bırak
            aday = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü\s\-]", " ", aday)
            aday = re.sub(r"\s+", " ", aday).strip()
            # Çok kısa veya boş sonuçları geçersiz say
            if len(aday) >= 2:
                return aday
    return None


def temiz_isim(isim: str) -> str:
    """İsmi dosya adı için güvenli hale getirir.

    - Yasak/riskli karakterleri temizler
    - Boşlukları alt çizgiye çevirir
    - Türkçe karakterleri korur
    """
    # Unicode normalizasyonu (birleşik karakterleri düzelt)
    isim = unicodedata.normalize("NFC", isim)
    # Dosya sistemlerinde sorun çıkaran karakterleri kaldır
    isim = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", isim)
    # Boşlukları alt çizgiye çevir
    isim = re.sub(r"\s+", "_", isim.strip())
    # Baş/son nokta ve alt çizgileri temizle
    isim = isim.strip("._")
    return isim or ISIM_BULUNAMADI


def benzersiz_ad(isim: str, kullanilanlar: set[str]) -> str:
    """Aynı isim tekrar ederse sonuna _1, _2 ... ekleyerek çakışmayı önler.

    Args:
        isim: Temizlenmiş dosya adı (uzantısız).
        kullanilanlar: Bu oturumda zaten kullanılan adlar kümesi
                       (fonksiyon seçilen adı bu kümeye ekler).
    """
    aday = isim
    sayac = 1
    while aday in kullanilanlar:
        aday = f"{isim}_{sayac}"
        sayac += 1
    kullanilanlar.add(aday)
    return aday


def kaydet(pdf_bytes: bytes, dosya_adi: str, cikti_klasoru: str = "cikti") -> Path:
    """PDF baytlarını cikti/<dosya_adi>.pdf olarak diske kaydeder.

    Returns:
        Kaydedilen dosyanın yolu.
    """
    klasor = Path(cikti_klasoru)
    klasor.mkdir(parents=True, exist_ok=True)
    hedef = klasor / f"{dosya_adi}.pdf"
    # PDF ikili (binary) veridir; doğrudan baytları yazıyoruz
    with open(hedef, "wb") as f:
        f.write(pdf_bytes)
    return hedef


def pdf_isle(pdf_bytes: bytes) -> dict:
    """Tek bir PDF için tüm OCR akışını çalıştırır.

    Returns:
        {"ham_metin": str, "isim": str | None, "hata": str | None}
    """
    try:
        ham_metin = metni_cikar(pdf_bytes)
        isim = ismi_bul(ham_metin)
        return {"ham_metin": ham_metin, "isim": isim, "hata": None}
    except Exception as e:  # Bozuk bir belge tüm işlemi durdurmasın
        return {"ham_metin": "", "isim": None, "hata": str(e)}
