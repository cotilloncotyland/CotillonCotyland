import streamlit as st
import pandas as pd
import csv
import io
import requests
import base64
from datetime import date
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics

# ID unificado de tu Google Sheets público
ID_DRIVE = "1z1naxcQyryThMHj3H9K3xi27EDuugBPnFKrrwrJ8v1Y" 
URL_DRIVE = f"https://docs.google.com/spreadsheets/d/{ID_DRIVE}/export?format=csv"

# =========================================================================
# FUNCIONES DE ARREGLO Y DECODIFICACIÓN
# =========================================================================
def fix_encoding(text: str) -> str:
    if text is None: return ""
    text = str(text)
    replacements = {
        "Ã\x91": "Ñ", "Ã±": "ñ", "Ã\x81": "Á", "Ã\x89": "É", 
        "Ã\x8d": "Í", "Ã\x93": "Ó", "Ã\x9a": "Ú", "Ã¡": "á", 
        "Ã©": "é", "Ã­": "í", "Ã³": "ó", "Ãº": "ú",
        "NÅ°": "N°", "NÂ°": "N°", "NÂ": "N°"
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
# FUNCIÓN INYECTADORA DE IMPRESIÓN DIRECTA
# =========================================================================
def embeber_e_imprimir_pdf(bytes_pdf, key_boton):
    """Genera un botón que abre el PDF limpio en una pestaña nueva y lanza la impresión en el acto"""
    base64_pdf = base64.b64encode(bytes_pdf).decode('utf-8')
    
    componente_html = f"""
    <script>
        function ejecutarImpresion() {{
            var byteCharacters = atob("{base64_pdf}");
            var byteNumbers = new Array(byteCharacters.length);
            for (var i = 0; i < byteCharacters.length; i++) {{
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }}
            var byteArray = new Uint8Array(byteNumbers);
            var blob = new Blob([byteArray], {{type: 'application/pdf'}});
            var fileURL = URL.createObjectURL(blob);
            
            var win = window.open(fileURL);
            if (win) {{
                setTimeout(function() {{
                    win.focus();
                    win.print();
                }}, 300);
            }} else {{
                alert("❌ Por favor habilitá las ventanas emergentes (pop-ups) en tu navegador para imprimir directo.");
            }}
        }}
    </script>
    <button onclick="ejecutarImpresion()" style="
        width: 100%;
        height: 45px;
        background-color: #FF9800;
        color: white;
        border: none;
        font-size: 16px;
        font-weight: bold;
        border-radius: 8px;
        cursor: pointer;
        box-shadow: 0px 4px 6px rgba(0,0,0,0.1);
        margin-top: 5px;
    ">🖨️ Mandar a Imprimir Directo</button>
    """
    st.components.v1.html(componente_html, height=60)

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
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(x + lbl_w/2, y + 14, f"{sku}  {date_str if date_str else label_date}")
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def generar_precios_medianos(data_rows):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    lbl_w, lbl_h = 100 * mm, 70 * mm
    margin_x, margin_y = (page_width - (2 * lbl_w)) / 2.0, (page_height - (4 * lbl_h)) / 2.0
    col, row = 0, 0
    for sku, name, price, date_str in data_rows:
        x = margin_x + col * lbl_w
        y = page_height - margin_y - (row + 1) * lbl_h
        c.rect(x, y, lbl_w, lbl_h)
        inner_w = lbl_w - 6*mm
        desc_text = fix_encoding(name).strip()
        if desc_text:
            f_size = 18
            while f_size >= 7:
                lines = wrap_text_to_width(desc_text, "Helvetica-Bold", f_size, inner_w)
                if len(lines) * f_size * 1.15 <= (lbl_h * 0.35): break
                f_size -= 1
            c.setFont("Helvetica-Bold", f_size)
            curr_y = y + lbl_h - 3*mm - f_size
            for line in lines:
                c.drawString(x + 3*mm + (inner_w - pdfmetrics.stringWidth(line, "Helvetica-Bold", f_size))/2.0, curr_y, line)
                curr_y -= f_size * 1.15
        price_text = format_price_arg(price).strip()
        if price_text:
            f_size = 95
            while f_size > 14:
                if pdfmetrics.stringWidth(price_text, "Helvetica-Bold", f_size) <= inner_w: break
                f_size -= 1
            c.setFont("Helvetica-Bold", f_size)
            c.drawString(x + 3*mm + (inner_w - pdfmetrics.stringWidth(price_text, "Helvetica-Bold", f_size))/2.0, y + 11*mm, price_text)
        footer = f"{str(sku).strip()}   {str(date_str).strip()}"
        c.setFont("Helvetica", 10)
        c.drawString(x + 3*mm + (inner_w - pdfmetrics.stringWidth(footer, "Helvetica", 10))/2.0, y + 3*mm, footer)
        col += 1
        if col >= 2: col, row = 0, row + 1
        if row >= 4: c.showPage(); row, col = 0, 0
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

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
        c.setFont("Helvetica", 8)
        c.drawCentredString(x + lbl_w/2, y + 2*mm, f"{sku} - {date_str if date_str else label_date}")
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

# =========================================================================
# INTERFAZ DE STREAMLIT
# =========================================================================
st.set_page_config(page_title="Cotyland Nube", page_icon="🎈", layout="wide")

# Interceptador F11 de PC invariable y blindado
st.components.v1.html("""
<script>
    window.parent.document.addEventListener('keydown', function(e) {
        if (e.key === 'F11' || e.keyCode === 122) {
            e.preventDefault(); 
            setTimeout(function() {
                var inputBuscador = window.parent.document.querySelector('input[type="text"]');
                if (inputBuscador) {
                    inputBuscador.dispatchEvent(new Event('change', { bubbles: true }));
                    var eventoEnter = new KeyboardEvent('keydown', {
                        bubbles: true, cancelable: true, key: 'Enter', keyCode: 13, which: 13
                    });
                    inputBuscador.dispatchEvent(eventoEnter);
                }
            }, 5);
        }
    });
</script>
""", height=0)

st.html("""
<style>
    button[data-testid="stMarkdownContainer"] p { font-size: 16px !important; font-weight: bold !important; }
    div[data-testid="stColumn"] button { height: 50px !important; font-size: 16px !important; font-weight: bold !important; border-radius: 10px !important; }
    div[data-testid="stDataFrame"] iframe { width: 100% !important; }
</style>
""")

st.title("🎈 Cotyland - Panel Multiplataforma")
tab0, tab1, tab2 = st.tabs(["📱 Buscador Móvil", "🖨️ Generador de Etiquetas (CSV)", "📊 Comparador de Precios"])

if "cola_impresion" not in st.session_state:
    st.session_state.cola_impresion = []
if "ultimo_producto" not in st.session_state:
    st.session_state.ultimo_producto = ""

with tab0:
    @st.cache_data(ttl="2s")
    def descargar_base_estatica(url):
        try:
            res = requests.get(url)
            if res.status_code == 200:
                content = res.content.decode("utf-8")
                lineas = content.splitlines()
                separador = ";" if lineas[0].count(";") > lineas[0].count(",") else ","
                reader = csv.reader(lineas, delimiter=separador)
                next(reader)
                lista = []
                for r in reader:
                    if not r or len(r) < 3: continue
                    sku_orig = r[0].strip()
                    desc = fix_encoding(r[1].strip())
                    precio = r[2].strip()
                    id_orig = r[3].strip() if len(r) > 3 else ""
                    
                    lista.append({
                        "SKU_Original": sku_orig, 
                        "SKU_Norm": sku_orig.replace(".", "").lstrip("0").lower(),
                        "Id_Articulo": id_orig, 
                        "Id_Norm": id_orig.replace(".", "").lstrip("0").lower(),
                        "Descripción": desc, "Precio Crudo": precio,
                        "Fecha": date.today().strftime("%d/%m/%y")
                    })
                return pd.DataFrame(lista)
        except: return None
        return None

    df_drive = descargar_base_estatica(URL_DRIVE)
    
    if df_drive is None or df_drive.empty:
        st.error("⚠️ Error cargando base de datos estática.")
        df_drive = pd.DataFrame()
    else:
        st.caption(f"🟢 Motor de Alta Velocidad Activo: {len(df_drive)} artículos en caché RAM.")

    st.markdown("### 🎛️ Configuración de Tanda de Escaneo:")
    tamanio_elegido = st.radio("Seleccioná qué tamaño querés que se guarde automáticamente al escanear:", ["🟢 Chico", "🔵 Mediano", "🔴 Gigante"], horizontal=True)

    def procesar_colector_veloz():
        query_cruda = st.session_state.colector_input.strip()
        if query_cruda:
            query_norm = query_cruda.replace("F11", "").replace(".", "").lstrip("0").lower()
            if query_norm:
                condicion = (df_drive["SKU_Norm"] == query_norm) | (df_drive["Id_Norm"] == query_norm)
                resultados = df_drive[condicion]
                
                if not resultados.empty:
                    prod = resultados.iloc[0]
                    codigo_impresion = prod['Id_Articulo'] if prod['Id_Articulo'] else prod['SKU_Original']
                    tipo_str = tamanio_elegido.split(" ")[1]
                    
                    st.session_state.cola_impresion.append((
                        codigo_impresion, prod["Descripción"], prod["Precio Crudo"], prod["Fecha"], tipo_str
                    ))
                    
                    st.session_state.cola_impresion = sorted(st.session_state.cola_impresion, key=lambda x: x[1].lower())
                    st.session_state.ultimo_producto = f"✅ Agregado: {prod['Descripción']} ({tamanio_elegido}) - {format_price_arg(prod['Precio Crudo'])}"
                else:
                    st.session_state.ultimo_producto = f"❌ Código no encontrado: '{query_cruda}'"
        
        st.session_state.colector_input = ""

    st.text_input("🔎 ESCANEÁ ACÁ (MODO CORRELATIVO CONSTANTE):", key="colector_input", on_change=procesar_colector_veloz, placeholder="Hacé foco acá y pasá los códigos de corrido...")

    if st.session_state.ultimo_producto:
        st.info(st.session_state.ultimo_producto)

    if st.session_state.cola_impresion:
        st.write("---")
        st.subheader("📋 Lista Correlativa de Impresión Actual (Ordenada Alfabéticamente)")
        
        df_cola = pd.DataFrame(st.session_state.cola_impresion, columns=["SKU", "Descripción", "Precio", "Fecha", "Tamaño"])
        df_cola.insert(0, "Quitar ❌", True)
        
        edited_cola = st.data_editor(
            df_cola, 
            column_config={
                "Quitar ❌": st.column_config.CheckboxColumn(default=True),
                "Descripción": st.column_config.TextColumn(width="large")
            }, 
            disabled=["SKU", "Descripción", "Precio", "Fecha", "Tamaño"], 
            hide_index=True, 
            use_container_width=True, 
            key="tabla_viva"
        )
        st.session_state.cola_impresion = [(row["SKU"], row["Descripción"], row["Precio"], row["Fecha"], row["Tamaño"]) for _, row in edited_cola[edited_cola["Quitar ❌"] == True].iterrows()]
        
        if st.session_state.cola_impresion:
            lg = [x[:4] for x in st.session_state.cola_impresion if x[4] == "Gigante"]
            lm = [x[:4] for x in st.session_state.cola_impresion if x[4] == "Mediano"]
            lc = [x[:4] for x in st.session_state.cola_impresion if x[4] == "Chico"]
            
            st.markdown("### 📥 Panel de Salida Masiva:")
            cg, cm, cc = st.columns(3)
            with cg:
                if lg:
                    st.write(f"**🔴 GIGANTES ({len(lg)})**")
                    pdf_g = generar_carteles_gigantes(lg)
                    st.download_button("⬇️ Descargar", data=pdf_g, file_name="gigantes.pdf", mime="application/pdf", use_container_width=True, key="f_g")
                    embeber_e_imprimir_pdf(pdf_g, "p_g")
            with cm:
                if lm:
                    st.write(f"**🔵 MEDIANOS ({len(lm)})**")
                    pdf_m = generar_precios_medianos(lm)
                    st.download_button("⬇️ Descargar", data=pdf_m, file_name="medianos.pdf", mime="application/pdf", use_container_width=True, key="f_m")
                    embeber_e_imprimir_pdf(pdf_m, "p_m")
            with cc:
                if lc:
                    st.write(f"**🟢 CHICOS ({len(lc)})**")
                    pdf_c = generar_etiquetas_chicas(lc)
                    st.download_button("⬇️ Descargar", data=pdf_c, file_name="chicos.pdf", mime="application/pdf", use_container_width=True, key="f_c")
                    embeber_e_imprimir_pdf(pdf_c, "p_c")

# Pestañas complementarias intactas
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
            edited_df = st.data_editor(df_products, column_config={"Imprimir": st.column_config.CheckboxColumn(default=True)}, disabled=["SKU", "Descripción", "Precio Crudo", "Fecha"], hide_index=True, use_container_width=True)
            df_filtrado = edited_df[edited_df["Imprimir"] == True]
            lista_final = [(row["SKU"], row["Descripción"], row["Precio Crudo"], row["Fecha"]) for _, row in df_filtrado.iterrows()]
            
            col1, col2, col3 = st.columns(3)
            with col1:
                pdf_csv_g = generar_carteles_gigantes(lista_final)
                st.download_button("📥 Bajar Gigantes", data=pdf_csv_g, file_name="carteles_gigantes_a4.pdf", mime="application/pdf", use_container_width=True, key="c_g")
                embeber_e_imprimir_pdf(pdf_csv_g, "csv_p_g")
            with col2:
                pdf_csv_m = generar_precios_medianos(lista_final)
                st.download_button("📥 Bajar Medianos", data=pdf_csv_m, file_name="precios_medianos_10x7.pdf", mime="application/pdf", use_container_width=True, key="c_m")
                embeber_e_imprimir_pdf(pdf_csv_m, "csv_p_m")
            with col3:
                pdf_csv_c = generar_etiquetas_chicas(lista_final)
                st.download_button("📥 Bajar Chicas", data=pdf_csv_c, file_name="etiquetas_chicas_7x35.pdf", mime="application/pdf", use_container_width=True, key="c_c")
                embeber_e_imprimir_pdf(pdf_csv_c, "csv_p_c")
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
                df_final = pd.merge(df_final, df_old[["SKU", "Precio"]].rename(columns={"Precio": "Precio_Anterior"}), on="SKU", how="left")[["SKU", "Descripcion", "Precio_Anterior", "Precio_Nuevo"]]
                
                df_final["Descripcion_upper"] = df_final["Descripcion"].fillna("").str.upper()
                df_final = df_final.sort_values("Descripcion_upper").drop(columns=["Descripcion_upper"])
                
                st.session_state.df_comparativa = df_final.copy()
                st.session_state.df_comparativa.insert(0, "🖨️ Seleccionar", False)
                st.success(f"¡Se encontraron {len(df_final)} productos con cambios!")
                
            except Exception as e: 
                st.error(f"❌ Error: {e}")

        if "df_comparativa" in st.session_state and not st.session_state.df_comparativa.empty:
            st.markdown("### 📋 Listado de Cambios Detectados")
            st.caption("Tildá los productos específicos que querés mandar a la tanda de impresión masiva de abajo:")
            
            edited_comp = st.data_editor(
                st.session_state.df_comparativa,
                column_config={
                    "🖨️ Seleccionar": st.column_config.CheckboxColumn(default=False, width="small"),
                    "SKU": st.column_config.TextColumn(width="small"),
                    "Descripcion": st.column_config.TextColumn(title="Descripción del Producto", width="large"),
                    "Precio_Anterior": st.column_config.TextColumn(width="small"),
                    "Precio_Nuevo": st.column_config.TextColumn(width="small")
                },
                disabled=["SKU", "Descripcion", "Precio_Anterior", "Precio_Nuevo"],
                hide_index=True,
                use_container_width=True,
                key="tabla_edicion_comparativa"
            )
            
            df_tildados = edited_comp[edited_comp["🖨️ Seleccionar"] == True]
            cant_items = len(df_tildados)
            
            st.markdown("### 📥 Impresión Rápida de Cambios:")
            comp_g, comp_m, comp_c = st.columns(3)
            
            if cant_items > 0:
                fecha_hoy = date.today().strftime("%d/%m/%y")
                lista_impresion_directa = [
                    (row["SKU"], row["Descripcion"], row["Precio_Nuevo"], fecha_hoy) 
                    for _, row in df_tildados.iterrows()
                ]
                
                with comp_g:
                    st.write(f"**🔴 Carteles Gigantes ({cant_items})**")
                    pdf_comp_g = generar_carteles_gigantes(lista_impresion_directa)
                    st.download_button("⬇️ Descargar PDF", data=pdf_comp_g, file_name="cambios_gigantes.pdf", mime="application/pdf", use_container_width=True, key="dl_comp_g")
                    embeber_e_imprimir_pdf(pdf_comp_g, "print_comp_g")
                    
                with comp_m:
                    st.write(f"**🔵 Precios Medianos ({cant_items})**")
                    pdf_comp_m = generar_precios_medianos(lista_impresion_directa)
                    st.download_button("⬇️ Descargar PDF", data=pdf_comp_m, file_name="cambios_medianos.pdf", mime="application/pdf", use_container_width=True, key="dl_comp_m")
                    embeber_e_imprimir_pdf(pdf_comp_m, "print_comp_m")
                    
                with comp_c:
                    st.write(f"**🟢 Etiquetas Chicas ({cant_items})**")
                    pdf_comp_c = generar_etiquetas_chicas(lista_impresion_directa)
                    st.download_button("⬇️ Descargar PDF", data=pdf_comp_c, file_name="cambios_chicas.pdf", mime="application/pdf", use_container_width=True, key="dl_comp_c")
                    embeber_e_imprimir_pdf(pdf_comp_c, "print_comp_c")
            else:
                with comp_g: st.info("🔴 Seleccioná ítems")
                with comp_m: st.info("🔵 Seleccioná ítems")
                with comp_c: st.info("🟢 Seleccioná ítems")
