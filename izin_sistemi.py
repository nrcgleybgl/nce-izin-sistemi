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

# ---------------------------------------------------
# 1. HATA ENGELLEYİCİ VE SAYFA AYARI
# ---------------------------------------------------
st.set_page_config(page_title="Pro-İK İzin Portalı", layout="wide")

# Tarayıcı çevirisini ve DOM hatalarını engellemek için meta etiketleri
st.markdown("""
    <meta name="google" content="notranslate">
    <style>
        .main { unicode-bidi: isolate; }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------
# 2. YARDIMCI FONKSİYONLAR
# ---------------------------------------------------
def excel_indir(df, dosya_adi="rapor.xlsx"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name="Sayfa1")
    return output.getvalue()

def pdf_olustur(veri, logo_path="assets/logo.png"):
    pdf = FPDF()
    pdf.add_page()

    def fix(metin):
        if metin is None: return ""
        karakterler = {
            'ğ': 'g', 'Ğ': 'G', 'ş': 's', 'Ş': 'S',
            'İ': 'I', 'ı': 'i', 'ç': 'c', 'Ç': 'C',
            'ö': 'o', 'Ö': 'O', 'ü': 'u', 'Ü': 'U'
        }
        for eski, yeni in karakterler.items():
            metin = metin.replace(eski, yeni)
        return metin

    try: pdf.image(logo_path, x=80, y=10, w=50)
    except: pass

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

    if veri.get("durum") == "Onaylandı" and veri.get("yonetici"):
        kutu_baslik("YONETICI ONAYI")
        metin = f"Bu izin, {veri['yonetici']} tarafindan {veri['onay_tarihi']} tarihinde onaylanmistir."
        pdf.multi_cell(190, 8, fix(metin), border=1)
        pdf.ln(5)

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(95, 10, fix("Personel Imzasi"), border=1, ln=False, align='C')
    pdf.cell(95, 10, fix("Yonetici Imzasi"), border=1, ln=True, align='C')

    return pdf.output(dest='S').encode('latin-1', errors='ignore')

def mail_gonder(alici, konu, icerik):
    try:
        gonderen = st.secrets["SMTP_EMAIL"]
        sifre = st.secrets["SMTP_PASSWORD"]
        msg = MIMEMultipart()
        msg['From'] = gonderen
        msg['To'] = alici
        msg['Subject'] = konu
        msg.attach(MIMEText(icerik, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gonderen, sifre)
        server.sendmail(gonderen, alici, msg.as_string())
        server.quit()
    except Exception as e:
        st.error(f"Mail gönderilemedi: {e}")

# ---------------------------------------------------
# 3. VERİTABANI BAĞLANTISI VE TABLOLAR
# ---------------------------------------------------
@st.cache_resource
def get_db():
    return psycopg2.connect(
        dbname=st.secrets["DB_NAME"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        host=st.secrets["DB_HOST"],
        port=st.secrets["DB_PORT"]
    )

conn = get_db()
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS personellers (
    sicil TEXT, ad_soyad TEXT, sifre TEXT, meslek TEXT, departman TEXT, 
    email TEXT, onayci_email TEXT, rol TEXT, cep_telefonu TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS talepler (
    id SERIAL PRIMARY KEY, ad_soyad TEXT, departman TEXT, meslek TEXT, 
    tip TEXT, baslangic TEXT, bitis TEXT, neden TEXT, durum TEXT, onay_notu TEXT)""")
conn.commit()

def veri_getir():
    try:
        df = pd.read_sql_query("SELECT * FROM personellers", conn)
        if "Ad Soyad" in df.columns: df.rename(columns={"Ad Soyad": "ad_soyad"}, inplace=True)
        return df
    except: return pd.DataFrame()

# ---------------------------------------------------
# 4. OTURUM VE GİRİŞ
# ---------------------------------------------------
if 'login_oldu' not in st.session_state:
    st.session_state['login_oldu'] = False

try: st.image("assets/logo.png", width=180)
except: pass

st.title("🔐 NCE Bordro Danışmanlık ve Eğitim - İK İzin Paneli")

df_p = veri_getir()

if not st.session_state['login_oldu']:
    with st.form("giris_formu"):
        isim = st.text_input("Ad Soyad")
        sifre = st.text_input("Şifre", type="password")
        if st.form_submit_button("Giriş Yap"):
            user_row = df_p[(df_p['ad_soyad'] == isim) & (df_p['sifre'].astype(str) == sifre)]
            if not user_row.empty:
                st.session_state['login_oldu'] = True
                st.session_state['user'] = user_row.iloc[0]
                st.rerun()
            else: st.error("Kullanıcı adı veya şifre hatalı!")

