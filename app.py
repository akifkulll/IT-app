# -*- coding: utf-8 -*-
"""
app.py — Taranmış PDF'lerden isim çıkarıp otomatik kaydeden Streamlit uygulaması.

Akış:
1. Kullanıcı bir veya birden fazla taranmış PDF yükler.
2. Her PDF için OCR (Tesseract, Türkçe) çalıştırılır ve "isim" alanı aranır.
3. Kullanıcı, kaydetmeden ÖNCE çıkarılan isimleri tabloda düzenleyebilir.
4. Onaylanan isimlerle dosyalar cikti/<temiz_isim>.pdf olarak kaydedilir.

Tüm işlem offline'dır; hiçbir veri buluta gönderilmez.
"""

import pandas as pd
import streamlit as st

from ocr_utils import (
    ISIM_BULUNAMADI,
    benzersiz_ad,
    kaydet,
    pdf_isle,
    temiz_isim,
)

st.set_page_config(page_title="PDF İsim Çıkarma", page_icon="📄", layout="wide")

st.title("📄 Taranmış PDF'lerden İsim Çıkarma ve Yeniden Adlandırma")
st.caption(
    "PDF'ler OCR ile okunur, isim alanı yakalanır ve dosyalar o isimle "
    "`cikti/` klasörüne kaydedilir. Tüm işlem **offline** çalışır."
)

# ---------------------------------------------------------------------------
# 1) Dosya yükleme
# ---------------------------------------------------------------------------
dosyalar = st.file_uploader(
    "Taranmış PDF dosyalarını seçin",
    type=["pdf"],
    accept_multiple_files=True,
)

# Oturum durumu: OCR sonuçlarını sakla ki her etkileşimde OCR tekrarlanmasın
if "sonuclar" not in st.session_state:
    st.session_state["sonuclar"] = None

# ---------------------------------------------------------------------------
# 2) OCR işlemi
# ---------------------------------------------------------------------------
if dosyalar and st.button("🔍 OCR Başlat", type="primary"):
    sonuclar = []
    ilerleme = st.progress(0, text="OCR çalışıyor...")

    for i, dosya in enumerate(dosyalar):
        ilerleme.progress((i + 1) / len(dosyalar), text=f"İşleniyor: {dosya.name}")
        pdf_bytes = dosya.getvalue()
        sonuc = pdf_isle(pdf_bytes)
        sonuclar.append(
            {
                "orijinal_ad": dosya.name,
                "pdf_bytes": pdf_bytes,
                "ham_metin": sonuc["ham_metin"],
                "isim": sonuc["isim"],
                "hata": sonuc["hata"],
            }
        )

    ilerleme.empty()
    st.session_state["sonuclar"] = sonuclar

sonuclar = st.session_state["sonuclar"]

# ---------------------------------------------------------------------------
# 3) OCR sonuçlarını göster + isim düzenleme
# ---------------------------------------------------------------------------
if sonuclar:
    st.subheader("1️⃣ OCR Sonuçları ve Doğrulama")
    st.info(
        "OCR hatalı okuyabilir. Aşağıda her belgenin ham OCR metnini kontrol edin "
        "ve gerekirse tabloda isimleri elle düzeltin."
    )

    # Ham OCR metinlerini belge belge göster (kullanıcı doğrulasın)
    for s in sonuclar:
        with st.expander(f"📃 {s['orijinal_ad']} — ham OCR metni"):
            if s["hata"]:
                st.error(f"Hata: {s['hata']}")
            elif s["ham_metin"].strip():
                st.text(s["ham_metin"])
            else:
                st.warning("OCR hiç metin çıkaramadı.")

    # Düzenlenebilir tablo: kullanıcı kaydetmeden önce isimleri düzeltebilir
    tablo = pd.DataFrame(
        [
            {
                "Orijinal Dosya": s["orijinal_ad"],
                "Çıkarılan İsim": s["isim"] if s["isim"] else ISIM_BULUNAMADI,
            }
            for s in sonuclar
        ]
    )

    st.subheader("2️⃣ İsimleri Düzenle (kaydetmeden önce)")
    duzenlenmis = st.data_editor(
        tablo,
        column_config={
            "Orijinal Dosya": st.column_config.TextColumn(disabled=True),
            "Çıkarılan İsim": st.column_config.TextColumn(
                help="Dosya bu isimle kaydedilecek. Elle düzeltebilirsiniz."
            ),
        },
        hide_index=True,
        use_container_width=True,
        key="isim_tablosu",
    )

    # -----------------------------------------------------------------------
    # 4) Kaydetme
    # -----------------------------------------------------------------------
    st.subheader("3️⃣ Kaydet")
    if st.button("💾 Dosyaları Kaydet (cikti/ klasörüne)"):
        rapor = []
        kullanilanlar: set[str] = set()

        for s, (_, satir) in zip(sonuclar, duzenlenmis.iterrows()):
            girilen_isim = str(satir["Çıkarılan İsim"]).strip()
            try:
                if s["hata"]:
                    raise RuntimeError(f"OCR hatası: {s['hata']}")

                guvenli = temiz_isim(girilen_isim)
                dosya_adi = benzersiz_ad(guvenli, kullanilanlar)
                yol = kaydet(s["pdf_bytes"], dosya_adi)

                rapor.append(
                    {
                        "Orijinal Dosya": s["orijinal_ad"],
                        "Çıkarılan İsim": girilen_isim,
                        "Yeni Dosya Adı": yol.name,
                        "Durum": "✅ Başarılı",
                    }
                )
            except Exception as e:  # Tek bir hata tüm kaydetmeyi durdurmasın
                rapor.append(
                    {
                        "Orijinal Dosya": s["orijinal_ad"],
                        "Çıkarılan İsim": girilen_isim,
                        "Yeni Dosya Adı": "-",
                        "Durum": f"❌ Hata: {e}",
                    }
                )

        st.subheader("📊 Sonuç Raporu")
        st.dataframe(pd.DataFrame(rapor), hide_index=True, use_container_width=True)

        basarili = sum(1 for r in rapor if r["Durum"].startswith("✅"))
        st.success(f"{basarili}/{len(rapor)} dosya `cikti/` klasörüne kaydedildi.")
else:
    st.info("Başlamak için yukarıdan bir veya birden fazla PDF yükleyin.")
