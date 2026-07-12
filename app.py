import base64
import csv
import io
from datetime import date

import pandas as pd
import requests
import streamlit as st
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

# ID unificado de tu Google Sheets público
ID_DRIVE = "1z1naxcQyryThMHj3H9K3xi27EDuugBPnFKrrwrJ8v1Y"
URL_DRIVE = f"https://docs.google.com/spreadsheets/d/{ID_DRIVE}/export?format=csv"


# =========================================================================
# FUNCIONES DE ARREGLO Y DECODIFICACIÓN
# =========================================================================
def fix_encoding(text: str) -> str:
    if text is None:
        return ""

    text = str(text)
    replacements = {
        "Ã\x91": "Ñ",
        "Ã±": "ñ",
        "Ã\x81": "Á",
        "Ã\x89": "É",
        "Ã\x8d": "Í",
        "Ã\x93": "Ó",
        "Ã\x9a": "Ú",
        "Ã¡": "á",
        "Ã©": "é",
        "Ã­": "í",
        "Ã³": "ó",
        "Ãº": "ú",
        "NÅ°": "N°",
        "NÂ°": "N°",
        "NÂ": "N°",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    try:
        return text.encode("latin1").decode("utf-8")
    except Exception:
        return text


def format_price_arg(price_str: str) -> str:
    if price_str is None or str(price_str).strip() == "":
        return ""

    s = str(price_str).replace("$", "").replace(" ", "").strip()

    # Formato argentino: 1.234,56
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    # Si tiene varios puntos, se interpretan como separadores de miles.
    elif s.count(".") > 1:
        s = s.replace(".", "")

    try:
        value = float(s)
    except (TypeError, ValueError):
        return f"${str(price_str).strip()}"

    us = f"{value:,.2f}"
    return f"${us.replace(',', 'X').replace('.', ',').replace('X', '.')}"


def wrap_text_to_width(text, font_name, font_size, max_width):
    words = str(text).split()
    if not words:
        return []

    lines = []
    current = words[0]
    for word in words[1:]:
        test = current + " " + word
        if pdfmetrics.stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def normalize_code(value: str) -> str:
    """Normaliza únicamente para comparar/buscar, sin alterar lo que se imprime."""
    if value is None:
        return ""
    return str(value).strip().replace(".", "").lstrip("0").lower()


def dataframe_matches_search(df: pd.DataFrame, query: str, columns: list[str]) -> pd.Series:
    if df.empty or not query.strip():
        return pd.Series(True, index=df.index)

    query_norm = fix_encoding(query).strip().lower()
    mask = pd.Series(False, index=df.index)
    for column in columns:
        if column in df.columns:
            mask |= df[column].fillna("").astype(str).str.lower().str.contains(
                query_norm, regex=False
            )
    return mask


def update_selection_from_editor(
    state_key: str,
    edited_df: pd.DataFrame,
    id_column: str,
    selection_column: str,
):
    """Actualiza solamente las filas visibles del editor, conservando las ocultas por búsqueda."""
    if state_key not in st.session_state or edited_df.empty:
        return

    current_df = st.session_state[state_key].copy()
    selections = edited_df.set_index(id_column)[selection_column].to_dict()
    current_df[selection_column] = current_df.apply(
        lambda row: selections.get(row[id_column], row[selection_column]), axis=1
    )
    st.session_state[state_key] = current_df


# =========================================================================
# FUNCIÓN INYECTORA DE IMPRESIÓN DIRECTA
# =========================================================================
def embeber_e_imprimir_pdf(bytes_pdf, key_boton):
    # key_boton se conserva para no modificar las llamadas existentes.
    _ = key_boton
    base64_pdf = base64.b64encode(bytes_pdf).decode("utf-8")
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
                setTimeout(function() {{ win.focus(); win.print(); }}, 300);
            }} else {{
                alert("❌ Habilitá las ventanas emergentes (pop-ups) en tu navegador.");
            }}
        }}
    </script>
    <button onclick="ejecutarImpresion()" style="
        width: 100%; height: 45px; background-color: #FF9800; color: white;
        border: none; font-size: 16px; font-weight: bold; border-radius: 8px;
        cursor: pointer; box-shadow: 0px 4px 6px rgba(0,0,0,0.1); margin-top: 5px;
    ">🖨️ Mandar a Imprimir Directo</button>
    """
    st.components.v1.html(componente_html, height=60)


# =========================================================================
# MOTORES DE GENERACIÓN DE PDF
# Se mantiene el formato original. El primer campo siempre es Código de barras.
# =========================================================================
def generar_carteles_gigantes(products_list):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    lbl_w, lbl_h = A4[0] - 10 * mm, (A4[1] - 15 * mm) / 2
    label_date = date.today().strftime("%d/%m/%Y")

    for i, (bar_code, name, price, date_str) in enumerate(products_list):
        pos = i % 2
        if i != 0 and pos == 0:
            c.showPage()

        x = 5 * mm
        y = A4[1] - 5 * mm - lbl_h if pos == 0 else 5 * mm
        c.rect(x, y, lbl_w, lbl_h)

        price_txt = format_price_arg(price).strip()
        f_size = 135
        while f_size > 20:
            if c.stringWidth(price_txt, "Helvetica-Bold", f_size) <= lbl_w - 20:
                break
            f_size -= 2
        c.setFont("Helvetica-Bold", f_size)
        c.drawString(
            x + (lbl_w - c.stringWidth(price_txt, "Helvetica-Bold", f_size)) / 2,
            y + lbl_h / 2 - f_size / 3,
            price_txt,
        )

        c.setFont("Helvetica-Bold", 26)
        desc_clean = fix_encoding(name).strip().upper()
        words = desc_clean.split()
        lines, current = [], ""
        for word in words:
            test = word if not current else current + " " + word
            if c.stringWidth(test, "Helvetica-Bold", 26) <= lbl_w - 40:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) == 1:
                    break
        if current and len(lines) < 2:
            lines.append(current)

        current_y = y + lbl_h - 45
        for line in lines:
            c.drawCentredString(x + lbl_w / 2, current_y, line)
            current_y -= 31

        c.setFont("Helvetica-Bold", 12)
        footer_date = date_str if str(date_str).strip() else label_date
        c.drawCentredString(
            x + lbl_w / 2,
            y + 16,
            f"{str(bar_code).strip()}  {str(footer_date).strip()}",
        )

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def generar_precios_medianos(data_rows):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    lbl_w, lbl_h = 100 * mm, 70 * mm
    margin_x = (page_width - 2 * lbl_w) / 2.0
    margin_y = (page_height - 4 * lbl_h) / 2.0
    col, row = 0, 0
    label_date = date.today().strftime("%d/%m/%y")

    for bar_code, name, price, date_str in data_rows:
        x = margin_x + col * lbl_w
        y = page_height - margin_y - (row + 1) * lbl_h
        c.rect(x, y, lbl_w, lbl_h)
        inner_w = lbl_w - 6 * mm

        desc_text = fix_encoding(name).strip().upper()
        if desc_text:
            f_size = 20
            lines = []
            while f_size >= 7:
                lines = wrap_text_to_width(
                    desc_text, "Helvetica-Bold", f_size, inner_w
                )
                if len(lines) * f_size * 1.15 <= lbl_h * 0.38:
                    break
                f_size -= 1

            c.setFont("Helvetica-Bold", f_size)
            current_y = y + lbl_h - 4 * mm - f_size
            for line in lines:
                c.drawString(
                    x
                    + 3 * mm
                    + (
                        inner_w
                        - pdfmetrics.stringWidth(line, "Helvetica-Bold", f_size)
                    )
                    / 2.0,
                    current_y,
                    line,
                )
                current_y -= f_size * 1.15

        price_text = format_price_arg(price).strip()
        if price_text:
            f_size = 105
            while f_size > 14:
                if (
                    pdfmetrics.stringWidth(price_text, "Helvetica-Bold", f_size)
                    <= inner_w
                ):
                    break
                f_size -= 1
            c.setFont("Helvetica-Bold", f_size)
            c.drawString(
                x
                + 3 * mm
                + (
                    inner_w
                    - pdfmetrics.stringWidth(price_text, "Helvetica-Bold", f_size)
                )
                / 2.0,
                y + 16.5 * mm,
                price_text,
            )

        footer_date = date_str if str(date_str).strip() else label_date
        footer = f"{str(bar_code).strip()}   {str(footer_date).strip()}"
        c.setFont("Helvetica", 10)
        c.drawString(
            x
            + 3 * mm
            + (inner_w - pdfmetrics.stringWidth(footer, "Helvetica", 10)) / 2.0,
            y + 4 * mm,
            footer,
        )

        col += 1
        if col >= 2:
            col, row = 0, row + 1
        if row >= 4:
            c.showPage()
            row, col = 0, 0

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def generar_etiquetas_chicas(products_list):
    buffer = io.BytesIO()
    w_page, h_page = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=(w_page, h_page))
    label_date = date.today().strftime("%d/%m/%y")
    lbl_w, lbl_h = 70 * mm, 35 * mm
    cols = int((w_page - 10 * mm + 2 * mm) // (lbl_w + 2 * mm))
    rows = int((h_page - 10 * mm + 2 * mm) // (lbl_h + 2 * mm))
    per_page = cols * rows

    for i, (bar_code, name, price, date_str) in enumerate(products_list):
        # Corrección del error de sintaxis original.
        if i > 0 and i % per_page == 0:
            c.showPage()

        pos = i % per_page
        row, col = pos // cols, pos % cols
        x = 5 * mm + col * (lbl_w + 2 * mm)
        y = h_page - 5 * mm - ((row + 1) * (lbl_h + 2 * mm)) + 2 * mm
        c.rect(x, y, lbl_w, lbl_h)

        price_txt = format_price_arg(price).strip()
        f_size_p = 44
        while f_size_p > 12:
            if c.stringWidth(price_txt, "Helvetica-Bold", f_size_p) <= lbl_w - 4 * mm:
                break
            f_size_p -= 1
        c.setFont("Helvetica-Bold", f_size_p)
        c.drawString(
            x
            + (lbl_w - c.stringWidth(price_txt, "Helvetica-Bold", f_size_p)) / 2,
            y + lbl_h * 0.25,
            price_txt,
        )

        c.setFont("Helvetica-Bold", 10)
        desc_clean = fix_encoding(name).strip().upper()
        words = desc_clean.split()
        lines, current = [], ""
        for word in words:
            test = word if not current else current + " " + word
            if c.stringWidth(test, "Helvetica-Bold", 10) <= lbl_w - 4 * mm:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) == 4:
                    break
        if current and len(lines) < 4:
            lines.append(current)

        current_y = y + lbl_h - 5 * mm
        for line in lines:
            if current_y < y + lbl_h * 0.25 + 14:
                break
            c.drawCentredString(x + lbl_w / 2, current_y, line)
            current_y -= 11.5

        c.setFont("Helvetica", 8)
        footer_date = date_str if str(date_str).strip() else label_date
        c.drawCentredString(
            x + lbl_w / 2,
            y + 2 * mm,
            f"{str(bar_code).strip()} - {str(footer_date).strip()}",
        )

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def generar_pdf_por_tamanio(tamanio: str, products_list):
    if tamanio == "Gigante":
        return generar_carteles_gigantes(products_list), "carteles_gigantes.pdf"
    if tamanio == "Mediana":
        return generar_precios_medianos(products_list), "precios_medianos.pdf"
    return generar_etiquetas_chicas(products_list), "etiquetas_chicas.pdf"


# =========================================================================
# CARGA DE DATOS
# =========================================================================
@st.cache_data(ttl="2m")
def descargar_base_estatica(url):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        content = response.content.decode("utf-8-sig", errors="replace")
        lines = content.splitlines()
        if not lines:
            return pd.DataFrame()

        separator = ";" if lines[0].count(";") > lines[0].count(",") else ","
        reader = csv.reader(lines, delimiter=separator)
        header = next(reader, None)
        if header is None:
            return pd.DataFrame()

        header_norm = [fix_encoding(value).strip().lower() for value in header]

        def find_column(candidates, fallback=None):
            for candidate in candidates:
                for index, value in enumerate(header_norm):
                    if candidate in value:
                        return index
            return fallback

        # Se prioriza explícitamente Código de barras. Los fallbacks conservan
        # compatibilidad con la estructura actual de la hoja.
        barcode_index = find_column(
            ["código de barras", "codigo de barras", "codigobarra", "barcode", "ean"],
            0,
        )
        description_index = find_column(
            ["descripción", "descripcion", "nombre", "producto"], 1
        )
        price_index = find_column(
            ["precio venta final", "precio_venta_final", "precio", "importe"], 2
        )
        article_id_index = find_column(
            ["idarticulo", "id articulo", "id_articulo", "código interno", "codigo interno"],
            3,
        )

        products = []
        for row in reader:
            if not row:
                continue

            max_required = max(
                barcode_index or 0,
                description_index or 0,
                price_index or 0,
                article_id_index or 0,
            )
            row = list(row) + [""] * (max_required + 1 - len(row))

            barcode = row[barcode_index].strip() if barcode_index is not None else ""
            description = (
                fix_encoding(row[description_index].strip())
                if description_index is not None
                else ""
            )
            price = row[price_index].strip() if price_index is not None else ""
            article_id = (
                row[article_id_index].strip() if article_id_index is not None else ""
            )

            if not barcode and not article_id:
                continue

            products.append(
                {
                    "Código de barras": barcode,
                    "Código_Norm": normalize_code(barcode),
                    "Id_Articulo": article_id,
                    "Id_Norm": normalize_code(article_id),
                    "Descripción": description,
                    "Precio Crudo": price,
                    "Fecha": date.today().strftime("%d/%m/%y"),
                }
            )

        return pd.DataFrame(products)
    except Exception:
        return pd.DataFrame()


def parse_csv_labels(uploaded_file) -> pd.DataFrame:
    """Lee el CSV de etiquetas manteniendo su estructura y usando Código de barras."""
    bytes_data = uploaded_file.getvalue()

    content = None
    for encoding in ("utf-8-sig", "latin1"):
        try:
            content = bytes_data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        raise ValueError("No se pudo decodificar el archivo CSV.")

    first_line = content.splitlines()[0] if content.splitlines() else ""
    separator = ";" if first_line.count(";") > first_line.count(",") else ","
    rows = list(csv.reader(content.splitlines(), delimiter=separator))
    if not rows:
        return pd.DataFrame()

    header_norm = [fix_encoding(value).strip().lower() for value in rows[0]]
    has_header = any(
        keyword in " ".join(header_norm)
        for keyword in ("precio", "descripción", "descripcion", "código", "codigo", "sku")
    )

    def find_header_index(candidates):
        for candidate in candidates:
            for index, value in enumerate(header_norm):
                if candidate in value:
                    return index
        return None

    if has_header:
        price_index = find_header_index(["precio", "importe"])
        description_index = find_header_index(["descripción", "descripcion", "producto", "nombre"])
        barcode_index = find_header_index(
            ["código de barras", "codigo de barras", "codigobarra", "barcode", "ean"]
        )
        date_index = find_header_index(["fecha"])
        data_rows = rows[1:]

        if barcode_index is None:
            raise ValueError(
                "El CSV no tiene una columna identificable como Código de barras."
            )
    else:
        # Estructura ya utilizada por la aplicación:
        # Precio, Descripción, SKU, Código de barras, Fecha.
        price_index = 0
        description_index = 1
        barcode_index = 3
        date_index = 4
        data_rows = rows

    parsed_products = []
    for row_number, row in enumerate(data_rows):
        if not row:
            continue

        required_indexes = [
            index
            for index in (price_index, description_index, barcode_index, date_index)
            if index is not None
        ]
        max_index = max(required_indexes, default=0)
        row_extended = list(row) + [""] * (max_index + 1 - len(row))

        barcode = (
            row_extended[barcode_index].strip() if barcode_index is not None else ""
        )
        description = (
            fix_encoding(row_extended[description_index].strip().strip('"'))
            if description_index is not None
            else ""
        )
        price = row_extended[price_index].strip() if price_index is not None else ""
        label_date = (
            row_extended[date_index].strip() if date_index is not None else ""
        )

        # Saltea encabezados repetidos o filas totalmente vacías.
        if not barcode and not description and not price:
            continue
        if barcode.lower() in {"código de barras", "codigo de barras", "barcode"}:
            continue

        parsed_products.append(
            {
                "_id": row_number,
                "Imprimir": True,
                "Código de barras": barcode if barcode else "S/C",
                "Descripción": description,
                "Precio Crudo": price,
                "Fecha": label_date,
            }
        )

    return pd.DataFrame(parsed_products)


def normalizar_precio(valor):
    if pd.isna(valor):
        return None

    s = str(valor).replace("$", "").replace(" ", "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")

    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def cargar_df_comparador(uploaded_file):
    uploaded_file.seek(0)
    try:
        df = pd.read_csv(uploaded_file, sep=",", header=None, engine="python", dtype=str)
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        df = pd.read_csv(
            uploaded_file,
            sep=",",
            header=None,
            engine="python",
            dtype=str,
            encoding="latin1",
        )

    if df.shape[1] < 15:
        raise IndexError("Estructura inválida: se esperaban al menos 15 columnas.")

    result = pd.DataFrame(
        {
            "Codigo_Barra": df[0],
            "Descripcion": df[10],
            "Precio": df[14],
        }
    )
    result = result[result["Codigo_Barra"].notna()].copy()
    result["Codigo_Barra"] = result["Codigo_Barra"].astype(str).str.strip()
    result = result[
        (result["Codigo_Barra"] != "")
        & (result["Codigo_Barra"] != "0")
        & (result["Codigo_Barra"].str.upper() != "S/C")
        & (result["Codigo_Barra"].str.lower() != "codigo_barra")
    ].copy()
    result["Descripcion"] = result["Descripcion"].fillna("").apply(fix_encoding)
    result["Precio_num"] = result["Precio"].apply(normalizar_precio)
    result = result.dropna(subset=["Precio_num"])
    result = result.drop_duplicates(subset=["Codigo_Barra"], keep="last")
    return result


def detectar_lista_vieja_y_nueva(df_a, df_b):
    """Detecta el orden por la mayoría de aumentos, no por un promedio global aislado."""
    paired = pd.merge(
        df_a[["Codigo_Barra", "Precio_num"]].rename(
            columns={"Precio_num": "Precio_a"}
        ),
        df_b[["Codigo_Barra", "Precio_num"]].rename(
            columns={"Precio_num": "Precio_b"}
        ),
        on="Codigo_Barra",
        how="inner",
    )

    if paired.empty:
        raise ValueError("Las listas no tienen códigos de barras coincidentes.")

    increases_b = int((paired["Precio_b"] > paired["Precio_a"]).sum())
    increases_a = int((paired["Precio_a"] > paired["Precio_b"]).sum())

    if increases_b > increases_a:
        return df_a, df_b
    if increases_a > increases_b:
        return df_b, df_a

    # Desempate compatible con la lógica anterior.
    median_a = paired["Precio_a"].median()
    median_b = paired["Precio_b"].median()
    return (df_a, df_b) if median_b >= median_a else (df_b, df_a)


# =========================================================================
# INTERFAZ DE STREAMLIT (PANTALLA ANCHA COMPLETA)
# =========================================================================
st.set_page_config(page_title="Cotyland Nube", page_icon="🎈", layout="wide")

st.components.v1.html(
    """
