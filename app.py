import streamlit as st
import pandas as pd
import csv
import io
from datetime import date
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics

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
    try:
        return text.encode("latin1").decode("utf-8")
    except Exception:
        return text

def format_price_arg(price_str: str) -> str:
    if not price_str: return ""
    s = str(price_str).replace("$", "").replace(" ", "")
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
        if pdfmetrics.stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines

# =========================================================================
# MOTOR PDF OPTIMIZADO
# =========================================================================
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
# INTERFAZ DE USUARIO
# =========================================================================
st.set_page_config(page_title="Cotyland Nube", page_icon="🎈", layout="centered")
st.title("🎈 Cotyland - Panel Multiplataforma")

# --- TRUCO CSS BLINDADO PARA DARLE COLOR A LOS BOTONES POR SU ID ---
st.html("""
<style>
    div[data-testid="stColumn"]:nth-of-type(1) button {
        background-color: #d32f2f !important;
        color: white !important;
        font-weight: bold !important;
        border: none !important;
    }
    div[data-testid="stColumn"]:nth-of-type(2) button {
        background-color: #1976d2 !important;
        color: white !important;
        font-weight: bold !important;
        border: none !important;
    }
    div[data-testid="stColumn"]:nth-of-type(3) button {
        background-color: #388e3c !important;
        color: white !important;
        font-weight: bold !important;
        border: none !important;
    }
</style>
""")

tab1, tab2 = st.tabs(["🖨️ Generador de Etiquetas", "📊 Comparador de Precios"])

