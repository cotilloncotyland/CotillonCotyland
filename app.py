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
# FUNCIONES AUXILIARES DE COMENTARIOS Y CORRECCIONES DE FORMATO
# =========================================================================
def fix_encoding(text: str) -> str:
    if text is None: return ""
    text = str(text)
    try: return text.encode("latin1").decode("utf-8")
    except Exception: return text

def format_price_arg(price_str: str) -> str:
    if not price_str: return ""
    s = price_str.replace("$", "").replace(" ", "")
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
# LÓGICA DE MOTOR PDF (ReportLab en Memoria)
# =========================================================================
def generar_carteles_grandes(data_rows):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    lbl_w, lbl_h = 10 * cm, 7 * cm
    margin_x, margin_y = (page_width - (2 * lbl_w)) / 2.0, (page_height - (4 * lbl_h)) / 2.0

    col, row = 0, 0
    for price, desc, code, date_str in data_rows:
        x = margin_x + col * lbl_w
        y = page_height - margin_y - (row + 1) * lbl_h
        c.setLineWidth(1)
        c.rect(x, y, lbl_w, lbl_h)
        
        inner_w = lbl_w - 0.6*cm
        desc_top = y + lbl_h - 0.3*cm
        
        # Descripcion
        desc_text = fix_encoding(desc).strip()
        if desc_text:
            f_size = 18
            while f_size >= 7:
                lines = wrap_text_to_width(desc_text, "Helvetica-Bold", f_size, inner_w)
                if len(lines) * f_size * 1.15 <= (lbl_h * 0.38): break
                f_size -= 1
            c.setFont("Helvetica-Bold", f_size)
            curr_y = desc_top - f_size
            for line in lines:
                c.drawString(x + 0.3*cm + (inner_w - pdfmetrics.stringWidth(line, "Helvetica-Bold", f_size))/2.0, curr_y, line)
                curr_y -= f_size * 1.15

        # Precio
        price_text = format_price_arg(price).strip()
        if price_text:
            f_size = min(90, (lbl_h * 0.5))
            while f_size > 18:
                if pdfmetrics.stringWidth(price_text, "Helvetica-Bold", f_size) <= inner_w: break
                f_size -= 1
            c.setFont("Helvetica-Bold", f_size)
            c.drawString(x + 0.3*cm + (inner_w - pdfmetrics.stringWidth(price_text, "Helvetica-Bold", f_size))/2.0, y + 1.2*cm, price_text)

        # Footer
        footer = f"{str(code).strip()}   {str(date_str).strip()}"
        c.setFont("Helvetica", 10)
        c.drawString(x + 0.3*cm + (inner_w - pdfmetrics.stringWidth(footer, "Helvetica", 10))/2.0, y + 0.4*cm, footer)

        col += 1
        if col >= 2: col, row = 0, row + 1
        if row >= 4: c.showPage(); row, col = 0, 0
    c.save()
    buffer.seek(0)
    return buffer

def generar_precios_medianos(products_list):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    lbl_w, lbl_h = A4[0] - 10*mm, (A4[1] - 15*mm) / 2
    for i, (sku, name, price) in enumerate(products_list):
        pos = i % 2
        if i != 0 and pos == 0: c.showPage()
        x, y = 5*mm, ((A4[1] - 5*mm - lbl_h) if pos == 0 else 5*mm)
        c.rect(x, y, lbl_w, lbl_h)
        
        price_txt = f"$ {price}"
        f_size = 110
        while c.stringWidth(price_txt, "Helvetica-Bold", f_size) > (lbl_w - 20) and f_size > 20: f_size -= 5
        c.setFont("Helvetica-Bold", f_size)
        c.drawString(x + (lbl_w - c.stringWidth(price_txt, "Helvetica-Bold", f_size))/2, y + lbl_h/2 - f_size/2 + 5, price_txt)

        c.setFont("Helvetica-Bold", 22)
        words = name.split()
        lines, curr = [], ""
        for w in words:
            test = w if not curr else curr + " " + w
            if c.stringWidth(test, "Helvetica-Bold", 22) <= (lbl_w - 40): curr = test
            else:
                if curr: lines.append(curr)
                curr = w
                if len(lines) == 1: break
        if curr and len(lines) < 2: lines.append(curr)
        
        ny = y + lbl_h - 45
        for line in lines:
            c.drawCentredString(x + lbl_w/2, ny, line)
            ny -= 27
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(x + lbl_w/2, y + 14, f"{sku}  {date.today().strftime('%d/%m/%Y')}")
    c.save()
    buffer.seek(0)
    return buffer