<script>
    function frenarPantallaCompleta(e) {
        if (e.key === 'F11' || e.keyCode === 122) {
            e.preventDefault();
            e.stopPropagation();
            setTimeout(function() {
                var box = window.parent.document.querySelector('input[type="text"]');
                if (box) {
                    box.focus();
                    box.dispatchEvent(new Event('change', { bubbles: true }));
                    var evEnter = new KeyboardEvent('keydown', { bubbles: true, key: 'Enter', keyCode: 13 });
                    box.dispatchEvent(evEnter);
                }
            }, 10);
        }
    }
    window.parent.document.addEventListener('keydown', frenarPantallaCompleta, true);
</script>
""",
    height=0,
)

st.html(
    """
<style>
    button[data-testid="stMarkdownContainer"] p { font-size: 16px !important; font-weight: bold !important; }
    div[data-testid="stColumn"] button { height: 50px !important; font-size: 16px !important; font-weight: bold !important; border-radius: 10px !important; }
    div[data-testid="stDataFrame"] iframe { width: 100% !important; }
</style>
"""
)

st.title("🎈 Cotyland - Panel Multiplataforma")
tab0, tab1, tab2 = st.tabs(
    ["📱 Buscador Móvil", "🖨️ Generador de Etiquetas (CSV)", "📊 Comparador de Precios"]
)

# Estados del escáner.
if "cola_impresion" not in st.session_state:
    st.session_state.cola_impresion = []
if "ultimo_producto" not in st.session_state:
    st.session_state.ultimo_producto = ""
if "duplicado_pendiente" not in st.session_state:
    st.session_state.duplicado_pendiente = None
if "scanner_pdf" not in st.session_state:
    st.session_state.scanner_pdf = None
if "scanner_pdf_name" not in st.session_state:
    st.session_state.scanner_pdf_name = ""


# =========================================================================
# PESTAÑA 1: ESCÁNER
# =========================================================================
with tab0:
    df_drive = descargar_base_estatica(URL_DRIVE)

    if df_drive.empty:
        st.error("⚠️ Error cargando base de datos estática.")
    else:
        st.caption(
            f"🟢 Motor de Alta Velocidad Activo: {len(df_drive)} artículos en caché RAM."
        )

    def agregar_producto_a_cola(product):
        st.session_state.cola_impresion.append(
            {
                "Imprimir": True,
                "Código de barras": str(product["Código de barras"]).strip(),
                "Descripción": product["Descripción"],
                "Precio": product["Precio Crudo"],
                "Fecha": product["Fecha"],
            }
        )
        st.session_state.ultimo_producto = (
            "✔ Agregado\n\n"
            f"**{product['Descripción']}**\n\n"
            f"{format_price_arg(product['Precio Crudo'])}  |  "
            f"Código: {str(product['Código de barras']).strip()}"
        )
        st.session_state.scanner_pdf = None
        st.session_state.scanner_pdf_name = ""

    def procesar_colector_veloz():
        raw_query = st.session_state.get("colector_input", "").strip()
        st.session_state.colector_input = ""

        if not raw_query or df_drive.empty:
            return

        query_norm = normalize_code(raw_query.replace("F11", ""))
        if not query_norm:
            return

        condition = (df_drive["Código_Norm"] == query_norm) | (
            df_drive["Id_Norm"] == query_norm
        )
        results = df_drive[condition]

        if results.empty:
            st.session_state.ultimo_producto = (
                f"❌ Código no encontrado: '{raw_query}'"
            )
            return

        product = results.iloc[0].to_dict()
        barcode_norm = normalize_code(product["Código de barras"])
        already_exists = any(
            normalize_code(item["Código de barras"]) == barcode_norm
            for item in st.session_state.cola_impresion
        )

        if already_exists:
            st.session_state.duplicado_pendiente = product
            st.session_state.ultimo_producto = ""
        else:
            agregar_producto_a_cola(product)

    st.text_input(
        "🔎 ESCANEÁ ACÁ (MODO CORRELATIVO CONSTANTE):",
        key="colector_input",
        on_change=procesar_colector_veloz,
        placeholder="Hacé foco acá y pasá los códigos de corrido...",
        disabled=st.session_state.duplicado_pendiente is not None,
    )

    if st.session_state.duplicado_pendiente is not None:
        duplicate = st.session_state.duplicado_pendiente
        st.warning(
            "Este producto ya fue agregado.\n\n"
            f"**{duplicate['Descripción']}**  |  "
            f"{format_price_arg(duplicate['Precio Crudo'])}  |  "
            f"Código: {duplicate['Código de barras']}"
        )
        duplicate_add_col, duplicate_ignore_col = st.columns(2)
        with duplicate_add_col:
            if st.button(
                "➕ Agregar otra etiqueta",
                type="primary",
                use_container_width=True,
                key="duplicate_add",
            ):
                agregar_producto_a_cola(duplicate)
                st.session_state.duplicado_pendiente = None
                st.rerun()
        with duplicate_ignore_col:
            if st.button(
                "Ignorar",
                use_container_width=True,
                key="duplicate_ignore",
            ):
                st.session_state.duplicado_pendiente = None
                st.session_state.ultimo_producto = "Producto duplicado ignorado."
                st.rerun()

    if st.session_state.ultimo_producto:
        if st.session_state.ultimo_producto.startswith("✔"):
            st.success(st.session_state.ultimo_producto)
        elif st.session_state.ultimo_producto.startswith("❌"):
            st.error(st.session_state.ultimo_producto)
        else:
            st.info(st.session_state.ultimo_producto)

    if st.session_state.cola_impresion:
        st.write("---")
        st.subheader("📋 Lista Correlativa de Impresión Actual")

        scanner_search = st.text_input(
            "Buscar producto",
            key="scanner_search",
            placeholder="Filtrá por código o descripción...",
        )

        scanner_df = pd.DataFrame(st.session_state.cola_impresion)
        scanner_df.insert(0, "_id", range(len(scanner_df)))

        action_select_all, action_deselect_all, action_clear = st.columns(3)
        with action_select_all:
            if st.button(
                "Seleccionar todos", use_container_width=True, key="scanner_select_all"
            ):
                for item in st.session_state.cola_impresion:
                    item["Imprimir"] = True
                st.session_state.scanner_pdf = None
                st.rerun()
        with action_deselect_all:
            if st.button(
                "Deseleccionar todos",
                use_container_width=True,
                key="scanner_deselect_all",
            ):
                for item in st.session_state.cola_impresion:
                    item["Imprimir"] = False
                st.session_state.scanner_pdf = None
                st.rerun()
        with action_clear:
            if st.button(
                "Vaciar lista", use_container_width=True, key="scanner_clear"
            ):
                st.session_state.cola_impresion = []
                st.session_state.scanner_pdf = None
                st.session_state.scanner_pdf_name = ""
                st.session_state.ultimo_producto = ""
                st.rerun()

        visible_scanner_df = scanner_df[
            dataframe_matches_search(
                scanner_df,
                scanner_search,
                ["Código de barras", "Descripción", "Precio", "Fecha"],
            )
        ].copy()

        edited_scanner = st.data_editor(
            visible_scanner_df,
            column_config={
                "Imprimir": st.column_config.CheckboxColumn(default=True),
                "_id": None,
            },
            disabled=["Código de barras", "Descripción", "Precio", "Fecha"],
            hide_index=True,
            use_container_width=True,
            key="tabla_viva_scanner",
        )

        if not edited_scanner.empty:
            selection_map = edited_scanner.set_index("_id")["Imprimir"].to_dict()
            for index, item in enumerate(st.session_state.cola_impresion):
                if index in selection_map:
                    item["Imprimir"] = bool(selection_map[index])

        selected_scanner = [
            item for item in st.session_state.cola_impresion if item["Imprimir"]
        ]

        st.markdown("### Elegir tamaño:")
        scanner_size = st.radio(
            "Tamaño de las etiquetas",
            ["Chica", "Mediana", "Gigante"],
            horizontal=True,
            key="scanner_size",
            label_visibility="collapsed",
        )

        if st.button(
            f"Generar PDF ({len(selected_scanner)} seleccionados)",
            type="primary",
            use_container_width=True,
            disabled=not selected_scanner,
            key="scanner_generate_pdf",
        ):
            scanner_print_list = [
                (
                    item["Código de barras"],
                    item["Descripción"],
                    item["Precio"],
                    item["Fecha"],
                )
                for item in selected_scanner
            ]
            pdf_bytes, pdf_name = generar_pdf_por_tamanio(
                scanner_size, scanner_print_list
            )
            st.session_state.scanner_pdf = pdf_bytes
            st.session_state.scanner_pdf_name = pdf_name

        if st.session_state.scanner_pdf:
            st.download_button(
                "⬇️ Descargar PDF",
                data=st.session_state.scanner_pdf,
                file_name=st.session_state.scanner_pdf_name,
                use_container_width=True,
                key="scanner_download_pdf",
            )
            embeber_e_imprimir_pdf(
                st.session_state.scanner_pdf, "scanner_print_pdf"
            )


# =========================================================================
# PESTAÑA 2: GENERADOR DESDE CSV
# =========================================================================
with tab1:
    st.subheader("1. Arrastrá tu archivo de precios")
    uploaded_file = st.file_uploader(
        "Subir CSV de Precios", type=["csv"], key="unificado_etiquetas"
    )

    if uploaded_file:
        try:
            upload_signature = (
                uploaded_file.name,
                uploaded_file.size,
                hash(uploaded_file.getvalue()),
            )
            if st.session_state.get("csv_upload_signature") != upload_signature:
                st.session_state.csv_products = parse_csv_labels(uploaded_file)
                st.session_state.csv_upload_signature = upload_signature

            df_products = st.session_state.csv_products.copy()
            st.success(f"✅ ¡Archivo leído! {len(df_products)} productos detectados.")

            csv_search = st.text_input(
                "Buscar producto",
                key="csv_search",
                placeholder="Filtrá por código o descripción...",
            )

            csv_select_col, csv_deselect_col = st.columns(2)
            with csv_select_col:
                if st.button(
                    "Seleccionar todos", use_container_width=True, key="csv_select_all"
                ):
                    st.session_state.csv_products["Imprimir"] = True
                    st.rerun()
            with csv_deselect_col:
                if st.button(
                    "Deseleccionar todos",
                    use_container_width=True,
                    key="csv_deselect_all",
                ):
                    st.session_state.csv_products["Imprimir"] = False
                    st.rerun()

            visible_products = df_products[
                dataframe_matches_search(
                    df_products,
                    csv_search,
                    ["Código de barras", "Descripción", "Precio Crudo", "Fecha"],
                )
            ].copy()

            edited_df = st.data_editor(
                visible_products,
                column_config={
                    "Imprimir": st.column_config.CheckboxColumn(default=True),
                    "_id": None,
                },
                disabled=["Código de barras", "Descripción", "Precio Crudo", "Fecha"],
                hide_index=True,
                use_container_width=True,
                key="csv_products_editor",
            )
            update_selection_from_editor(
                "csv_products", edited_df, "_id", "Imprimir"
            )

            selected_csv = st.session_state.csv_products[
                st.session_state.csv_products["Imprimir"] == True
            ]
            final_list = [
                (
                    row["Código de barras"],
                    row["Descripción"],
                    row["Precio Crudo"],
                    row["Fecha"],
                )
                for _, row in selected_csv.iterrows()
            ]

            if final_list:
                col1, col2, col3 = st.columns(3)
                with col1:
                    pdf_csv_g = generar_carteles_gigantes(final_list)
                    st.download_button(
                        "📥 Bajar Gigantes",
                        data=pdf_csv_g,
                        file_name="carteles_gigantes_a4.pdf",
                        use_container_width=True,
                        key="c_g",
                    )
                    embeber_e_imprimir_pdf(pdf_csv_g, "csv_p_g")
                with col2:
                    pdf_csv_m = generar_precios_medianos(final_list)
                    st.download_button(
                        "📥 Bajar Medianos",
                        data=pdf_csv_m,
                        file_name="precios_medianos_10x7.pdf",
                        use_container_width=True,
                        key="c_m",
                    )
                    embeber_e_imprimir_pdf(pdf_csv_m, "csv_p_m")
                with col3:
                    pdf_csv_c = generar_etiquetas_chicas(final_list)
                    st.download_button(
                        "📥 Bajar Chicas",
                        data=pdf_csv_c,
                        file_name="etiquetas_chicas_7x35.pdf",
                        use_container_width=True,
                        key="c_c",
                    )
                    embeber_e_imprimir_pdf(pdf_csv_c, "csv_p_c")
            else:
                st.info("Seleccioná al menos un producto para generar las etiquetas.")
        except Exception as exc:
            st.error(f"❌ Error: {exc}")


# =========================================================================
# PESTAÑA 3: COMPARADOR DE PRECIOS
# =========================================================================
with tab2:
    st.subheader("📊 Comparar Cambios de Precios")
    file_a = st.file_uploader(
        "Subir Archivo de Lista (A)", type=["csv"], key="file_a_up"
    )
    file_b = st.file_uploader(
        "Subir Archivo de Lista (B)", type=["csv"], key="file_b_up"
    )

    if file_a and file_b:
        if st.button(
            "Cruzar Listas y Detectar Cambios",
            type="primary",
            use_container_width=True,
        ):
            try:
                df_a = cargar_df_comparador(file_a)
                df_b = cargar_df_comparador(file_b)
                df_old, df_new = detectar_lista_vieja_y_nueva(df_a, df_b)

                merged = pd.merge(
                    df_old[["Codigo_Barra", "Precio_num"]].rename(
                        columns={"Precio_num": "Precio_old"}
                    ),
                    df_new[
                        ["Codigo_Barra", "Precio_num", "Descripcion", "Precio"]
                    ],
                    on="Codigo_Barra",
                    how="inner",
                )

                changed = merged[
                    merged["Precio_old"].round(4)
                    != merged["Precio_num"].round(4)
                ].copy()

                final_df = changed[
                    ["Codigo_Barra", "Descripcion", "Precio_old", "Precio"]
                ].rename(
                    columns={
                        "Codigo_Barra": "Código Barra",
                        "Precio": "Precio_Nuevo",
                        "Precio_old": "Precio_Anterior",
                    }
                )

                final_df["Desc_Upper"] = (
                    final_df["Descripcion"].fillna("").str.upper()
                )
                final_df = final_df.sort_values("Desc_Upper").drop(
                    columns=["Desc_Upper"]
                )
                final_df = final_df.reset_index(drop=True)
                final_df.insert(0, "_id", range(len(final_df)))
                final_df.insert(1, "🖨️ Seleccionar", False)

                st.session_state.df_comparativa = final_df
                st.success(
                    f"¡Se encontraron {len(final_df)} productos con cambios!"
                )
            except Exception as exc:
                st.error(f"❌ Error: {exc}")

        if "df_comparativa" in st.session_state:
            comparative_df = st.session_state.df_comparativa
            if comparative_df.empty:
                st.info("No se detectaron cambios de precio entre las listas.")
            else:
                st.markdown("### 📋 Listado de Cambios Detectados")

                comp_search = st.text_input(
                    "Buscar producto",
                    key="comp_search",
                    placeholder="Filtrá por código o descripción...",
                )

                comp_select_col, comp_deselect_col = st.columns(2)
                with comp_select_col:
                    if st.button(
                        "Seleccionar todos",
                        use_container_width=True,
                        key="comp_select_all",
                    ):
                        st.session_state.df_comparativa["🖨️ Seleccionar"] = True
                        st.rerun()
                with comp_deselect_col:
                    if st.button(
                        "Deseleccionar todos",
                        use_container_width=True,
                        key="comp_deselect_all",
                    ):
                        st.session_state.df_comparativa["🖨️ Seleccionar"] = False
                        st.rerun()

                visible_comp = comparative_df[
                    dataframe_matches_search(
                        comparative_df,
                        comp_search,
                        ["Código Barra", "Descripcion", "Precio_Anterior", "Precio_Nuevo"],
                    )
                ].copy()

                edited_comp = st.data_editor(
                    visible_comp,
                    column_config={
                        "🖨️ Seleccionar": st.column_config.CheckboxColumn(
                            default=False
                        ),
                        "_id": None,
                    },
                    disabled=[
                        "Código Barra",
                        "Descripcion",
                        "Precio_Anterior",
                        "Precio_Nuevo",
                    ],
                    hide_index=True,
                    use_container_width=True,
                    key="tabla_edicion_comparativa",
                )
                update_selection_from_editor(
                    "df_comparativa",
                    edited_comp,
                    "_id",
                    "🖨️ Seleccionar",
                )

                selected_comp = st.session_state.df_comparativa[
                    st.session_state.df_comparativa["🖨️ Seleccionar"] == True
                ]
                selected_count = len(selected_comp)

                st.markdown("### 📥 Impresión Rápida de Cambios Cruzados:")
                comp_g, comp_m, comp_c = st.columns(3)

                if selected_count > 0:
                    today = date.today().strftime("%d/%m/%y")
                    direct_print_list = [
                        (
                            str(row["Código Barra"]),
                            row["Descripcion"],
                            row["Precio_Nuevo"],
                            today,
                        )
                        for _, row in selected_comp.iterrows()
                    ]

                    with comp_g:
                        st.write(f"**🔴 Carteles Gigantes ({selected_count})**")
                        pdf_comp_g = generar_carteles_gigantes(direct_print_list)
                        st.download_button(
                            "⬇️ Descargar PDF",
                            data=pdf_comp_g,
                            file_name="cambios_gigantes.pdf",
                            use_container_width=True,
                            key="dl_comp_g",
                        )
                        embeber_e_imprimir_pdf(pdf_comp_g, "print_comp_g")
                    with comp_m:
                        st.write(f"**🔵 Precios Medianos ({selected_count})**")
                        pdf_comp_m = generar_precios_medianos(direct_print_list)
                        st.download_button(
                            "⬇️ Descargar PDF",
                            data=pdf_comp_m,
                            file_name="cambios_medianos.pdf",
                            use_container_width=True,
                            key="dl_comp_m",
                        )
                        embeber_e_imprimir_pdf(pdf_comp_m, "print_comp_m")
                    with comp_c:
                        st.write(f"**🟢 Etiquetas Chicas ({selected_count})**")
                        pdf_comp_c = generar_etiquetas_chicas(direct_print_list)
                        st.download_button(
                            "⬇️ Descargar PDF",
                            data=pdf_comp_c,
                            file_name="cambios_chicas.pdf",
                            use_container_width=True,
                            key="dl_comp_c",
                        )
                        embeber_e_imprimir_pdf(pdf_comp_c, "print_comp_c")
                else:
                    with comp_g:
                        st.info("🔴 Tildá los ítems a imprimir")
                    with comp_m:
                        st.info("🔵 Tildá los ítems a imprimir")
                    with comp_c:
                        st.info("🟢 Tildá los ítems a imprimir")
