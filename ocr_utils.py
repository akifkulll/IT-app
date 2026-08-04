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
from PIL import Image, ImageFilter, ImageOps

# PDF → görüntü dönüşümünde kullanılacak çözünürlük (dpi)
DPI = 300

# İkinci OCR turunda kullanılan yüksek çözünürlük — harf netliğini
# artırıp "semet" gibi karışan okumaları düzeltmeye yardımcı olur
DPI_YUKSEK = 400

# Tesseract için Türkçe dil paketi
OCR_DIL = "tur"

# İsim alanını yakalamak için denenecek etiket varyasyonları.
# Sıra önemlidir: en güvenilir/özel etiketler başta aranır.
# Etiketten sonra ":" veya boşluk gelebilir; isim aynı satırda ya da
# (aynı satırda yoksa) bir alt satırda aranır.
ISIM_ETIKETLERI = [
    # Önce tam ad-soyad etiketleri (en güvenilir alanlar)
    r"Adı\s*Soyadı",
    r"Ad[ıi]\s*[-/]?\s*Soyad[ıi]",
    r"Ad\s*Soyad",
    r"İsim\s*[-/]?\s*Soyisim",
    r"Isim\s*[-/]?\s*Soyisim",
    r"Name\s*[-/]?\s*Surname",
    # Sonra kullanıcı etiketleri
    r"Kullanıcı\s*Adı",
    r"Kullanıcı",
    r"Kullanici",
    r"User\s*Name",
    r"User",
    # En sona en genel etiketler
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
    # IT teslim formlarındaki alan adları ve OCR bozulmaları
    "cwid", "ewid", "cwid:", "type", "old", "device", "devices",
    "delivered", "cause", "change", "imei", "imel", "inventory",
    "envanter", "kodu", "cihaz", "eski", "teslim", "form", "formu", "ve",
    "web", "www", "http", "https",
}

# Bulunamayan isimler için kullanılacak yer tutucu
ISIM_BULUNAMADI = "isim_bulunamadi"

# Belge türüne göre dosya adının sonuna eklenecek kodlar.
# Sıra önemlidir: ilk eşleşen kazanır.
#
# Notlar:
# - \b (tam kelime sınırı) ile 'Delivery', gövdedeki 'Delivered' kelimesine
#   yanlışlıkla eşleşmez.
# - 'Delivery' için (?!\s*Form) ile, IT formunun BAŞLIĞINDAKİ
#   "... Equipment Delivery Form" ifadesi D tetiklemez; yalnızca tür
#   alanındaki gerçek "Delivery" değeri D verir.
# - IT formu başlığı ('IT Ekipman ... / IT Equipment Delivery Form') hem
#   Türkçe hem İngilizce yazımıyla ve OCR'ın 'IT' okuma hatalarından
#   bağımsız olarak 'Ekipman Teslim' / 'Equipment Delivery' üzerinden
#   yakalanır.
# Pickup deseni, Türkçe OCR (lang=tur) yüzünden oluşan yazım
# kaymalarına dayanıklı: i<->ı, c<->ç, k<->l, u<->ü karışabilir.
# Örn: Pickup, Pick up, Pick-up, Pıckup, Piçkup, Picküp, Piclup...
PICKUP_DESENI = r"\bP[iı][cçk][cçkl]?\s*-?\s*[uü]p\b"

BELGE_KODLARI = [
    (r"\bMobile\b", "M"),
    (PICKUP_DESENI, "P"),
    (r"Ekipman\s+Teslim|Equipment\s+Delivery|[İIı1l]T\s+Ekipman|[İIı1l]T\s+Equipment", "IT"),
    (r"(?<!Equipment )\bDelivery\b", "D"),
]


def belge_kodu(metin: str) -> str | None:
    """OCR metnine göre belge türü kodunu döndürür (M/P/D/IT); yoksa None.

    Dosya adının sonuna '_<kod>' olarak eklenmek üzere kullanılır.
    """
    for desen, kod in BELGE_KODLARI:
        if re.search(desen, metin, flags=re.IGNORECASE):
            return kod
    return None


def _on_isle(gorsel, buyut: float = 1.0, ikili: bool = False):
    """OCR öncesi görüntü iyileştirme.

    Soluk/renkli kutulardaki yazıların okunabilmesi için: gri tona çevir,
    (isteğe bağlı) büyüt, kontrastı aç, keskinleştir; istenirse siyah-beyaz
    eşikleme (binarizasyon) uygula.

    Args:
        buyut: Büyütme oranı. 1.0 = büyütme yok.
        ikili: True ise görüntü siyah-beyaza eşiklenir. Basılı yazıda
            harf kenarlarını netleştirip karışan harfleri ('semet' gibi)
            düzeltebilir.
    """
    gorsel = gorsel.convert("L")  # gri ton
    if buyut != 1.0:
        gorsel = gorsel.resize(
            (int(gorsel.width * buyut), int(gorsel.height * buyut)),
            Image.LANCZOS,
        )
    gorsel = ImageOps.autocontrast(gorsel, cutoff=2)  # kontrastı aç
    if ikili:
        # 150 eşiği: bu değerin altı siyah (yazı), üstü beyaz (zemin)
        gorsel = gorsel.point(lambda p: 0 if p < 150 else 255, mode="L")
    gorsel = gorsel.filter(ImageFilter.SHARPEN)  # keskinleştir
    return gorsel


