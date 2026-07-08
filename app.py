import streamlit as st
import pandas as pd
import csv
import io
import requests
from datetime import date
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics

# =========================================================================
# ID DE TU HOJA DE CÁLCULO FIJA (Google Sheets público unificado)
# =========================================================================
ID_DRIVE = "1z1naxcQyryThMHj3H9K3xi27EDuugBPnFKrrwrJ8v1Y" 
URL_DRIVE = f"https://docs.google.com/spreadsheets/d/{ID_DRIVE}/export?format=csv"

# =========================================================================
# FUNCIONES AUXILIARES UNIFICADAS
# =========================================================================
def fix_encoding(text: str) -> str:
    if text is None: return ""
    text = str(text)
    replacements = {
        "Ã\x91": "Ñ", "Ã±": "ñ", "Ã\x81": "Á", "Ã\x89": "É", 
        "Ã\x8d": "Í", "Ã\x93": "Ó", "Ã\x9a": "Ú", "Ã¡": "á", 
        "Ã©": "é", "Ã­": "í", "Ã³": "ó", "Ãº": "ú",
        "NÅ°": "N°", "NÂ°": "N°", "NÂ": "N°", "N° ": "N°"
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    try: return text.encode("latin1").decode("utf-8")
    except Exception: return text

def format_price_arg(price_str: str) -> str:
    if not price_str: return ""
    s = str(price_str).replace("$", "").replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(".", "").replace(",", ".")
    try: value = float(s)
    except ValueError: return price_str.strip()
    us = f"{value:,.2f}"
    return f"${us.replace(',', 'X').replace('.', ',').replace('X', '.')}"

def wrap_text_to_width(text, font_name, font_size, max_width):
    words = text.split()
    if not words: return []
    lines = []
    current = words[0]
    for w in words[1:]:
        test = current + " " + w
        if pdfmetrics.stringWidth(test, font_name, font_size) <= max_width: current = test
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines

# =========================================================================
# MOTORES DE GENERACIÓN DE PDF
# =========================================================================
def generar_carteles_gigantes(products_list):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    lbl_w, lbl_h = A4[0] - 10*mm, (A4[1] - 15*mm) / 2
    label_date = date.today().strftime("%d/%m/%Y")
    for i, (sku, name, price, date_str) in enumerate(products_list):
        pos = i % 2
        if i != 0 and pos == 0: c.showPage()
        x, y = 5*mm, ((A4[1] - 5*mm - lbl_h) if pos == 0 else 5*mm)
        c.rect(x, y, lbl_w, lbl_h)
        price_txt = format_price_arg(price).strip()
        f_size = 125
        while f_size > 20:
            if c.stringWidth(price_txt, "Helvetica-Bold", f_size) <= (lbl_w - 20): break
            f_size -= 2
        c.setFont("Helvetica-Bold", f_size)
        c.drawString(x + (lbl_w - c.stringWidth(price_txt, "Helvetica-Bold", f_size))/2, y + lbl_h/2 - f_size/2, price_txt)
        c.setFont("Helvetica-Bold", 24)
        desc_clean = fix_encoding(name).strip()
        words = desc_clean.split()
        lines, curr = [], ""
        for w in words:
            test = w if not curr else curr + " " + w
            if c.stringWidth(test, "Helvetica-Bold", 24) <= (lbl_w - 40): curr = test
            else:
                if curr: lines.append(curr)
                curr = w
                if len(lines) == 1: break
        if curr and len(lines) < 2: lines.append(curr)
        ny = y + lbl_h - 45
        for line in lines:
            c.drawCentredString(x + lbl_w/2, ny, line)
            ny -= 29
        final_date = date_str if date_str else label_date
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(x + lbl_w/2, y + 14, f"{sku}  {final_date}")
    c.save()
    buffer.seek(0)
    return buffer

def generar_precios_medianos(data_rows):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    lbl_w, lbl_h = 10 * cm, 7 * cm
    margin_x, margin_y = (page_width - (2 * lbl_w)) / 2.0, (page_height - (4 * lbl_h)) / 2.0
    col, row = 0, 0
    for sku, name, price, date_str in data_rows:
        x = margin_x + col * lbl_w
        y = page_height - margin_y - (row + 1) * lbl_h
        c.setLineWidth(1)
        c.rect(x, y, lbl_w, lbl_h)
        inner_w = lbl_w - 0.6*cm
        desc_top = y + lbl_h - 0.3*cm
        desc_text = fix_encoding(name).strip()
        if desc_text:
            f_size = 18
            while f_size >= 7:
                lines = wrap_text_to_width(desc_text, "Helvetica-Bold", f_size, inner_w)
                if len(lines) * f_size * 1.15 <= (lbl_h * 0.35): break
                f_size -= 1
            c.setFont("Helvetica-Bold", f_size)
            curr_y = desc_top - f_size
            for line in lines:
                c.drawString(x + 0.3*cm + (inner_w - pdfmetrics.stringWidth(line, "Helvetica-Bold", f_size))/2.0, curr_y, line)
                curr_y -= f_size * 1.15
        price_text = format_price_arg(price).strip()
        if price_text:
            f_size = 95
            while f_size > 14:
                if pdfmetrics.stringWidth(price_text, "Helvetica-Bold", f_size) <= inner_w: break
                f_size -= 1
            c.setFont("Helvetica-Bold", f_size)
            c.drawString(x + 0.3*cm + (inner_w - pdfmetrics.stringWidth(price_text, "Helvetica-Bold", f_size))/2.0, y + 1.1*cm, price_text)
        footer = f"{str(sku).strip()}   {str(date_str).strip()}"
        c.setFont("Helvetica", 10)
        c.drawString(x + 0.3*cm + (inner_w - pdfmetrics.stringWidth(footer, "Helvetica", 10))/2.0, y + 0.3*cm, footer)
        col += 1
        if col >= 2: col, row = 0, row + 1
        if row >= 4: c.showPage(); row, col = 0, 0
    c.save()
    buffer.seek(0)
    return buffer

def generar_etiquetas_chicas(products_list):
    buffer = io.BytesIO()
    w_page, h_page = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=(w_page, h_page))
    label_date = date.today().strftime("%d/%m/%y")
    lbl_w, lbl_h = 70*mm, 35*mm
    cols, rows = int((w_page - 10*mm + 2*mm) // (lbl_w + 2*mm)), int((h_page - 10*mm + 2*mm) // (lbl_h + 2*mm))
    per_page = cols * rows
    for i, (sku, name, price, date_str) in enumerate(products_list):
        if i > 0 and i % per_page == 0: c.showPage()
        pos = i % per_page
        r, col = pos // cols, pos % cols
        x = 5*mm + col * (lbl_w + 2*mm)
        y = h_page - 5*mm - ((r + 1) * (lbl_h + 2*mm)) + 2*mm
        c.setLineWidth(0.5)
        c.rect(x, y, lbl_w, lbl_h)
        price_txt = format_price_arg(price).strip()
        f_size_p = 34
        while f_size_p > 12:
            if c.stringWidth(price_txt, "Helvetica-Bold", f_size_p) <= (lbl_w - 4*mm): break
            f_size_p -= 1
        c.setFont("Helvetica-Bold", f_size_p)
        c.drawString(x + (lbl_w - c.stringWidth(price_txt, "Helvetica-Bold", f_size_p))/2, y + (lbl_h * 0.22), price_txt)
        c.setFont("Helvetica-Bold", 9)
        desc_clean = fix_encoding(name).strip()
        words = desc_clean.split()
        lines, curr = [], ""
        for w in words:
            test = w if not curr else curr + " " + w
            if c.stringWidth(test, "Helvetica-Bold", 9) <= (lbl_w - 4*mm): curr = test
            else:
                if curr: lines.append(curr)
                curr = w
                if len(lines) == 4: break
        if curr and len(lines) < 4: lines.append(curr)
        ny = y + lbl_h - 5*mm
        for line in lines:
            if ny < (y + (lbl_h * 0.22) + 16): break
            c.drawCentredString(x + lbl_w/2, ny, line)
            ny -= 11
        final_date = date_str if date_str else label_date
        c.setFont("Helvetica", 8)
        c.drawCentredString(x + lbl_w/2, y + 2*mm, f"{sku} - {final_date}")
    c.save()
    buffer.seek(0)
    return buffer

# =========================================================================
# INTERFAZ MULTIPLATAFORMA
# =========================================================================
st.set_page_config(page_title="Cotyland Nube", page_icon="🎈", layout="centered")

st.html("""
<style>
    button[data-testid="stMarkdownContainer"] p { font-size: 16px !important; font-weight: bold !important; }
    div[data-testid="stColumn"] button { height: 65px !important; font-size: 18px !important; font-weight: bold !important; border-radius: 12px !important; }
    div[data-testid="stColumn"]:nth-of-type(1) button { background-color: #D32F2F !important; color: white !important; border: none !important; }
    div[data-testid="stColumn"]:nth-of-type(2) button { background-color: #1976D2 !important; color: white !important; border: none !important; }
    div[data-testid="stColumn"]:nth-of-type(3) button { background-color: #388E3C !important; color: white !important; border: none !important; }
</style>
""")

st.title("🎈 Cotyland - Panel Multiplataforma")
tab0, tab1, tab2 = st.tabs(["📱 Buscador Móvil", "🖨️ Generador de Etiquetas (CSV)", "📊 Comparador de Precios"])

if "cola_impresion" not in st.session_state:
    st.session_state.cola_impresion = []

# -------------------------------------------------------------------------
# PESTAÑA 1: COLECTOR MÓVIL (Búsqueda cruzada Barcode + IdArticulo)
# -------------------------------------------------------------------------
with tab0:
    @st.cache_data(ttl=2)
    def descargar_base_drive(url):
        try:
            res = requests.get(url)
            if res.status_code == 200:
                content = res.content.decode("utf-8")
                lineas = content.splitlines()
                if not lineas: return None
                primera_linea = lineas[0]
                separador = ";" if primera_linea.count(";") > primera_linea.count(",") else ","
                
                reader = csv.reader(lineas, delimiter=separador, quoting=csv.QUOTE_NONE)
                next(reader)
                lista = []
                for r in reader:
                    if not r or len(r) < 3: continue
                    
                    sku_raw = r[0].replace('"', '').replace("'", "").strip()
                    desc = fix_encoding(r[1].replace('"', '').strip())
                    precio_raw = r[2].replace('"', '').strip()
                    # LEER COLUMNA 3 (IdArticulo interno del sistema)
                    id_art = r[3].replace('"', '').replace("'", "").strip() if len(r) > 3 else ""
                    
                    if not sku_raw or not desc: continue
                    lista.append({
                        "SKU_Original": sku_raw, 
                        "Id_Articulo": id_art,
                        "Descripción": desc, 
                        "Precio Crudo": precio_raw,
                        "Fecha": date.today().strftime("%d/%m/%y")
                    })
                return pd.DataFrame(lista)
        except: return None
        return None

    df_drive = descargar_base_drive(URL_DRIVE)
    
    if df_drive is None or df_drive.empty:
        st.error("⚠️ Error de lectura. Verificá que el Spreadsheet esté público.")
        df_drive = pd.DataFrame(columns=["SKU_Original", "Id_Articulo", "Descripción", "Precio Crudo", "Fecha"])
    else:
        st.caption(f"🟢 Base de datos unificada en vivo. {len(df_drive)} artículos activos cargados.")

    raw_query = st.text_input("🔎 ESCANEÁ O ESCRIBÍ ACÁ:", key="scanner_input", placeholder="Hacé foco acá con el lector...").strip()
    
    if raw_query:
        # Limpieza automática del punto para la comparación
        query_clean = raw_query.replace(".", "").strip().lower()
        
        # ⚡ BÚSQUEDA CRUZADA INTELIGENTE FIEL
        # Compara el texto limpio contra el Código de Barras O contra el IdArticulo interno
        condicion_sku = (df_drive["SKU_Original"].str.lower() == query_clean) | (df_drive["Id_Articulo"].str.lower() == query_clean)
        
        # Búsqueda tradicional por palabra clave en descripción
        keywords = query_clean.split()
        condicion_desc = pd.Series(True, index=df_drive.index)
        for kw in keywords:
            condicion_desc &= df_drive["Descripción"].str.lower().str.contains(kw)
            
        resultados = df_drive[condicion_sku | condicion_desc]
        
        if resultados.empty:
            st.warning(f"❌ No encontrado en el archivo: '{raw_query}'")
        else:
            if len(resultados) == 1:
                prod = resultados.iloc[0]
            else:
                opciones_mostrar = resultados.copy()
                opciones_mostrar["Etiqueta"] = opciones_mostrar["SKU_Original"] + " (ID: " + opciones_mostrar["Id_Articulo"] + ") - " + opciones_mostrar["Descripción"]
                seleccionado = st.selectbox("Múltiples opciones encontradas:", options=opciones_mostrar.index, format_func=lambda idx: opciones_mostrar.loc[idx, "Etiqueta"])
                prod = df_drive.loc[seleccionado]
            
            # Usamos preferentemente el IdInterno si se buscó por clave de sistema para armar el cartel
            codigo_impresion = prod['Id_Articulo'] if prod['Id_Articulo'] and query_clean in prod['Id_Articulo'].lower() else prod['SKU_Original']
            
            st.info(f"📦 **PRODUCTO:** {prod['Descripción']} \n\n 🔢 **CÓDIGO INTERNO:** {prod['Id_Articulo']} \n\n 🏷️ **CÓDIGO BARRAS:** {prod['SKU_Original']}")
            st.metric(label="💰 PRECIO EN GÓNDOLA", value=format_price_arg(prod["Precio Crudo"]))
            
            st.write("📐 **Mandar a Imprimir:**")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("🔴 GIGANTE", key="btn_g_u", use_container_width=True):
                    st.session_state.cola_impresion.append((codigo_impresion, prod["Descripción"], prod["Precio Crudo"], prod["Fecha"], "Gigante"))
                    st.toast("¡Agregado a Gigantes! 🔴")
            with c2:
                if st.button("🔵 MEDIANO", key="btn_m_u", use_container_width=True):
                    st.session_state.cola_impresion.append((codigo_impresion, prod["Descripción"], prod["Precio Crudo"], prod["Fecha"], "Mediano"))
                    st.toast("¡Agregado a Medianos! 🔵")
            with c3:
                if st.button("🟢 CHICO", key="btn_c_u", use_container_width=True):
                    st.session_state.cola_impresion.append((codigo_impresion, prod["Descripción"], prod["Precio Crudo"], prod["Fecha"], "Chico"))
                    st.toast("¡Agregado a Chicos! 🟢")

    if st.session_state.cola_impresion:
        st.write("---")
        st.subheader("📋 Tu Carrito de Impresión")
        df_cola = pd.DataFrame(st.session_state.cola_impresion, columns=["SKU", "Descripción", "Precio", "Fecha", "Tamaño"])
        df_cola.insert(0, "Quitar ❌", True)
        
        edited_cola = st.data_editor(df_cola, column_config={"Quitar ❌": st.column_config.CheckboxColumn(default=True)}, disabled=["SKU", "Descripción", "Precio", "Fecha", "Tamaño"], hide_index=True, use_container_width=True)
        df_limpio = edited_cola[edited_cola["Quitar ❌"] == True]
        st.session_state.cola_impresion = [(row["SKU"], row["Descripción"], row["Precio"], row["Fecha"], row["Tamaño"]) for _, row in df_limpio.iterrows()]
        
        if st.session_state.cola_impresion:
            lg = [x[:4] for x in st.session_state.cola_impresion if x[4] == "Gigante"]
            lm = [x[:4] for x in st.session_state.cola_impresion if x[4] == "Mediano"]
            lc = [x[:4] for x in st.session_state.cola_impresion if x[4] == "Chico"]
            
            st.write("")
            st.markdown("### 📥 Descargar Archivos Finales:")
            cg, cm, cc = st.columns(3)
            with cg:
                if lg and st.button(f"📥 PDF ({len(lg)}) Gigantes", key="dl_g", use_container_width=True):
                    pdf = generar_carteles_gigantes(lg)
                    st.download_button("Bajar", data=pdf, file_name="movil_gigantes.pdf", mime="application/pdf", use_container_width=True)
            with cm:
                if lm and st.button(f"📥 PDF ({len(lm)}) Medianos", key="dl_m", use_container_width=True):
                    pdf = generar_precios_medianos(lm)
                    st.download_button("Bajar", data=pdf, file_name="movil_medianos.pdf", mime="application/pdf", use_container_width=True)
            with cc:
                if lc and st.button(f"📥 PDF ({len(lc)}) Chicos", key="dl_c", use_container_width=True):
                    pdf = generar_etiquetas_chicas(lc)
                    st.download_button("Bajar", data=pdf, file_name="movil_chicos.pdf", mime="application/pdf", use_container_width=True)

# Pestañas masivas e históricas intactas
with tab1:
    st.subheader("1. Arrastrá tu archivo de precios")
    uploaded_file = st.file_uploader("Subir CSV de Precios", type=["csv"], key="unificado_etiquetas")
    if uploaded_file:
        try:
            bytes_data = uploaded_file.getvalue()
            content = bytes_data.decode("latin1")
            reader = csv.reader(content.splitlines())
            parsed_products = []
            for r in reader:
                if not r: continue
                if len(r) < 3: raise ValueError("Estructura inválida.")
                r_ext = list(r) + [""] * (5 - len(r))
                sku = r_ext[2].strip()
                parsed_products.append({"Imprimir": True, "SKU": sku if sku else "S/C", "Descripción": fix_encoding(r_ext[1].strip().strip('"')), "Precio Crudo": r_ext[0].strip(), "Fecha": r_ext[4].strip()})
            df_products = pd.DataFrame(parsed_products)
            st.success(f"✅ ¡Archivo leído! {len(df_products)} productos detectados.")
            selected_row = st.selectbox("🔎 Previsualizar:", options=range(len(df_products)), format_func=lambda idx: f"{df_products.iloc[idx]['SKU']} - {df_products.iloc[idx]['Descripción']}")
            edited_df = st.data_editor(df_products, column_config={"Imprimir": st.column_config.CheckboxColumn(default=True)}, disabled=["SKU", "Descripción", "Precio Crudo", "Fecha"], hide_index=True, use_container_width=True)
            df_filtrado = edited_df[edited_df["Imprimir"] == True]
            lista_final = [(row["SKU"], row["Descripción"], row["Precio Crudo"], row["Fecha"]) for _, row in df_filtrado.iterrows()]
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Descargar PDF Gigante", key="btn_g_csv"):
                    pdf = generar_carteles_gigantes(lista_final)
                    st.download_button("📥 Bajar Gigantes", data=pdf, file_name="carteles_gigantes_a4.pdf", mime="application/pdf", use_container_width=True)
            with col2:
                if st.button("Descargar PDF Mediano", key="btn_m_csv"):
                    pdf = generar_precios_medianos(lista_final)
                    st.download_button("📥 Bajar Medianos", data=pdf, file_name="precios_medianos_10x7.pdf", mime="application/pdf", use_container_width=True)
            with col3:
                if st.button("Descargar PDF Chico", key="btn_c_csv"):
                    pdf = generar_etiquetas_chicas(lista_final)
                    st.download_button("📥 Bajar Chicas", data=pdf, file_name="etiquetas_chicas_7x35.pdf", mime="application/pdf", use_container_width=True)
        except Exception as e: st.error(f"❌ Error: {e}")

with tab2:
    st.subheader("📊 Comparar Cambios de Precios")
    file_a = st.file_uploader("Subir Archivo de Lista (A)", type=["csv"], key="file_a_up")
    file_b = st.file_uploader("Subir Archivo de Lista (B)", type=["csv"], key="file_b_up")
    if file_a and file_b:
        if st.button("Cruzar Listas y Detectar Cambios", type="primary", use_container_width=True):
            try:
                def normalizar_precio(valor):
                    if pd.isna(valor): return None
                    s = str(valor).replace(".", "").replace(",", ".").strip()
                    try: return float(s)
                    except: return None
                def cargar_df_crudo(p):
                    df = pd.read_csv(p, sep=",", header=None, engine="python", dtype=str)
                    if df.shape[1] < 15: raise IndexError("Estructura inválida.")
                    df_res = pd.DataFrame({"SKU": df[9], "Descripcion": df[10], "Precio": df[14]})
                    df_res["Precio_num"] = df_res["Precio"].apply(normalizar_precio)
                    return df_res
                df_a = cargar_df_crudo(file_a)
                df_b = cargar_df_crudo(file_b)
                df_old, df_new = (df_a, df_b) if df_b["Precio_num"].mean() >= df_a["Precio_num"].mean() else (df_b, df_a)
                merged = pd.merge(df_old[["SKU", "Precio_num"]].rename(columns={"Precio_num": "Precio_old"}), df_new[["SKU", "Precio_num"]].rename(columns={"Precio_num": "Precio_new"}), on="SKU", how="inner")
                changed = merged[merged["Precio_old"] != merged["Precio_new"]]
                df_final = pd.merge(changed[["SKU"]], df_new[["SKU", "Descripcion", "Precio"]], on="SKU", how="left").rename(columns={"Precio": "Precio_Nuevo"})
                df_final = pd.merge(df_final, df_old[["SKU", "Precio"]].rename(columns={"Precio": "Precio_Anterior"}), on="SKU", how="left")[["SKU", "Descripcion", "Precio_Anterior", "Precio_Nuevo"]].sort_values("SKU")
                st.success(f"¡Se encontraron {len(df_final)} productos con cambios!")
                st.dataframe(df_final, use_container_width=True)
            except Exception as e: st.error(f"❌ Error: {e}")
