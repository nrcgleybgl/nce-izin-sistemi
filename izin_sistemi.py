import streamlit as st
import pandas as pd
from datetime import date, timedelta
import psycopg2
import psycopg2.extras
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from io import BytesIO
from fpdf import FPDF

from dotenv import load_dotenv
import os

load_dotenv()

# ---------------------------------------------------
# EXCEL İNDİRME FONKSİYONU
# ---------------------------------------------------
def excel_indir(df, dosya_adi="rapor.xlsx"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name="Sayfa1")
    return output.getvalue()

# ---------------------------------------------------
# PDF OLUŞTURMA FONKSİYONU
# ---------------------------------------------------
def pdf_olustur(veri, logo_path="assets/logo.png"):
    pdf = FPDF()
    pdf.add_page()

    def fix(metin):
        if metin is None:
            return ""
        karakterler = {
            'ğ': 'g', 'Ğ': 'G', 'ş': 's', 'Ş': 'S',
            'İ': 'I', 'ı': 'i', 'ç': 'c', 'Ç': 'C',
            'ö': 'o', 'Ö': 'O', 'ü': 'u', 'Ü': 'U'
        }
        for eski, yeni in karakterler.items():
            metin = metin.replace(eski, yeni)
        return metin

    try:
        pdf.image(logo_path, x=80, y=10, w=50)
    except:
        pass

    pdf.ln(35)
    pdf.set_font("Arial", 'B', 18)
    pdf.cell(0, 10, fix("IZIN TALEP FORMU"), ln=True, align='C')
    pdf.ln(5)

    def kutu_baslik(baslik):
        pdf.set_font("Arial", 'B', 12)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(190, 8, fix(baslik), ln=True, fill=True)

    def satir(label, value):
        pdf.set_font("Arial", size=11)
        pdf.cell(50, 8, fix(f"{label}:"), border=1)
        pdf.cell(140, 8, fix(str(value)), border=1, ln=True)

    kutu_baslik("PERSONEL BILGILERI")
    satir("Ad Soyad", veri["ad_soyad"])
    satir("Sicil No", veri["sicil"])
    satir("Departman", veri["departman"])
    satir("Gorevi", veri["meslek"])
    satir("Cep Telefonu", veri["telefon"])
    satir("Mail Adresi", veri["email"])
    pdf.ln(5)

    kutu_baslik("IZIN BILGILERI")
    satir("Izin Turu", veri["tip"])
    satir("Baslangic Tarihi", veri["baslangic"])
    satir("Bitis Tarihi", veri["bitis"])

    pdf.set_font("Arial", size=11)
    pdf.cell(50, 8, fix("Izin Nedeni:"), border=1)
    pdf.multi_cell(140, 8, fix(str(veri["neden"])), border=1)
    pdf.ln(5)

    if veri["durum"] == "Onaylandı" and veri["yonetici"]:
        kutu_baslik("YONETICI ONAYI")
        metin = f"Bu izin, {veri['yonetici']} tarafindan {veri['onay_tarihi']} tarihinde onaylanmistir."
        pdf.multi_cell(190, 8, fix(metin), border=1)
        pdf.ln(5)

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(95, 10, fix("Personel Imzasi"), border=1, ln=False, align='C')
    pdf.cell(95, 10, fix("Yonetici Imzasi"), border=1, ln=True, align='C')

    return pdf.output(dest='S').encode('latin-1', errors='ignore')

