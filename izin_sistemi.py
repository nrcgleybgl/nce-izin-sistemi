import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import psycopg2
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from io import BytesIO
from fpdf import FPDF
from dotenv import load_dotenv
import os
import unicodedata

load_dotenv()

# ---------------------------------------------------
# DATABASE
# ---------------------------------------------------

def get_db():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        sslmode="require"
    )

conn = get_db()
c = conn.cursor()

# ---------------------------------------------------
# TABLOLAR (DATE YAPISI)
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
    baslangic DATE,
    bitis DATE,
    neden TEXT,
    durum TEXT,
    onay_notu TEXT
)
""")

conn.commit()

# ---------------------------------------------------
# YARDIMCI FONKSİYONLAR
# ---------------------------------------------------

def tr_tarih(t):
    if t:
        return t.strftime("%d/%m/%Y")
    return ""

def excel_indir(df, dosya_adi="rapor.xlsx"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def temizle(text):
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()

# ---------------------------------------------------
# PDF
# ---------------------------------------------------

def pdf_olustur(veri):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "IZIN TALEP FORMU", ln=True, align='C')
    pdf.ln(10)

    pdf.set_font("Arial", size=12)

    for k, v in veri.items():
        pdf.cell(60, 8, f"{k}:", border=1)
        pdf.cell(120, 8, str(v), border=1, ln=True)

    return pdf.output(dest='S').encode('latin-1', errors='ignore')

# ---------------------------------------------------
# MAIL
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
    except:
        pass

# ---------------------------------------------------
# LOGIN
# ---------------------------------------------------

st.set_page_config(page_title="Pro-İK İzin Portalı", layout="wide")

if "login_oldu" not in st.session_state:
    st.session_state["login_oldu"] = False
    st.session_state["user"] = None

def veri_getir():
    return pd.read_sql_query("SELECT * FROM personellers", conn)

df_p = veri_getir()

if not st.session_state["login_oldu"]:
    st.title("🔐 İK İzin Portalı")

    with st.form("giris"):
        isim = st.text_input("Ad Soyad")
        sifre = st.text_input("Şifre", type="password")

        if st.form_submit_button("Giriş"):
            user_row = df_p[
                (df_p["ad_soyad"] == isim) &
                (df_p["sifre"].astype(str) == sifre)
            ]

            if not user_row.empty:
                st.session_state["login_oldu"] = True
                st.session_state["user"] = user_row.iloc[0]
                st.rerun()
            else:
                st.error("Hatalı giriş")

    st.stop()
    # ---------------------------------------------------
# ANA PANEL
# ---------------------------------------------------

user = st.session_state["user"]
rol = user.get("rol", "Personel")

ana_menu = ["İzin Talep Formu", "İzinlerim (Durum Takip)"]

if rol in ["Yönetici", "İK"]:
    ana_menu.append("Onay Bekleyenler (Yönetici)")

if rol == "İK":
    ana_menu.append("Tüm Talepler (İK)")
    ana_menu.append("Personel Yönetimi (İK)")

st.sidebar.title(f"👤 {user['ad_soyad']}")
st.sidebar.write(f"Rol: {rol}")
menu = st.sidebar.radio("Menü", ana_menu)

if st.sidebar.button("Çıkış"):
    st.session_state["login_oldu"] = False
    st.rerun()

# ---------------------------------------------------
# 1️⃣ İZİN TALEP FORMU
# ---------------------------------------------------

if menu == "İzin Talep Formu":

    st.header("📝 Yeni İzin Talebi")

    izin_turleri = [
        "Yıllık İzin", "Mazeret İzni", "Ücretsiz İzin",
        "Raporlu İzin", "Doğum İzni", "Babalık İzni",
        "Evlenme İzni", "Cenaze İzni"
    ]

    with st.form("izin_formu"):
        tip = st.selectbox("İzin Türü", izin_turleri)
        baslangic = st.date_input("Başlangıç Tarihi", date.today())
        bitis = st.date_input("Bitiş Tarihi", date.today())
        neden = st.text_area("İzin Nedeni")

        if st.form_submit_button("Talebi Gönder"):

            if bitis < baslangic:
                st.error("Bitiş tarihi başlangıçtan önce olamaz.")
                st.stop()

            # ✅ 1 YIL SINIRI
            if (bitis - baslangic).days > 365:
                st.error("Maksimum 1 yıllık izin girilebilir.")
                st.stop()

            # ✅ ÇAKIŞMA KONTROLÜ
            c.execute("""
                SELECT COUNT(*) FROM talepler
                WHERE ad_soyad=%s
                AND durum!='Silindi'
                AND (
                    (baslangic BETWEEN %s AND %s)
                    OR
                    (bitis BETWEEN %s AND %s)
                )
            """, (
                user["ad_soyad"],
                baslangic,
                bitis,
                baslangic,
                bitis
            ))

            if c.fetchone()[0] > 0:
                st.warning("Bu tarih aralığında zaten izin talebiniz var.")
                st.stop()

            c.execute("""
                INSERT INTO talepler
                (ad_soyad, departman, meslek, tip, baslangic, bitis, neden, durum)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'Beklemede')
            """, (
                user["ad_soyad"],
                user["departman"],
                user["meslek"],
                tip,
                baslangic,
                bitis,
                neden
            ))

            conn.commit()
            st.success("İzin talebi gönderildi.")
            st.rerun()

# ---------------------------------------------------
# 2️⃣ İZİNLERİM
# ---------------------------------------------------

elif menu == "İzinlerim (Durum Takip)":

    st.header("📑 İzinlerim")

    c.execute("""
        SELECT * FROM talepler
        WHERE ad_soyad=%s
        AND durum!='Silindi'
        ORDER BY id DESC
    """, (user["ad_soyad"],))

    rows = c.fetchall()

    if not rows:
        st.info("Henüz izin kaydınız yok.")
    else:

        columns = [desc[0] for desc in c.description]
        df = pd.DataFrame(rows, columns=columns)

        for _, row in df.iterrows():

            st.markdown(f"""
            **{row['tip']}**  
            {tr_tarih(row['baslangic'])} → {tr_tarih(row['bitis'])}  
            Durum: **{row['durum']}**
            """)

            col1, col2 = st.columns(2)

            # ✅ SOFT DELETE
            if col1.button("Sil", key=f"sil_{row['id']}"):
                c.execute("UPDATE talepler SET durum='Silindi' WHERE id=%s", (row["id"],))
                conn.commit()
                st.success("Silindi.")
                st.rerun()

            # ✅ DÜZENLE
            if col2.button("Düzenle", key=f"duz_{row['id']}"):
                st.session_state["duzenle_id"] = row["id"]
                st.rerun()

        # ---------------------------------------------------
        # DÜZENLEME FORMU
        # ---------------------------------------------------

        if "duzenle_id" in st.session_state:

            c.execute("SELECT * FROM talepler WHERE id=%s", (st.session_state["duzenle_id"],))
            row = c.fetchone()
            columns = [desc[0] for desc in c.description]
            duz = dict(zip(columns, row))

            st.markdown("---")
            st.subheader("✏️ İzin Güncelle")

            yeni_tip = st.selectbox("İzin Türü", izin_turleri, index=izin_turleri.index(duz["tip"]))
            yeni_bas = st.date_input("Başlangıç", duz["baslangic"])
            yeni_bit = st.date_input("Bitiş", duz["bitis"])
            yeni_neden = st.text_area("Neden", duz["neden"])

            if st.button("Kaydet"):

                if (yeni_bit - yeni_bas).days > 365:
                    st.error("Maksimum 1 yıl.")
                    st.stop()

                c.execute("""
                    UPDATE talepler
                    SET tip=%s, baslangic=%s, bitis=%s, neden=%s
                    WHERE id=%s
                """, (yeni_tip, yeni_bas, yeni_bit, yeni_neden, duz["id"]))

                conn.commit()
                del st.session_state["duzenle_id"]
                st.success("Güncellendi.")
                st.rerun()

        # ---------------------------------------------------
        # PDF
        # ---------------------------------------------------

        st.markdown("---")
        st.subheader("📥 Onaylanan İzinler (PDF)")

        for _, row in df.iterrows():
            if row["durum"] == "Onaylandı":

                veri = {
                    "Ad Soyad": row["ad_soyad"],
                    "İzin Türü": row["tip"],
                    "Başlangıç": tr_tarih(row["baslangic"]),
                    "Bitiş": tr_tarih(row["bitis"]),
                    "Durum": row["durum"]
                }

                pdf_bytes = pdf_olustur(veri)

                dosya_adi = temizle(f"{row['ad_soyad']}_{row['tip']}.pdf")

                st.download_button(
                    "PDF İndir",
                    data=pdf_bytes,
                    file_name=dosya_adi,
                    mime="application/pdf"
                )
                # ---------------------------------------------------
# 3️⃣ YÖNETİCİ ONAY EKRANI
# ---------------------------------------------------

elif menu == "Onay Bekleyenler (Yönetici)":

    st.header("⏳ Onay Bekleyen Talepler")

    c.execute("""
        SELECT * FROM talepler
        WHERE durum='Beklemede'
        ORDER BY id DESC
    """)
    rows = c.fetchall()

    if not rows:
        st.info("Bekleyen talep yok.")
    else:
        columns = [desc[0] for desc in c.description]
        df = pd.DataFrame(rows, columns=columns)

        for _, row in df.iterrows():

            with st.expander(f"{row['ad_soyad']} - {row['tip']}"):

                st.write(f"Tarih: {tr_tarih(row['baslangic'])} → {tr_tarih(row['bitis'])}")
                st.write(f"Neden: {row['neden']}")

                col1, col2 = st.columns(2)

                # ONAY
                if col1.button("Onayla", key=f"on_{row['id']}"):

                    imza = f"{user['ad_soyad']} tarafından {date.today()} tarihinde onaylandı."

                    c.execute("""
                        UPDATE talepler
                        SET durum='Onaylandı', onay_notu=%s
                        WHERE id=%s
                    """, (imza, row["id"]))

                    conn.commit()

                    st.success("Onaylandı.")
                    st.rerun()

                # RED
                if col2.button("Reddet", key=f"red_{row['id']}"):

                    c.execute("""
                        UPDATE talepler
                        SET durum='Reddedildi'
                        WHERE id=%s
                    """, (row["id"],))

                    conn.commit()

                    st.warning("Reddedildi.")
                    st.rerun()

# ---------------------------------------------------
# 4️⃣ İK - TÜM TALEPLER
# ---------------------------------------------------

elif menu == "Tüm Talepler (İK)":

    st.header("📊 Tüm İzin Talepleri")

    c.execute("""
        SELECT * FROM talepler
        WHERE durum!='Silindi'
        ORDER BY id DESC
    """)
    rows = c.fetchall()

    if not rows:
        st.info("Kayıt bulunamadı.")
    else:
        columns = [desc[0] for desc in c.description]
        df = pd.DataFrame(rows, columns=columns)

        df["baslangic"] = df["baslangic"].apply(tr_tarih)
        df["bitis"] = df["bitis"].apply(tr_tarih)

        secilenler = st.multiselect(
            "Silmek istediğiniz kayıt ID'leri",
            df["id"].tolist()
        )

        if st.button("🗑️ Seçilenleri Sil"):
            for i in secilenler:
                c.execute("UPDATE talepler SET durum='Silindi' WHERE id=%s", (i,))
            conn.commit()
            st.success("Seçilenler silindi.")
            st.rerun()

        st.dataframe(df, use_container_width=True)

        st.download_button(
            "Excel İndir",
            data=excel_indir(df),
            file_name="tum_talepler.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ---------------------------------------------------
# 5️⃣ PERSONEL YÖNETİMİ
# ---------------------------------------------------

elif menu == "Personel Yönetimi (İK)":

    st.header("👥 Personel Yönetimi")

    df_p = veri_getir()

    if not df_p.empty:
        st.dataframe(df_p, use_container_width=True)

    st.markdown("---")
    st.subheader("Yeni Personel Ekle")

    with st.form("personel_ekle"):

        sicil = st.text_input("Sicil")
        ad_soyad = st.text_input("Ad Soyad")
        sifre = st.text_input("Şifre")
        meslek = st.text_input("Meslek")
        departman = st.text_input("Departman")
        email = st.text_input("Email")
        onayci_email = st.text_input("Onaycı Email")
        rol_sec = st.selectbox("Rol", ["Personel", "Yönetici", "İK"])
        cep = st.text_input("Cep Telefonu")

        if st.form_submit_button("Kaydet"):

            c.execute("""
                INSERT INTO personellers
                (sicil, ad_soyad, sifre, meslek, departman,
                 email, onayci_email, rol, cep_telefonu)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                sicil, ad_soyad, sifre, meslek,
                departman, email, onayci_email,
                rol_sec, cep
            ))

            conn.commit()
            st.success("Personel eklendi.")
            st.rerun()

    st.markdown("---")
    st.subheader("Personel Sil")

    if not df_p.empty:

        silinecek = st.selectbox(
            "Silinecek Personel",
            df_p["ad_soyad"].tolist()
        )

        if st.button("❌ Sil"):
            c.execute("DELETE FROM personellers WHERE ad_soyad=%s", (silinecek,))
            conn.commit()
            st.success("Silindi.")
            st.rerun()

    st.markdown("---")
    st.subheader("Excel'den Personel Aktar")

    uploaded = st.file_uploader("Excel Yükle", type=["xlsx"])

    if uploaded:
        try:
            df_import = pd.read_excel(uploaded)

            for _, r in df_import.iterrows():
                c.execute("""
                    INSERT INTO personellers
                    (sicil, ad_soyad, sifre, meslek, departman,
                     email, onayci_email, rol, cep_telefonu)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    str(r["Sicil"]),
                    str(r["Ad Soyad"]),
                    str(r["Sifre"]),
                    str(r["Meslek"]),
                    str(r["Departman"]),
                    str(r["Email"]),
                    str(r["Onayci_Email"]),
                    str(r["Rol"]),
                    str(r["Cep_Telefonu"])
                ))

            conn.commit()
            st.success("Excel başarıyla aktarıldı.")
            st.rerun()

        except Exception as e:
            st.error(f"Hata: {e}")