def _sayfalari_oku(sayfalar, config: str = "") -> str:
    """Verilen sayfa görüntülerini OCR'dan geçirip birleşik metni döndürür."""
    return "\n\n".join(
        pytesseract.image_to_string(s, lang=OCR_DIL, config=config)
        for s in sayfalar
    )


def metni_cikar(pdf_bytes: bytes, iyilestir: bool = False) -> str:
    """PDF baytlarını görüntüye çevirir ve OCR ile ham metni döndürür.

    Args:
        pdf_bytes: Yüklenen PDF dosyasının ham baytları.
        iyilestir: True ise görüntü ön işlemden geçirilir ve tablo/kutu
            düzenini daha iyi çözen OCR modu (--psm 6) kullanılır.

    Returns:
        Tüm sayfaların OCR metni (sayfalar arasında boş satır ile).
    """
    sayfalar = convert_from_bytes(pdf_bytes, dpi=DPI)
    if iyilestir:
        sayfalar = [_on_isle(s) for s in sayfalar]
        return _sayfalari_oku(sayfalar, "--psm 6")
    return _sayfalari_oku(sayfalar)


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
ALT_SATIR_LIMITI = 6


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
        kelimeler[-1].lower() in GECERSIZ_KELIMELER
        or len(kelimeler[-1]) < 2
        # Sondaki kısa ve TAMAMEN büyük harfli parçalar kod artığıdır
        # (kullanıcı kodu 'AK123C' -> 'AK' gibi); gerçek soyadlar daha uzun
        or (len(kelimeler[-1]) <= 3 and kelimeler[-1].isupper() and len(kelimeler) > 1)
        # Küçük harfle başlayan kısa parçalar OCR gürültüsüdür ('ii', 'web'
        # gibi) — gerçek isim/soyisim büyük harfle başlar
        or (len(kelimeler[-1]) <= 3 and kelimeler[-1][0].islower() and len(kelimeler) > 1)
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
    # Tek kelimelik aday en az 3 harf olmalı (kod artıkları: 'AK' gibi)
    if len(kelimeler) == 1 and len(kelimeler[0]) < 3:
        return None
    return " ".join(kelimeler)


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
                # Başka bir alanın etiketiyle başlayan satırları atla
                # ("CWID: A123", "Model: XPS" gibi) — o alanın değeri
                # isim değildir
                etiket_m = re.match(
                    r"\s*([A-Za-zÇĞİÖŞÜçğıöşü]+)\s*[:=]", sonraki
                )
                # Rakam ağırlıklı satırlar da kimlik/kod değeridir (CWID,
                # seri no vb.), isim olamaz — atla
                harf = sum(c.isalpha() for c in sonraki)
                rakam = sum(c.isdigit() for c in sonraki)
                if (etiket_m and etiket_m.group(1).lower() in GECERSIZ_KELIMELER) or (
                    rakam > 0 and rakam >= harf
                ):
                    bakilan += 1
                    if bakilan >= ALT_SATIR_LIMITI:
                        break
                    continue
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
        {"ham_metin": str, "isim": str | None, "kod": str | None,
         "hata": str | None}
        kod: belge türü soneki (M/P/D/IT) veya None.
    """
    try:
        # 1. deneme: normal OCR
        sayfalar = convert_from_bytes(pdf_bytes, dpi=DPI)
        ham_metin = _sayfalari_oku(sayfalar)
        isim = ismi_bul(ham_metin)

        # İsim bulunamadıysa: sayfayı daha yüksek çözünürlükte (400 dpi)
        # yeniden render edip çeşitli iyileştirme + OCR modu varyantlarını
        # dener. Harf netliği için binarizasyonlu varyantlar başta tutulur;
        # ilk isim bulan varyant kazanır.
        # (buyut_orani, binarize, psm_modu):
        if isim is None:
            yuksek_sayfalar = convert_from_bytes(pdf_bytes, dpi=DPI_YUKSEK)
            varyantlar = [
                (1.0, True, "--psm 6"),    # binarize + tek metin bloğu
                (1.5, True, "--psm 6"),    # 1.5x + binarize
                (1.0, False, "--psm 6"),   # binarizesiz (güvenli geri dönüş)
                (1.0, False, "--psm 4"),   # sütunlu düzen
                (2.0, False, "--psm 6"),   # 2x büyütme
            ]
            for buyut, ikili, config in varyantlar:
                iyi_sayfalar = [
                    _on_isle(s, buyut, ikili) for s in yuksek_sayfalar
                ]
                ham_metin2 = _sayfalari_oku(iyi_sayfalar, config)
                bulunan = ismi_bul(ham_metin2)
                if bulunan is not None:
                    isim = bulunan
                    ham_metin = ham_metin2  # başarılı okumayı göster
                    break

        # Belge türü kodunu (M/P/D/IT) çıkarılan metinden belirle
        kod = belge_kodu(ham_metin)

        return {"ham_metin": ham_metin, "isim": isim, "kod": kod, "hata": None}
    except Exception as e:  # Bozuk bir belge tüm işlemi durdurmasın
        return {"ham_metin": "", "isim": None, "kod": None, "hata": str(e)}