# ---------------------------------------------------
# 5. ANA PANEL
# ---------------------------------------------------
else:
    user = st.session_state['user']
    rol = user.get('rol', 'Personel')

    ana_menu = ["İzin Talep Formu", "İzinlerim (Durum Takip)"]
    if rol in ["Yönetici", "İK"]: ana_menu.append("Onay Bekleyenler (Yönetici)")
    if rol == "İK":
        ana_menu.append("Tüm Talepler (İK)")
        ana_menu.append("Personel Yönetimi (İK)")

    menu = st.sidebar.radio("İşlem Menüsü", ana_menu)
    if st.sidebar.button("🔒 Güvenli Çıkış"):
        st.session_state['login_oldu'] = False
        st.rerun()

    # --- İZİN TALEP FORMU ---
    if menu == "İzin Talep Formu":
        st.header("📝 Yeni İzin Talebi Oluştur")
        izin_turleri = ["Yıllık İzin", "Mazeret İzni", "Ücretsiz İzin", "Raporlu İzin", "Doğum İzni", "Babalık İzni", "Evlenme İzni", "Cenaze İzni"]
        with st.form("izin_formu"):
            tip = st.selectbox("İzin Türü", izin_turleri)
            baslangic = st.date_input("Başlangıç Tarihi", date.today())
            bitis = st.date_input("Bitiş Tarihi", date.today())
            neden = st.text_area("İzin Nedeni")
            if st.form_submit_button("Talebi Gönder"):
                if bitis < baslangic: st.error("Bitiş tarihi hatalı.")
                else:
                    c.execute("INSERT INTO talepler (ad_soyad, departman, meslek, tip, baslangic, bitis, neden, durum) VALUES (%s,%s,%s,%s,%s,%s,%s,'Beklemede')",
                              (user["ad_soyad"], user["departman"], user["meslek"], tip, str(baslangic), str(bitis), neden))
                    conn.commit()
                    mail_gonder(user["onayci_email"], "Yeni İzin Talebi", f"{user['ad_soyad']} yeni talep oluşturdu.")
                    st.success("Talebiniz başarıyla gönderildi!")
                    st.rerun()

    # --- İZİNLERİM ---
    elif menu == "İzinlerim (Durum Takip)":
        st.header("📑 İzin Taleplerim")
        kendi_izinlerim = pd.read_sql_query(f"SELECT * FROM talepler WHERE ad_soyad='{user['ad_soyad']}' ORDER BY id DESC", conn)
        for index, row in kendi_izinlerim.iterrows():
            with st.container():
                col1, col2, col3 = st.columns([4, 1, 1])
                col1.write(f"**{row['tip']}** ({row['baslangic']} / {row['bitis']}) - Durum: **{row['durum']}**")
                if col2.button("Sil", key=f"del_{row['id']}"):
                    c.execute("DELETE FROM talepler WHERE id=%s", (row['id'],))
                    conn.commit()
                    st.rerun()
                if col3.button("Düzenle", key=f"edt_{row['id']}"):
                    st.session_state["duzenlenecek_id"] = row["id"]
                    st.rerun()

        if "duzenlenecek_id" in st.session_state:
            st.markdown("---")
            duz_id = st.session_state["duzenlenecek_id"]
            duz_row = pd.read_sql_query(f"SELECT * FROM talepler WHERE id={duz_id}", conn).iloc[0]
            with st.form("duzenle_form"):
                y_tip = st.selectbox("İzin Türü", ["Yıllık İzin", "Mazeret İzni", "Ücretsiz İzin"], index=0)
                y_bas = st.date_input("Başlangıç", date.fromisoformat(duz_row["baslangic"]))
                y_bit = st.date_input("Bitiş", date.fromisoformat(duz_row["bitis"]))
                y_neden = st.text_area("Neden", duz_row["neden"])
                if st.form_submit_button("Güncelle"):
                    c.execute("UPDATE talepler SET tip=%s, baslangic=%s, bitis=%s, neden=%s WHERE id=%s", (y_tip, str(y_bas), str(y_bit), y_neden, duz_id))
                    conn.commit()
                    del st.session_state["duzenlenecek_id"]
                    st.rerun()

        st.subheader("🖨️ Onaylanan İzinlerin PDF Çıktısı")
        for index, row in kendi_izinlerim.iterrows():
            if row['durum'] == "Onaylandı":
                yonetici, onay_tarihi = "", ""
                if row["onay_notu"]:
                    parts = row["onay_notu"].split()
                    if "tarafından" in parts:
                        idx = parts.index("tarafından")
                        yonetici = " ".join(parts[:idx])
                        onay_tarihi = parts[idx + 1] if len(parts) > idx + 1 else ""
                
                pdf_bytes = pdf_olustur({
                    "ad_soyad": row["ad_soyad"], "sicil": user["sicil"], "departman": row["departman"],
                    "meslek": row["meslek"], "telefon": user["cep_telefonu"], "email": user["email"],
                    "tip": row["tip"], "baslangic": row["baslangic"], "bitis": row["bitis"],
                    "neden": row["neden"], "durum": row["durum"], "yonetici": yonetici, "onay_tarihi": onay_tarihi
                })
                st.download_button(f"📥 PDF İndir ({row['baslangic']})", pdf_bytes, f"izin_{row['id']}.pdf", "application/pdf")

    # --- YÖNETİCİ ONAY ---
    elif menu == "Onay Bekleyenler (Yönetici)":
        st.header("⏳ Onayınızı Bekleyenler")
        bagli = df_p[df_p['onayci_email'] == user['email']]['ad_soyad'].tolist()
        bekleyenler = pd.read_sql_query("SELECT * FROM talepler WHERE durum='Beklemede'", conn)
        filtreli = bekleyenler[bekleyenler['ad_soyad'].isin(bagli)]
        for index, row in filtreli.iterrows():
            with st.expander(f"📌 {row['ad_soyad']} - {row['tip']}"):
                st.write(f"Tarih: {row['baslangic']} / {row['bitis']}\nNeden: {row['neden']}")
                o_col, r_col = st.columns(2)
                if o_col.button("Onayla", key=f"onay_{row['id']}"):
                    imza = f"{user['ad_soyad']} ({user['meslek']}) tarafından {date.today()} tarihinde onaylandı."
                    c.execute("UPDATE talepler SET durum='Onaylandı', onay_notu=%s WHERE id=%s", (imza, row['id']))
                    conn.commit()
                    st.rerun()
                if r_col.button("Reddet", key=f"red_{row['id']}"):
                    c.execute("UPDATE talepler SET durum='Reddedildi' WHERE id=%s", (row['id'],))
                    conn.commit()
                    st.rerun()

    # --- İK TÜM TALEPLER ---
    elif menu == "Tüm Talepler (İK)":
        st.header("📊 Şirket Geneli Tüm İzinler")
        df_all = pd.read_sql_query("SELECT * FROM talepler", conn)
        st.dataframe(df_all, use_container_width=True)
        st.download_button("📥 Excel Olarak İndir", excel_indir(df_all), "tum_talepler.xlsx")

    # --- PERSONEL YÖNETİMİ ---
    elif menu == "Personel Yönetimi (İK)":
        st.header("👥 Personel Yönetimi")
        df_p = veri_getir()
        st.dataframe(df_p, use_container_width=True)
        
        with st.expander("➕ Yeni Personel Ekle"):
            with st.form("yeni_per_form"):
                c1, c2 = st.columns(2)
                sc = c1.text_input("Sicil")
                ads = c2.text_input("Ad Soyad")
                pw = st.text_input("Şifre")
                rol_s = st.selectbox("Rol", ["Personel", "Yönetici", "İK"])
                if st.form_submit_button("Kaydet"):
                    c.execute("INSERT INTO personellers (sicil, ad_soyad, sifre, rol) VALUES (%s,%s,%s,%s)", (sc, ads, pw, rol_s))
                    conn.commit()
                    st.rerun()

        with st.expander("❌ Personel Sil"):
            silinecek = st.selectbox("Silinecek Personel", df_p["ad_soyad"].tolist() if not df_p.empty else [])
            if st.button("Seçili Personeli Sil"):
                c.execute("DELETE FROM personellers WHERE ad_soyad=%s", (silinecek,))
                conn.commit()
                st.rerun()

        with st.expander("📤 Excel'den Toplu Personel Yükle"):
            up = st.file_uploader("Excel Seç", type=["xlsx"])
            if up:
                df_imp = pd.read_excel(up)
                for _, r in df_imp.iterrows():
                    c.execute("INSERT INTO personellers (sicil, ad_soyad, sifre, meslek, departman, email, onayci_email, rol, cep_telefonu) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                              (str(r["Sicil"]), str(r["Ad Soyad"]), str(r["Sifre"]), str(r["Meslek"]), str(r["Departman"]), str(r["Email"]), str(r["Onayci_Email"]), str(r["Rol"]), str(r["Cep_Telefonu"])))
                conn.commit()
                st.success("Aktarıldı!")
                st.rerun()