def generar_etiquetas_chicas(products_list):
    buffer = io.BytesIO()
    w_page, h_page = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=(w_page, h_page))
    lbl_w, lbl_h = 70*mm, 35*mm
    cols, rows = int((w_page - 10*mm + 2*mm) // (lbl_w + 2*mm)), int((h_page - 10*mm + 2*mm) // (lbl_h + 2*mm))
    per_page = cols * rows

    for i, (sku, name, price) in enumerate(products_list):
        if i > 0 and i % per_page == 0: c.showPage()
        pos = i % per_page
        r, col = pos // cols, pos % cols
        x = 5*mm + col * (lbl_w + 2*mm)
        y = h_page - 5*mm - ((r + 1) * (lbl_h + 2*mm)) + 2*mm

        c.setLineWidth(0.5)
        c.rect(x, y, lbl_w, lbl_h)
        c.setFont("Helvetica-Bold", 30)
        price_txt = f"$ {price}"
        c.drawString(x + (lbl_w - c.stringWidth(price_txt, "Helvetica-Bold", 30))/2, y + (lbl_h * 0.25), price_txt)

        c.setFont("Helvetica-Bold", 9)
        words = name.split()
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
            if ny < (y + (lbl_h * 0.25) + 22): break
            c.drawCentredString(x + lbl_w/2, ny, line)
            ny -= 11
        c.setFont("Helvetica", 8)
        c.drawCentredString(x + lbl_w/2, y + 2*mm, f"{sku} - {date.today().strftime('%d/%m/%y')}")
    c.save()
    buffer.seek(0)
    return buffer

# =========================================================================
# INTERFAZ WEB APLICACIÓN
# =========================================================================
st.set_page_config(page_title="Cotyland Nube", page_icon="🎈", layout="centered")
st.title("🎈 Cotyland - Panel Multiplataforma")

tab1, tab2 = st.tabs(["🖨️ Generador de Etiquetas", "📊 Comparador de Precios"])

with tab1:
    st.subheader("1. Arrastrá tu archivo de precios")
    uploaded_file = st.file_uploader("Subir CSV de Precios", type=["csv"], key="unificado_etiquetas")
    
    if uploaded_file:
        bytes_data = uploaded_file.getvalue()
        content = bytes_data.decode("latin1")
        reader = csv.reader(content.splitlines())
        
        rows_grandes, products_med_chico = [], []
        for r in reader:
            if not r: continue
            r_ext = list(r) + [""] * (5 - len(r))
            rows_grandes.append((r_ext[0], r_ext[1], r_ext[2], r_ext[4]))
            products_med_chico.append((r_ext[2].strip(), r_ext[1].strip().strip('"'), r_ext[0].strip().replace("$","").strip().replace(".",",")))
        
        st.success(f"CSV cargado correctamente ({len(rows_grandes)} productos).")
        st.write("---")
        st.subheader("2. Elegí el tamaño que necesitás imprimir:")

        with st.container(border=True):
            st.markdown("### 🔲 Opción A: Carteles Grandes (10x7 cm)")
            st.caption("Especial para góndolas o exhibidores principales. Entran 8 por hoja A4 (2 columnas x 4 filas).")
            st.code("📝 MUESTRA:\n[ DESCRIPCIÓN DEL PRODUCTO ]\n         $ 1.250,00\nART-1234      07/07/2026", language="text")
            st.write("")
            if st.button("Generar Carteles Grandes", use_container_width=True):
                pdf = generar_carteles_grandes(rows_grandes)
                st.download_button("📥 Descargar PDF Grande", data=pdf, file_name="carteles_grandes_10x7.pdf", mime="application/pdf", use_container_width=True)

        with st.container(border=True):
            st.markdown("### 🔲 Opción B: Precios Medianos (Mitad de A4)")
            st.caption("Carteles gigantes de oferta. Entran exactamente 2 por hoja vertical.")
            st.code("📝 MUESTRA:\n[ PRODUCTO EN PROMO ]\n         $ 4.500\nART-5566      07/07/2026", language="text")
            st.write("")
            if st.button("Generar Precios Medianos", use_container_width=True):
                pdf = generar_precios_medianos(products_med_chico)
                st.download_button("📥 Descargar PDF Mediano", data=pdf, file_name="precios_medianos_a4.pdf", mime="application/pdf", use_container_width=True)

        with st.container(border=True):
            st.markdown("### 🔲 Opción C: Etiquetas Chicas (7x3.5 cm)")
            st.caption("Ideales para pegar directo en artículos chicos o estanterías compactas. Formato apaisado (A4 Horizontal).")
            st.code("📝 MUESTRA:\n[ NOMBRE ARTÍCULO ]\n         $ 450\nART-999 - 07/07/26", language="text")
            st.write("")
            if st.button("Generar Etiquetas Chicas", use_container_width=True):
                pdf = generar_etiquetas_chicas(products_med_chico)
                st.download_button("📥 Descargar PDF Chico", data=pdf, file_name="etiquetas_chicas_7x35.pdf", mime="application/pdf", use_container_width=True)

with tab2:
    st.subheader("📊 Comparar Cambios de Precios")
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