# ---------------------------------------------------
# GMAIL SMTP (WEB UYUMLU - .env)
# ---------------------------------------------------
def mail_gonder(alici, konu, icerik):
    try:
        gonderen = os.getenv("SMTP_MAIL")
        sifre = os.getenv("SMTP_SIFRE")

        msg = MIMEMultipart()
        msg["From"] = gonderen
        msg["To"] = alici
        msg["Subject"] = konu
        msg.attach(MIMEText(icerik, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(gonderen, sifre)
        server.sendmail(gonderen, alici, msg.as_string())
        server.quit()

    except Exception as e:
        print("Mail gönderilemedi:", e)

import psycopg2
import os
import streamlit as st

# Fonksiyon
def get_db():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        sslmode="require"
    )

# Bağlantıyı oluşturma
try:
    conn = get_db()
    c = conn.cursor()
except Exception as e:
    st.error(f"Veritabanına bağlanılamadı: {e}")

# ---------------------------------------------------
# TABLOLARI OLUŞTUR (PostgreSQL)
# ---------------------------------------------------
c.execute("""
CREATE TABLE IF NOT EXISTS personellers (
    sicil TEXT,
    ad_soyad TEXT,
    sifre TEXT,
    meslek TEXT,
    departman TEXT,
    email TEXT,
    onayci_email TEXT,
    rol TEXT,
    cep_telefonu TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS talepler (
    id SERIAL PRIMARY KEY,
    ad_soyad TEXT,
    departman TEXT,
    meslek TEXT,
    tip TEXT,
    baslangic TEXT,
    bitis TEXT,
    neden TEXT,
    durum TEXT,
    onay_notu TEXT
)
""")

conn.commit()

# ---------------------------------------------------
# PERSONEL VERİSİ OKUMA
# ---------------------------------------------------
def veri_getir():
    try:
        return pd.read_sql_query("SELECT * FROM personellers", conn)
    except:
        return pd.DataFrame()

# ---------------------------------------------------
# STREAMLIT ARAYÜZ
# ---------------------------------------------------
st.set_page_config(page_title="Pro-İK İzin Portalı", layout="wide")

if 'login_oldu' not in st.session_state:
    st.session_state['login_oldu'] = False
    st.session_state['user'] = None

df_p = veri_getir()

if not st.session_state['login_oldu']:
    st.image("assets/logo.png", width=180)
    st.title("🔐 NCE Bordro Danışmanlık ve Eğitim - İK İzin Paneli")

df_p = veri_getir()

if "Ad Soyad" in df_p.columns:
    df_p.rename(columns={"Ad Soyad": "ad_soyad"}, inplace=True)

# ---------------------------------------------------
# GİRİŞ FORMU
# ---------------------------------------------------
if not st.session_state.get("login_oldu", False):

    with st.form("giris_formu"):
        isim = st.text_input("Ad Soyad")
        sifre = st.text_input("Şifre", type="password")

        if st.form_submit_button("Giriş Yap"):
            user_row = df_p[
                (df_p['ad_soyad'] == isim) &
                (df_p['sifre'].astype(str) == sifre)
            ]

            if not user_row.empty:
                st.session_state['login_oldu'] = True
                st.session_state['user'] = user_row.iloc[0]
                st.rerun()
            else:
                st.error("Kullanıcı adı veya şifre hatalı!")
# ---------------------------------------------------
# ANA PANEL
# ---------------------------------------------------
else:
    user = st.session_state['user']
    rol = user.get('rol', 'Personel')

    ana_menu = ["İzin Talep Formu", "İzinlerim (Durum Takip)"]
    if rol in ["Yönetici", "İK"]:
        ana_menu.append("Onay Bekleyenler (Yönetici)")
    if rol == "İK":
        ana_menu.append("Tüm Talepler (İK)")
        ana_menu.append("Personel Yönetimi (İK)")

    st.sidebar.image("assets/logo.png", width=120)
    st.sidebar.title(f"👤 {user['ad_soyad']}")
    st.sidebar.write(f"**Rol:** {rol}")
    st.sidebar.write(f"**Departman:** {user['departman']}")

    menu = st.sidebar.radio("İşlem Menüsü", ana_menu)

    st.sidebar.markdown("---")
    if st.sidebar.button("🔒 Güvenli Çıkış"):
        st.session_state['login_oldu'] = False
        st.session_state['user'] = None
        st.rerun()

    # ---------------------------------------------------
    # İZİN TALEP FORMU
    # ---------------------------------------------------
    if menu == "İzin Talep Formu":
        st.header("📝 Yeni İzin Talebi Oluştur")

        izin_turleri = [
            "Yıllık İzin", "Mazeret İzni", "Ücretsiz İzin", "Raporlu İzin",
            "Doğum İzni", "Babalık İzni", "Evlenme İzni", "Cenaze İzni"
        ]

        with st.form("izin_formu"):
            tip = st.selectbox("İzin Türü", izin_turleri)
            baslangic = st.date_input("Başlangıç Tarihi", date.today())
            bitis = st.date_input("Bitiş Tarihi", date.today())
            neden = st.text_area("İzin Nedeni")

            if st.form_submit_button("Talebi Gönder"):
                if bitis < baslangic:
                    st.error("Bitiş tarihi başlangıç tarihinden önce olamaz.")
                else:
                    c.execute("""
                        INSERT INTO talepler (ad_soyad, departman, meslek, tip, baslangic, bitis, neden, durum)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,'Beklemede')
                    """, (
                        user["ad_soyad"],
                        user["departman"],
                        user["meslek"],
                        tip,
                        str(baslangic),
                        str(bitis),
                        neden
                    ))
                    conn.commit()

                    mail_gonder(
                        user["onayci_email"],
                        "Yeni İzin Talebi",
                        f"{user['ad_soyad']} tarafından yeni bir izin talebi oluşturuldu."
                    )

                    st.success("İzin talebiniz başarıyla gönderildi!")
                    st.rerun()

    # ---------------------------------------------------
    # İZİNLERİM (DÜZENLE / SİL + PDF)
    # ---------------------------------------------------
    elif menu == "İzinlerim (Durum Takip)":
        st.header("📑 İzin Taleplerimin Son Durumu")

        kendi_izinlerim = pd.read_sql_query(
            f"SELECT * FROM talepler WHERE ad_soyad='{user['ad_soyad']}' ORDER BY id DESC",
            conn
        )

        if kendi_izinlerim.empty:
            st.info("Henüz bir izin talebiniz bulunmuyor.")
        else:
            st.subheader("📋 İzin Listem")

            for index, row in kendi_izinlerim.iterrows():
                kutu = st.container()
                with kutu:
                    col1, col2, col3 = st.columns([4, 1, 1])

                    col1.write(
                        f"**{row['tip']}** — {row['baslangic']} → {row['bitis']}  \n"
                        f"Durum: **{row['durum']}**"
                    )

                    # ❌ SİL BUTONU
                    if col2.button("Sil", key=f"sil_{row['id']}"):
                        c.execute("DELETE FROM talepler WHERE id=%s", (row['id'],))
                        conn.commit()
                        st.success("Talep silindi!")
                        st.rerun()

                    # ✏️ DÜZENLE BUTONU
                    if col3.button("Düzenle", key=f"duz_{row['id']}"):
                        st.session_state["duzenlenecek_id"] = row["id"]
                        st.rerun()

            # ---------------------------------------------------
            # ✏️ DÜZENLEME FORMU
            # ---------------------------------------------------
            if "duzenlenecek_id" in st.session_state:
                duz_id = st.session_state["duzenlenecek_id"]

                duz_row = pd.read_sql_query(
                    f"SELECT * FROM talepler WHERE id={duz_id}",
                    conn
                ).iloc[0]

                st.markdown("---")
                st.subheader("✏️ İzin Düzenle")

                izin_turleri = [
                    "Yıllık İzin", "Mazeret İzni", "Ücretsiz İzin", "Raporlu İzin",
                    "Doğum İzni", "Babalık İzni", "Evlenme İzni", "Cenaze İzni"
                ]

                yeni_tip = st.selectbox("İzin Türü", izin_turleri, index=izin_turleri.index(duz_row["tip"]))
                yeni_bas = st.date_input("Başlangıç", date.fromisoformat(duz_row["baslangic"]))
                yeni_bit = st.date_input("Bitiş", date.fromisoformat(duz_row["bitis"]))
                yeni_neden = st.text_area("İzin Nedeni", duz_row["neden"])

                if st.button("Kaydet"):
                    c.execute("""
                        UPDATE talepler
                        SET tip=%s, baslangic=%s, bitis=%s, neden=%s
                        WHERE id=%s
                    """, (yeni_tip, str(yeni_bas), str(yeni_bit), yeni_neden, duz_id))
                    conn.commit()

                    del st.session_state["duzenlenecek_id"]
                    st.success("Talep güncellendi!")
                    st.rerun()

            # ---------------------------------------------------
            # 🖨️ ONAYLANAN İZİNLERİN PDF ÇIKTISI
            # ---------------------------------------------------
            st.markdown("---")
            st.subheader("🖨️ Onaylanan İzinlerin PDF Çıktısı")

            for index, row in kendi_izinlerim.iterrows():
                if row['durum'] == "Onaylandı":

                    yonetici = ""
                    onay_tarihi = ""
                    if row["onay_notu"]:
                        parts = row["onay_notu"].split()
                        if "tarafından" in parts:
                            idx = parts.index("tarafından")
                            yonetici = " ".join(parts[:idx])
                            if len(parts) > idx + 1:
                                onay_tarihi = parts[idx + 1]

                    veri = {
                        "ad_soyad": row["ad_soyad"],
                        "sicil": user["sicil"],
                        "departman": row["departman"],
                        "meslek": row["meslek"],
                        "telefon": user["cep_telefonu"],
                        "email": user["email"],
                        "tip": row["tip"],
                        "baslangic": row["baslangic"],
                        "bitis": row["bitis"],
                        "neden": row["neden"],
                        "durum": row["durum"],
                        "yonetici": yonetici,
                        "onay_tarihi": onay_tarihi
                    }

                    pdf_bytes = pdf_olustur(veri)

                    st.download_button(
                        label=f"📥 {row['baslangic']} - {row['tip']} PDF İndir",
                        data=pdf_bytes,
                        file_name=f"izin_formu_{row['id']}.pdf",
                        mime="application/pdf"
                    )
    # ---------------------------------------------------
    # YÖNETİCİ ONAY EKRANI
    # ---------------------------------------------------
    elif menu == "Onay Bekleyenler (Yönetici)":
        st.header("⏳ Onayınızı Bekleyen Personel Talepleri")
        df_p = veri_getir()

        if "Ad Soyad" in df_p.columns:
            df_p.rename(columns={"Ad Soyad": "ad_soyad"}, inplace=True)

        bagli_personeller = df_p[df_p['onayci_email'] == user['email']]['ad_soyad'].tolist()

        bekleyenler = pd.read_sql_query("SELECT * FROM talepler WHERE durum='Beklemede'", conn)
        filtreli = bekleyenler[bekleyenler['ad_soyad'].isin(bagli_personeller)]

        if filtreli.empty:
            st.info("Şu an onayınızı bekleyen bir talep bulunmuyor.")
        else:
            for index, row in filtreli.iterrows():
                with st.expander(f"📌 {row['ad_soyad']} - {row['tip']}"):
                    st.write(f"**Tarih:** {row['baslangic']} / {row['bitis']}")
                    st.write(f"**Açıklama:** {row['neden']}")

                    o_col, r_col = st.columns(2)

                    if o_col.button("Onayla", key=f"on_{row['id']}"):
                        imza = f"{user['ad_soyad']} ({user['meslek']}) tarafından {date.today()} tarihinde onaylandı."
                        c.execute(
                            "UPDATE talepler SET durum='Onaylandı', onay_notu=%s WHERE id=%s",
                            (imza, row['id'])
                        )
                        conn.commit()

                        p_email = df_p[df_p['ad_soyad'] == row['ad_soyad']]['email'].values[0]
                        mail_gonder(p_email, "İzniniz Onaylandı", f"Sayın {row['ad_soyad']}, izniniz onaylanmıştır.")

                        st.rerun()

                    if r_col.button("Reddet", key=f"red_{row['id']}"):
                        c.execute("UPDATE talepler SET durum='Reddedildi' WHERE id=%s", (row['id'],))
                        conn.commit()

                        p_email = df_p[df_p['ad_soyad'] == row['ad_soyad']]['email'].values[0]
                        mail_gonder(p_email, "İzniniz Reddedildi", f"Sayın {row['ad_soyad']}, izniniz reddedilmiştir.")

                        st.rerun()

    # ---------------------------------------------------
    # İK GENEL TAKİP
    # ---------------------------------------------------
    elif menu == "Tüm Talepler (İK)":
        st.header("📊 Şirket Geneli Tüm İzin Hareketleri")

        df_all = pd.read_sql_query("SELECT * FROM talepler", conn)
        st.dataframe(df_all, use_container_width=True)

        st.download_button(
            label="📥 Excel Olarak İndir",
            data=excel_indir(df_all),
            file_name="tum_talepler.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # ---------------------------------------------------
    # PERSONEL YÖNETİMİ (İK)
    # ---------------------------------------------------
    elif menu == "Personel Yönetimi (İK)":
        st.header("👥 Personel Yönetimi (İK)")

        df_p = veri_getir()
        if "Ad Soyad" in df_p.columns:
            df_p.rename(columns={"Ad Soyad": "ad_soyad"}, inplace=True)

        st.subheader("Mevcut Personel Listesi")
        if df_p.empty:
            st.info("Sistemde henüz personel kaydı yok.")
        else:
            st.dataframe(df_p, use_container_width=True)

        st.markdown("---")
        st.subheader("Yeni Personel Ekle")

        with st.form("personel_ekle"):
            col1, col2 = st.columns(2)
            sicil = col1.text_input("Sicil")
            ad_soyad = col2.text_input("Ad Soyad")

            col3, col4 = st.columns(2)
            sifre = col3.text_input("Şifre")
            rol_sec = col4.selectbox("Rol", ["Personel", "Yönetici", "İK"])

            meslek = st.text_input("Meslek")
            departman = st.text_input("Departman")
            email = st.text_input("Email")
            onayci_email = st.text_input("Onaycı Email")
            cep_tel = st.text_input("Cep Telefonu")

            if st.form_submit_button("Kaydet"):
                c.execute(
                    """
                    INSERT INTO personellers (sicil, ad_soyad, sifre, meslek, departman,
                                              email, onayci_email, rol, cep_telefonu)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (sicil, ad_soyad, sifre, meslek, departman, email, onayci_email, rol_sec, cep_tel)
                )
                conn.commit()
                st.success("Personel başarıyla eklendi!")
                st.rerun()

        st.markdown("---")
        st.subheader("Personel Sil")

        if df_p.empty:
            st.info("Silinecek personel bulunmuyor.")
        else:
            silinecek = st.selectbox("Silinecek Personeli Seçin", df_p["ad_soyad"].tolist())

            if st.button("❌ Personeli Sil"):
                c.execute("DELETE FROM personellers WHERE ad_soyad=%s", (silinecek,))
                conn.commit()
                st.success(f"{silinecek} başarıyla silindi!")
                st.rerun()

        st.markdown("---")
        st.subheader("Excel'den Personel İçe Aktar")

        st.info("Excel formatı şu sütunları içermelidir: Sicil, Ad Soyad, Sifre, Meslek, Departman, Email, Onayci_Email, Rol, Cep_Telefonu")

        uploaded_file = st.file_uploader("Personel Excel Dosyası Yükle", type=["xlsx"])

        if uploaded_file is not None:
            try:
                df_import = pd.read_excel(uploaded_file)
                beklenen_kolonlar = ["Sicil", "Ad Soyad", "Sifre", "Meslek", "Departman", "Email", "Onayci_Email", "Rol", "Cep_Telefonu"]

                if not all(k in df_import.columns for k in beklenen_kolonlar):
                    st.error("Excel formatı hatalı. Lütfen belirtilen sütun adlarını birebir kullanın.")
                else:
                    eklenen = 0

                    for _, r in df_import.iterrows():

                        c.execute("SELECT COUNT(*) FROM personellers WHERE sicil=%s", (str(r["Sicil"]),))
                        var_mi = c.fetchone()[0]

                        if var_mi == 0:
                            c.execute(
                                """
                                INSERT INTO personellers (sicil, ad_soyad, sifre, meslek, departman,
                                                          email, onayci_email, rol, cep_telefonu)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                """,
                                (
                                    str(r["Sicil"]),
                                    str(r["Ad Soyad"]),
                                    str(r["Sifre"]),
                                    str(r["Meslek"]),
                                    str(r["Departman"]),
                                    str(r["Email"]),
                                    str(r["Onayci_Email"]),
                                    str(r["Rol"]),
                                    str(r["Cep_Telefonu"])
                                )
                            )
                            eklenen += 1

                    conn.commit()
                    st.success(f"{eklenen} personel başarıyla içe aktarıldı.")
                    st.rerun()

            except Exception as e:
                st.error(f"Excel içe aktarılırken hata: {e}")
