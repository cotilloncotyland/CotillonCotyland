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
# ID DE TU CARPETA / ARCHIVO DE DRIVE (CONFIGURADO)
# =========================================================================
# Reemplazá este ID con el ID real de tu archivo compartido en Drive:
ID_DRIVE = "1Jo4IsUcisgZJs0Aep9otQOCMNIHyJiXB" 
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
    s = str(price_str).replace("$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        value = float(s)
    except ValueError:
        return price_str.strip()
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
# INTERFAZ DE USUARIO CONFIGURADA
# =========================================================================
st.set_page_config(page_title="Cotyland Nube", page_icon="🎈", layout="centered")
st.title("🎈 Cotyland - Panel Multiplataforma")

st.html("""
<style>
    div[data-testid="stColumn"]:nth-of-type(1) button { background-color: #d32f2f !important; color: white !important; font-weight: bold !important; border: none !important; }
    div[data-testid="stColumn"]:nth-of-type(2) button { background-color: #1976d2 !important; color: white !important; font-weight: bold !important; border: none !important; }
    div[data-testid="stColumn"]:nth-of-type(3) button { background-color: #388e3c !important; color: white !important; font-weight: bold !important; border: none !important; }
</style>
""")

tab1, tab2, tab3 = st.tabs(["📱 Buscador Móvil (Drive)", "🖨️ Carga Masiva (CSV)", "📊 Comparador de Precios"])

if "cola_impresion" not in st.session_state:
    st.session_state.cola_impresion = []

# =========================================================================
# PESTAÑA 1: COLECTOR MÓVIL EN TIEMPO REAL CON PRE-FILTRADO Y AUTO-MUESTRA
# =========================================================================
with tab1:
    st.subheader("📱 Colector de Etiquetas desde el Celular")
    
    @st.cache_data(ttl=300)
    def descargar_base_drive(url):
        try:
            res = requests.get(url)
            if res.status_code == 200:
                content = res.content.decode("latin1")
                # Procesador ultra seguro línea por línea usando punto y coma (;)
                reader = csv.reader(content.splitlines(), delimiter=";")
                next(reader) # Saltear cabecera
                lista = []
                for r in reader:
                    if not r or len(r) < 3: continue
                    precio_raw = r[2].strip().replace(".", "").replace(",", ".")
                    try:
                        precio_f = float(precio_raw)
                        # REGLA SOLICITADA: Descartar estrictamente los precios en cero
                        if precio_f > 0:
                            lista.append({
                                "SKU": r[0].strip(),
                                "Descripción": fix_encoding(r[1].strip().strip('"')),
                                "Precio Crudo": r[2].strip(),
                                "Fecha": date.today().strftime("%d/%m/%y")
                            })
                    except:
                        continue
                return pd.DataFrame(lista)
        except:
            return None
        return None

    df_drive = descargar_base_drive(URL_DRIVE)
    
    if df_drive is None:
        st.error("⚠️ Error leyendo desde Drive. Comprobá que la carpeta esté compartida como pública.")
        df_drive = pd.DataFrame(columns=["SKU", "Descripción", "Precio Crudo", "Fecha"])
    else:
        st.caption(f"🟢 Conectado a Drive. Base de datos optimizada: {len(df_drive)} artículos activos con precio.")

    # Entrada de búsqueda única inteligente (Súper Combinada)
    query = st.text_input("🔎 Buscá por Código (completo/parcial) o palabras de la Descripción:", key="scanner_input", placeholder="Ej: caja 260 o punto sku...").strip().lower()
    
    if query:
        # Partir los términos por espacios para buscar "Caja" y "260" al mismo tiempo
        keywords = query.split()
        condicion = pd.Series(True, index=df_drive.index)
        
        for kw in keywords:
            condicion &= (df_drive["SKU"].str.lower().str.contains(kw)) | (df_drive["Descripción"].str.lower().str.contains(kw))
            
        resultados = df_drive[condicion]
        
        if resultados.empty:
            st.warning("❌ No se encontró ningún artículo que coincida.")
        elif len(resultados) == 1:
            # Opción única: Desplegar directo la ficha técnica
            prod = resultados.iloc[0]
            st.success(f"📦 Producto Seleccionado: {prod['Descripción']}")
            st.metric(label="Precio de Venta", value=format_price_arg(prod["Precio Crudo"]))
            st.text(f"SKU: {prod['SKU']}   |   Fecha: {prod['Fecha']}")
            
            st.write("📐 **¿A qué tamaño de cartel lo querés mandar?**")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("🔴 Gigante", key="btn_g_u"):
                    st.session_state.cola_impresion.append((prod["SKU"], prod["Descripción"], prod["Precio Crudo"], prod["Fecha"], "Gigante"))
                    st.toast("Agregado como Gigante 🔴")
            with c2:
                if st.button("🔵 Mediano", key="btn_m_u"):
                    st.session_state.cola_impresion.append((prod["SKU"], prod["Descripción"], prod["Precio Crudo"], prod["Fecha"], "Mediano"))
                    st.toast("Agregado como Mediano 🔵")
            with c3:
                if st.button("🟢 Chico", key="btn_c_u"):
                    st.session_state.cola_impresion.append((prod["SKU"], prod["Descripción"], prod["Precio Crudo"], prod["Fecha"], "Chico"))
                    st.toast("Agregado como Chico 🟢")
        else:
            # Múltiples opciones: Mostrar planilla interactiva para tocar la correcta
            st.info(f"Se encontraron {len(resultados)} opciones. Tocá el círculo a la izquierda de la correcta:")
            
            # Formatear visualmente para el selector móvil
            resultados_mostrar = resultados.copy()
            resultados_mostrar["Mostrar"] = resultados_mostrar["SKU"] + " - " + resultados_mostrar["Descripción"] + " (" + resultados_mostrar["Precio Crudo"] + ")"
            
            seleccionado = st.radio(
                "Resultados encontrados:",
                options=resultados_mostrar.index,
                format_func=lambda idx: resultados_mostrar.loc[idx, "Mostrar"],
                label_visibility="collapsed"
            )
            
            prod = df_drive.loc[seleccionado]
            st.markdown("---")
            st.success(f"📦 Producto Seleccionado: {prod['Descripción']}")
            st.metric(label="Precio de Venta", value=format_price_arg(prod["Precio Crudo"]))
            
            st.write("📐 **¿A qué tamaño de cartel lo querés mandar?**")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("🔴 Mandar a Gigante", key="btn_g_m_sel"):
                    st.session_state.cola_impresion.append((prod["SKU"], prod["Descripción"], prod["Precio Crudo"], prod["Fecha"], "Gigante"))
                    st.toast("Agregado como Gigante 🔴")
            with c2:
                if st.button("🔵 Mandar a Mediano", key="btn_m_m_sel"):
                    st.session_state.cola_impresion.append((prod["SKU"], prod["Descripción"], prod["Precio Crudo"], prod["Fecha"], "Mediano"))
                    st.toast("Agregado como Mediano 🔵")
            with c3:
                if st.button("🟢 Mandar a Chico", key="btn_c_m_sel"):
                    st.session_state.cola_impresion.append((prod["SKU"], prod["Descripción"], prod["Precio Crudo"], prod["Fecha"], "Chico"))
                    st.toast("Agregado como Chico 🟢")

    # Mostrar la canasta/cola de lo que va juntando con el teléfono
    if st.session_state.cola_impresion:
        st.write("---")
        st.subheader("📋 Artículos Juntados en el Recorrido")
        
        df_cola = pd.DataFrame(st.session_state.cola_impresion, columns=["SKU", "Descripción", "Precio", "Fecha", "Tamaño"])
        df_cola.insert(0, "Quitar ❌", True)
        
        edited_cola = st.data_editor(
            df_cola,
            column_config={"Quitar ❌": st.column_config.CheckboxColumn(default=True)},
            disabled=["SKU", "Descripción", "Precio", "Fecha", "Tamaño"],
            hide_index=True,
            use_container_width=True
        )
        
        # Actualizar la cola si destildó algo (acción de cerrar)
        df_limpio = edited_cola[edited_cola["Quitar ❌"] == True]
        st.session_state.cola_impresion = [
            (row["SKU"], row["Descripción"], row["Precio"], row["Fecha"], row["Tamaño"]) 
            for _, row in df_limpio.iterrows()
        ]
        
        if st.button("🗑️ Vaciar canasta por completo", use_container_width=True):
            st.session_state.cola_impresion = []
            st.rerun()
            
        st.write("---")
        st.subheader("🖨️ Finalizar y Armar PDFs")
        
        lg = [x[:4] for x in st.session_state.cola_impresion if x[4] == "Gigante"]
        lm = [x[:4] for x in st.session_state.cola_impresion if x[4] == "Mediano"]
        lc = [x[:4] for x in st.session_state.cola_impresion if x[4] == "Chico"]
        
        cg, cm, cc = st.columns(3)
        with cg:
            if lg:
                if st.button(f"📥 PDF {len(lg)} Gigantes", key="dl_g"):
                    pdf = generar_carteles_gigantes(lg)
                    st.download_button("Descargar", data=pdf, file_name="movil_gigantes.pdf", mime="application/pdf", use_container_width=True)
        with cm:
            if lm:
                if st.button(f"📥 PDF {len(lm)} Medianos", key="dl_m"):
                    pdf = generar_precios_medianos(lm)
                    st.download_button("Descargar", data=pdf, file_name="movil_medianos.pdf", mime="application/pdf", use_container_width=True)
        with cc:
            if lc:
                if st.button(f"📥 PDF {len(lc)} Chicos", key="dl_c"):
                    pdf = generar_etiquetas_chicas(lc)
                    st.download_button("Descargar", data=pdf, file_name="movil_chicos.pdf", mime="application/pdf", use_container_width=True)

# =========================================================================
# PESTAÑA 2: CARGA TRADICIONAL COMPLETA POR CSV
# =========================================================================
with tab2:
    st.subheader("Subir archivo completo de precios")
    uploaded_file = st.file_uploader("Subir CSV de Precios", type=["csv"], key="unificado_etiquetas")
    if uploaded_file:
        try:
            bytes_data = uploaded_file.getvalue()
            content = bytes_data.decode("latin1")
            reader = csv.reader(content.splitlines(), delimiter=";")
            parsed_products = []
            for r in reader:
                if not r or r[0].strip() == "Codigo_Barra": continue
                r_ext = list(r) + [""] * (5 - len(r))
                parsed_products.append({
                    "Imprimir": True, "SKU": r_ext[0].strip(),
                    "Descripción": fix_encoding(r_ext[1].strip().strip('"')),
                    "Precio Crudo": r_ext[2].strip(), "Fecha": date.today().strftime("%d/%m/%y")
                })
            df_products = pd.DataFrame(parsed_products)
            st.success(f"✅ ¡Archivo correcto! {len(df_products)} productos detectados.")
            
            edited_df = st.data_editor(df_products, column_config={"Imprimir": st.column_config.CheckboxColumn(default=True)}, disabled=["SKU", "Descripción", "Precio Crudo", "Fecha"], hide_index=True, use_container_width=True)
            df_filtrado = edited_df[edited_df["Imprimir"] == True]
            lista_final = [(row["SKU"], row["Descripción"], row["Precio Crudo"], row["Fecha"]) for _, row in df_filtrado.iterrows()]
            
            if lista_final:
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("Descargar PDF Gigante", key="btn_g_csv"):
                        pdf = generar_carteles_gigantes(lista_final)
                        st.download_button("📥 Bajar Gigantes", data=pdf, file_name="masivo_gigantes.pdf", mime="application/pdf", use_container_width=True)
                with col2:
                    if st.button("Descargar PDF Mediano", key="btn_m_csv"):
                        pdf = generar_precios_medianos(lista_final)
                        st.download_button("📥 Bajar Medianos", data=pdf, file_name="masivo_medianos.pdf", mime="application/pdf", use_container_width=True)
                with col3:
                    if st.button("Descargar PDF Chico", key="btn_c_csv"):
                        pdf = generar_etiquetas_chicas(lista_final)
                        st.download_button("📥 Bajar Chicas", data=pdf, file_name="masivo_chicas.pdf", mime="application/pdf", use_container_width=True)
        except Exception as e:
            st.error(f"❌ Error: {e}")

# =========================================================================
# PESTAÑA 3: COMPARADOR DE PRECIOS
# =========================================================================
with tab3:
    st.subheader("📊 Comparar Cambios de Precios")
    col_old, col_new = st.columns(2)
    with col_old: file_a = st.file_uploader("Subir Archivo de Lista (A)", type=["csv"], key="file_a_up")
    with col_new: file_b = st.file_uploader("Subir Archivo de Lista (B)", type=["csv"], key="file_b_up")
    if file_a and file_b:
        if st.button("Cruzar Listas y Detectar Cambios", type="primary", use_container_width=True):
            try:
                def normalizar_precio(valor):
                    if pd.isna(valor): return None
                    s = str(valor).replace(".", "").replace(",", ".").strip()
                    try: return float(s)
                    except: return None
                def cargar_df_crudo(p):
                    df = pd.read_csv(p, sep=";", header=None, engine="python", dtype=str, skiprows=1)
                    df_res = pd.DataFrame({"SKU": df[0], "Descripcion": df[1], "Precio": df[2]})
                    df_res["Precio_num"] = df_res["Precio"].apply(normalizar_precio)
                    return df_res
                df_a, df_b = cargar_df_crudo(file_a), cargar_df_crudo(file_b)
                if df_b["Precio_num"].mean() >= df_a["Precio_num"].mean(): df_old, df_new = df_a, df_b
                else: df_old, df_new = df_b, df_a
                merged = pd.merge(df_old[["SKU", "Precio_num"]].rename(columns={"Precio_num": "Precio_old"}), df_new[["SKU", "Precio_num"]].rename(columns={"Precio_num": "Precio_new"}), on="SKU", how="inner")
                changed = merged[merged["Precio_old"] != merged["Precio_new"]]
                if changed.empty: st.info("No se detectaron variaciones de precio.")
                else:
                    df_final = pd.merge(changed[["SKU"]], df_new[["SKU", "Descripcion", "Precio"]], on="SKU", how="left").rename(columns={"Precio": "Precio_Nuevo"})
                    df_final = pd.merge(df_final, df_old[["SKU", "Precio"]].rename(columns={"Precio": "Precio_Anterior"}), on="SKU", how="left")
                    df_final = df_final[["SKU", "Descripcion", "Precio_Anterior", "Precio_Nuevo"]].sort_values("SKU")
                    st.success(f"¡Se encontraron {len(df_final)} productos con cambios!")
                    st.dataframe(df_final, use_container_width=True)
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer: df_final.to_excel(writer, index=False)
                    excel_buffer.seek(0)
                    st.download_button("📥 Descargar Excel de Cambios (.xlsx)", data=excel_buffer, file_name="cambios_de_precios.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            except Exception as e: st.error(f"❌ Error: {e}")
