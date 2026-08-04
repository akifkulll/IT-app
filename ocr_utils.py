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
# Sıra önemlidir: en güvenilir/özel etiketler başta aranır.
# Etiketten sonra ":" veya boşluk gelebilir; isim aynı satırda ya da
# (aynı satırda yoksa) bir alt satırda aranır.
ISIM_ETIKETLERI = [
    r"Kullanıcı\s*Adı",
    r"Kullanıcı",
    r"Kullanici",
    r"User\s*Name",
    r"User",
    r"Adı\s*Soyadı",
    r"Ad[ıi]\s*[-/]?\s*Soyad[ıi]",
    r"Ad\s*Soyad",
    r"İsim\s*[-/]?\s*Soyisim",
    r"Isim\s*[-/]?\s*Soyisim",
    r"Name\s*[-/]?\s*Surname",
    r"İsim",
    r"Isim",
    r"Name",
]

# Kişi ismi OLMAYAN, form başlıklarında/alan adlarında geçen kelimeler.
# Yakalanan aday yalnızca bu kelimelerden oluşuyorsa geçersiz sayılır;
# böylece "Model Serial Number" gibi başlıklar isim olarak alınmaz.
GECERSIZ_KELIMELER = {
    "model", "serial", "number", "seri", "numara", "no", "sn",
    "name", "surname", "user", "kullanıcı", "kullanici", "adı", "ad",
    "soyad", "soyadı", "soyisim", "isim", "tarih", "date", "departman", "department",
    "unvan", "title", "id", "tc", "kimlik", "telefon", "phone", "email",
}

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


def _adayi_temizle(metin: str) -> str:
    """Ham bir metin parçasından isim adayını ayıklar.

    Sadece harf, boşluk ve tire bırakır; fazla boşlukları teker.
    """
    metin = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü\s\-]", " ", metin)
    metin = re.sub(r"\s+", " ", metin).strip()
    return metin


# Etiketin altında isim ararken en fazla kaç DOLU satıra bakılacağı.
# Kutulu formlarda OCR, etiketle kutudaki değerin arasına çizgi/başlık
# satırları sokabildiği için 1 satır yetmiyor.
ALT_SATIR_LIMITI = 4


def _isim_ayikla(aday: str) -> str | None:
    """Adaydan geçerli kişi ismini ayıklar; yoksa None döner.

    - Baştaki başlık/etiket kelimelerini ("Name", "Surname", "İsim"...)
      atar: "Name Surname Ahmet Yılmaz" -> "Ahmet Yılmaz".
    - Kalan kelimelerin tamamı başlık kelimesiyse ya da makul bir isim
      uzunluğunda değilse (1-5 kelime) geçersiz sayar.
    """
    # Hiç harf içermeyen parçaları at (kutu çizgileri: '----', '__' vb.)
    kelimeler = [
        k for k in aday.split()
        if re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", k)
    ]
    # Baştaki ve sondaki başlık kelimelerini / tek harfli artıkları soy
    while kelimeler and (
        kelimeler[0].lower() in GECERSIZ_KELIMELER or len(kelimeler[0]) < 2
    ):
        kelimeler = kelimeler[1:]
    while kelimeler and (
        kelimeler[-1].lower() in GECERSIZ_KELIMELER or len(kelimeler[-1]) < 2
    ):
        kelimeler = kelimeler[:-1]
    if not kelimeler:
        return None
    # Kalan kısımda hâlâ başlık kelimesi varsa bu bir isim değil, başlıktır
    if any(k.lower() in GECERSIZ_KELIMELER for k in kelimeler):
        return None
    # Makul isim uzunluğu: 1-5 kelime (paragraf/serbest metin yakalamayalım)
    if len(kelimeler) > 5:
        return None
    isim = " ".join(kelimeler)
    return isim if len(isim) >= 2 else None


def ismi_bul(metin: str) -> str | None:
    """OCR metninde isim alanını etiket varyasyonlarıyla arar.

    Her etiket için önce aynı satırda etiketten sonra gelen kısma bakar;
    orada geçerli bir isim yoksa (boş ya da başlık kelimesi) altındaki
    birkaç dolu satırı dener — kutulu formlarda OCR ismi etiketten birkaç
    satır sonraya yazabilir. Bulamazsa None döner.
    """
    satirlar = metin.splitlines()
    for etiket in ISIM_ETIKETLERI:
        # Etiket + isteğe bağlı ":" / "=" / "-" + satırın kalanı
        desen = re.compile(rf"{etiket}\s*[:=\-]?\s*(?P<isim>.*)", flags=re.IGNORECASE)
        for i, satir in enumerate(satirlar):
            eslesme = desen.search(satir)
            if not eslesme:
                continue

            # 1) Aynı satırda etiketten sonra gelen kısım
            isim = _isim_ayikla(_adayi_temizle(eslesme.group("isim")))
            if isim:
                return isim

            # 2) Etiketin altındaki birkaç dolu satıra bak (kutu içi değer)
            bakilan = 0
            for sonraki in satirlar[i + 1:]:
                aday = _adayi_temizle(sonraki)
                if not aday:
                    continue  # boş satırları atla
                isim = _isim_ayikla(aday)
                if isim:
                    return isim
                bakilan += 1
                if bakilan >= ALT_SATIR_LIMITI:
                    break  # bu eşleşmeden vazgeç, diğerlerini dene
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