with tab1:
    st.subheader("1. Arrastrá tu archivo de precios")
    uploaded_file = st.file_uploader("Subir CSV de Precios", type=["csv"], key="unificado_etiquetas")
    
    if uploaded_file:
        bytes_data = uploaded_file.getvalue()
        content = bytes_data.decode("latin1")
        reader = csv.reader(content.splitlines())
        
        parsed_products = []
        for r in reader:
            if not r: continue
            r_ext = list(r) + [""] * (5 - len(r))
            sku = r_ext[2].strip()
            parsed_products.append({
                "Imprimir": True,
                "SKU": sku if sku else "S/C",
                "Descripción": fix_encoding(r_ext[1].strip().strip('"')),
                "Precio Crudo": r_ext[0].strip(),
                "Fecha": r_ext[4].strip()
            })
            
        df_products = pd.DataFrame(parsed_products)
        
        st.write("---")
        st.subheader("2. Seleccioná un producto para PREVISUALIZAR o desmarcalo:")
        
        selected_row = st.selectbox(
            "🔎 Elegí un producto para ver el boceto real en pantalla:",
            options=range(len(df_products)),
            format_func=lambda idx: f"{df_products.iloc[idx]['SKU']} - {df_products.iloc[idx]['Descripción']} ({format_price_arg(df_products.iloc[idx]['Precio Crudo'])})"
        )
        
        p_view = df_products.iloc[selected_row]
        p_txt = format_price_arg(p_view["Precio Crudo"])
        d_txt = p_view["Descripción"]
        s_txt = p_view["SKU"]
        f_txt = p_view["Fecha"] if p_view["Fecha"] else date.today().strftime("%d/%m/%y")
        
        with st.container(border=True):
            st.write("👁️ **VISTA PREVIA DEL CARTEL SELECCIONADO**")
            st.subheader(d_txt)
            st.metric(label="Precio Final (Grosor Máximo Auto-Ajustable)", value=p_txt)
            st.text(f"Código: {s_txt}   |   Fecha: {f_txt}")

        st.write("")
        edited_df = st.data_editor(
            df_products,
            column_config={
                "Imprimir": st.column_config.CheckboxColumn(help="Desmarcar para quitar del PDF", default=True),
                "SKU": st.column_config.TextColumn(disabled=True),
                "Descripción": st.column_config.TextColumn(disabled=True),
                "Precio Crudo": st.column_config.TextColumn(disabled=True),
                "Fecha": st.column_config.TextColumn(disabled=True),
            },
            disabled=["SKU", "Descripción", "Precio Crudo", "Fecha"],
            hide_index=True,
            use_container_width=True
        )
        
        df_filtrado = edited_df[edited_df["Imprimir"] == True]
        lista_final = []
        for _, row in df_filtrado.iterrows():
            lista_final.append((row["SKU"], row["Descripción"], row["Precio Crudo"], row["Fecha"]))
            
        st.write("---")
        st.subheader("3. Descargar Formato de Impresión:")
        
        if len(lista_final) == 0:
            st.warning("⚠️ No seleccionaste ningún producto para imprimir.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                with st.container(border=True):
                    st.markdown("🔴 **Opción A**\n\nCarteles Gigantes\n*(Ofertas - 2 por A4)*")
                    if st.button("Descargar PDF Gigante", use_container_width=True):
                        pdf = generar_carteles_gigantes(lista_final)
                        st.download_button("📥 Bajar Gigantes", data=pdf, file_name="carteles_gigantes_a4.pdf", mime="application/pdf", use_container_width=True)

            with col2:
                with st.container(border=True):
                    st.markdown("🔵 **Opción B**\n\nPrecios Medianos\n*(Góndola - 10x7 cm)*")
                    if st.button("Descargar PDF Mediano", use_container_width=True):
                        pdf = generar_precios_medianos(lista_final)
                        st.download_button("📥 Bajar Medianos", data=pdf, file_name="precios_medianos_10x7.pdf", mime="application/pdf", use_container_width=True)

            with col3:
                with st.container(border=True):
                    st.markdown("🟢 **Opción C**\n\nEtiquetas Chicas\n*(Artículos - 7x3.5 cm)*")
                    if st.button("Descargar PDF Chico", use_container_width=True):
                        pdf = generar_etiquetas_chicas(lista_final)
                        st.download_button("📥 Bajar Chicas", data=pdf, file_name="etiquetas_chicas_7x35.pdf", mime="application/pdf", use_container_width=True)

with tab2:
    st.subheader("📊 Comparador de Cambios de Precios")
    st.write("Subí las dos listas que descargaste del sistema para cruzar los datos automáticamente.")
    
    col_old, col_new = st.columns(2)
    with col_old:
        file_old = st.file_uploader("1. Archivo Viejo (Anterior)", type=["csv"], key="v_up")
    with col_new:
        file_new = st.file_uploader("2. Archivo Nuevo (Actual)", type=["csv"], key="n_up")
        
    if file_old and file_new:
        if st.button("Cruzar Listas y Detectar Cambios", type="primary", use_container_width=True):
            try:
                def normalizar_precio(valor):
                    if pd.isna(valor): return None
                    s = str(valor).replace(".", "").replace(",", ".").strip()
                    try: return float(s)
                    except: return None

                def cargar_df(p):
                    df = pd.read_csv(p, sep=",", header=None, engine="python", dtype=str)
                    return pd.DataFrame({"SKU": df[9], "Descripcion": df[10], "Precio": df[14]})

                df_old, df_new = cargar_df(file_old), cargar_df(file_new)
                df_old["Precio_num"] = df_old["Precio"].apply(normalizar_precio)
                df_new["Precio_num"] = df_new["Precio"].apply(normalizar_precio)

                merged = pd.merge(df_old[["SKU", "Precio_num"]].rename(columns={"Precio_num": "Precio_old"}),
                                  df_new[["SKU", "Precio_num"]].rename(columns={"Precio_num": "Precio_new"}), on="SKU", how="inner")
                changed = merged[merged["Precio_old"] != merged["Precio_new"]]

                if changed.empty:
                    st.info("No se detectaron variaciones de precio.")
                else:
                    df_final = pd.merge(changed[["SKU"]], df_new[["SKU", "Descripcion", "Precio"]], on="SKU", how="left").rename(columns={"Precio": "Precio_nuevo"})
                    df_final = pd.merge(df_final, df_old[["SKU", "Precio"]].rename(columns={"Precio": "Precio_anterior"}), on="SKU", how="left")
                    df_final = df_final[["SKU", "Descripcion", "Precio_anterior", "Precio_nuevo"]].sort_values("SKU")

                    st.success(f"¡Se encontraron {len(df_final)} productos con cambios!")
                    st.dataframe(df_final, use_container_width=True)
                    
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        df_final.to_excel(writer, index=False)
                    excel_buffer.seek(0)
                    
                    st.download_button("📥 Descargar Excel de Cambios (.xlsx)", data=excel_buffer, file_name="cambios_de_precios.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            except Exception as e:
                st.error(f"Error procesando los CSV: {e}")
