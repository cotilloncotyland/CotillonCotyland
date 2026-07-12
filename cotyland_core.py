"""Lógica estable y testeable de la aplicación Cotyland."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date
from pathlib import Path
from typing import BinaryIO, Iterable

import pandas as pd
import requests
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

COMPARATOR_COLUMNS = [9, 10, 11, 14]


def fix_encoding(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if "Ã" in text or "Â" in text:
        try:
            return text.encode("latin1").decode("utf-8")
        except (UnicodeError, UnicodeEncodeError):
            pass
    return text


def clean_code(value: object) -> str:
    """Conserva el código; solo elimina espacio exterior y teclas del lector."""
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"^(?:(?:F2|F11)\s*)+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:\s*(?:F2|F11))+$", "", text, flags=re.IGNORECASE)
    return text.strip()


def normalize_code(value: object) -> str:
    return clean_code(value).casefold()


def format_price_arg(value: object) -> str:
    if value is None or str(value).strip() == "":
        return ""
    number = parse_price(value)
    if number is None:
        return f"${str(value).strip()}"
    formatted = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${formatted}"


def parse_price(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).replace("$", "").replace(" ", "").strip()
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def price_series(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.replace("$", "", regex=False).str.replace(" ", "", regex=False)
    has_comma = text.str.contains(",", regex=False)
    normalized = text.copy()
    normalized.loc[has_comma] = normalized.loc[has_comma].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    multiple_dots = ~has_comma & normalized.str.count(r"\.").gt(1)
    normalized.loc[multiple_dots] = normalized.loc[multiple_dots].str.replace(".", "", regex=False)
    return pd.to_numeric(normalized, errors="coerce")


def wrap_text_to_width(text: str, font_name: str, font_size: int, max_width: float) -> list[str]:
    words = str(text).split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _footer_code(barcode: object, article_id: object = "") -> str:
    return clean_code(barcode) or clean_code(article_id)


def generar_carteles_gigantes(products: Iterable[tuple]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    label_w, label_h = A4[0] - 10 * mm, (A4[1] - 15 * mm) / 2
    today = date.today().strftime("%d/%m/%Y")
    for index, row in enumerate(products):
        barcode, name, price, date_text, *rest = row
        article_id = rest[0] if rest else ""
        position = index % 2
        if index and position == 0:
            pdf.showPage()
        x = 5 * mm
        y = A4[1] - 5 * mm - label_h if position == 0 else 5 * mm
        pdf.rect(x, y, label_w, label_h)
        price_text = format_price_arg(price)
        size = 135
        while size > 20 and pdfmetrics.stringWidth(price_text, "Helvetica-Bold", size) > label_w - 20:
            size -= 2
        pdf.setFont("Helvetica-Bold", size)
        pdf.drawCentredString(x + label_w / 2, y + label_h / 2 - size / 3, price_text)
        description = fix_encoding(name).strip().upper()
        lines = wrap_text_to_width(description, "Helvetica-Bold", 26, label_w - 40)[:2]
        pdf.setFont("Helvetica-Bold", 26)
        cursor_y = y + label_h - 45
        for line in lines:
            pdf.drawCentredString(x + label_w / 2, cursor_y, line)
            cursor_y -= 31
        footer_date = str(date_text).strip() or today
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawCentredString(x + label_w / 2, y + 16, f"{_footer_code(barcode, article_id)}  {footer_date}")
    pdf.save()
    return buffer.getvalue()


def generar_precios_medianos(products: Iterable[tuple]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    page_w, page_h = A4
    label_w, label_h = 100 * mm, 70 * mm
    margin_x, margin_y = (page_w - 2 * label_w) / 2, (page_h - 4 * label_h) / 2
    today = date.today().strftime("%d/%m/%y")
    column = row_number = 0
    for row in products:
        barcode, name, price, date_text, *rest = row
        article_id = rest[0] if rest else ""
        x, y = margin_x + column * label_w, page_h - margin_y - (row_number + 1) * label_h
        pdf.rect(x, y, label_w, label_h)
        inner_w = label_w - 6 * mm
        description = fix_encoding(name).strip().upper()
        size = 20
        lines = wrap_text_to_width(description, "Helvetica-Bold", size, inner_w)
        while size >= 8 and len(lines) * size * 1.15 > label_h * 0.38:
            size -= 1
            lines = wrap_text_to_width(description, "Helvetica-Bold", size, inner_w)
        pdf.setFont("Helvetica-Bold", size)
        cursor_y = y + label_h - 4 * mm - size
        for line in lines:
            pdf.drawCentredString(x + label_w / 2, cursor_y, line)
            cursor_y -= size * 1.15
        price_text = format_price_arg(price)
        size = 105
        while size > 14 and pdfmetrics.stringWidth(price_text, "Helvetica-Bold", size) > inner_w:
            size -= 1
        pdf.setFont("Helvetica-Bold", size)
        pdf.drawCentredString(x + label_w / 2, y + 16.5 * mm, price_text)
        footer = f"{_footer_code(barcode, article_id)}   {str(date_text).strip() or today}"
        pdf.setFont("Helvetica", 10)
        pdf.drawCentredString(x + label_w / 2, y + 4 * mm, footer)
        column += 1
        if column == 2:
            column, row_number = 0, row_number + 1
        if row_number == 4:
            pdf.showPage()
            column = row_number = 0
    pdf.save()
    return buffer.getvalue()


def generar_etiquetas_chicas(products: Iterable[tuple]) -> bytes:
    buffer = io.BytesIO()
    page_w, page_h = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=(page_w, page_h), pageCompression=1)
    today = date.today().strftime("%d/%m/%y")
    label_w, label_h = 70 * mm, 35 * mm
    columns = int((page_w - 10 * mm + 2 * mm) // (label_w + 2 * mm))
    rows = int((page_h - 10 * mm + 2 * mm) // (label_h + 2 * mm))
    per_page = columns * rows
    for index, row in enumerate(products):
        barcode, name, price, date_text, *rest = row
        article_id = rest[0] if rest else ""
        if index and index % per_page == 0:
            pdf.showPage()
        position = index % per_page
        row_number, column = divmod(position, columns)
        x = 5 * mm + column * (label_w + 2 * mm)
        y = page_h - 5 * mm - ((row_number + 1) * (label_h + 2 * mm)) + 2 * mm
        pdf.rect(x, y, label_w, label_h)
        price_text = format_price_arg(price)
        size = 44
        while size > 12 and pdfmetrics.stringWidth(price_text, "Helvetica-Bold", size) > label_w - 4 * mm:
            size -= 1
        pdf.setFont("Helvetica-Bold", size)
        pdf.drawCentredString(x + label_w / 2, y + label_h * 0.25, price_text)
        pdf.setFont("Helvetica-Bold", 10)
        lines = wrap_text_to_width(fix_encoding(name).strip().upper(), "Helvetica-Bold", 10, label_w - 4 * mm)[:4]
        cursor_y = y + label_h - 5 * mm
        for line in lines:
            if cursor_y < y + label_h * 0.25 + 14:
                break
            pdf.drawCentredString(x + label_w / 2, cursor_y, line)
            cursor_y -= 11.5
        pdf.setFont("Helvetica", 8)
        footer = f"{_footer_code(barcode, article_id)} - {str(date_text).strip() or today}"
        pdf.drawCentredString(x + label_w / 2, y + 2 * mm, footer)
    pdf.save()
    return buffer.getvalue()


def generar_pdf_por_tamanio(size: str, products: Iterable[tuple]) -> tuple[bytes, str]:
    products = list(products)
    if not products:
        raise ValueError("No hay productos seleccionados.")
    if size == "Gigante":
        return generar_carteles_gigantes(products), "carteles_gigantes.pdf"
    if size == "Mediana":
        return generar_precios_medianos(products), "precios_medianos.pdf"
    if size == "Chica":
        return generar_etiquetas_chicas(products), "etiquetas_chicas.pdf"
    raise ValueError(f"Tamaño desconocido: {size}")


def _open_csv_source(source: str | Path | BinaryIO):
    if hasattr(source, "seek"):
        source.seek(0)
    return source


def load_comparator_csv(source: str | Path | BinaryIO) -> pd.DataFrame:
    """Lee solo las cuatro columnas necesarias para evitar picos de memoria."""
    source = _open_csv_source(source)
    kwargs = dict(header=None, usecols=COMPARATOR_COLUMNS, dtype=str, keep_default_na=False, engine="c")
    try:
        frame = pd.read_csv(source, encoding="utf-8-sig", **kwargs)
    except UnicodeDecodeError:
        source = _open_csv_source(source)
        frame = pd.read_csv(source, encoding="cp1252", **kwargs)
    frame.columns = ["IdArticulo", "Descripcion", "Codigo_Catalogo", "Precio"]
    for column in ("IdArticulo", "Codigo_Catalogo"):
        frame[column] = frame[column].astype(str).str.strip()
    frame = frame[frame["IdArticulo"].ne("")].copy()
    frame["Precio_num"] = price_series(frame["Precio"])
    frame = frame.dropna(subset=["Precio_num"])
    frame = frame.drop_duplicates(subset=["IdArticulo"], keep="last")
    return frame


def compare_price_lists(source_a, source_b) -> tuple[pd.DataFrame, dict[str, int | str]]:
    frame_a, frame_b = load_comparator_csv(source_a), load_comparator_csv(source_b)
    paired = frame_a[["IdArticulo", "Precio_num"]].merge(
        frame_b[["IdArticulo", "Precio_num"]], on="IdArticulo", how="inner", suffixes=("_a", "_b"), validate="one_to_one"
    )
    if paired.empty:
        raise ValueError("Las listas no tienen IdArticulo coincidentes.")
    b_up = int((paired["Precio_num_b"] > paired["Precio_num_a"]).sum())
    a_up = int((paired["Precio_num_a"] > paired["Precio_num_b"]).sum())
    if b_up > a_up or (b_up == a_up and paired["Precio_num_b"].median() >= paired["Precio_num_a"].median()):
        old, new, order = frame_a, frame_b, "A→B"
    else:
        old, new, order = frame_b, frame_a, "B→A"
    merged = old[["IdArticulo", "Precio_num"]].merge(
        new[["IdArticulo", "Descripcion", "Codigo_Catalogo", "Precio", "Precio_num"]],
        on="IdArticulo", how="inner", suffixes=("_Anterior", "_Nuevo"), validate="one_to_one"
    )
    changed = merged[merged["Precio_num_Anterior"].round(4).ne(merged["Precio_num_Nuevo"].round(4))].copy()
    changed["Codigo_Impresion"] = changed["Codigo_Catalogo"].where(changed["Codigo_Catalogo"].ne(""), changed["IdArticulo"])
    changed["Movimiento"] = changed.apply(lambda row: "Aumento" if row["Precio_num_Nuevo"] > row["Precio_num_Anterior"] else "Baja", axis=1)
    changed = changed.sort_values(["Descripcion", "IdArticulo"], key=lambda col: col.astype(str).str.casefold()).reset_index(drop=True)
    result = changed[["IdArticulo", "Codigo_Impresion", "Descripcion", "Precio_num_Anterior", "Precio_num_Nuevo", "Movimiento"]]
    stats = {
        "coincidencias": len(merged),
        "cambios": len(result),
        "aumentos": int(result["Movimiento"].eq("Aumento").sum()),
        "bajas": int(result["Movimiento"].eq("Baja").sum()),
        "orden": order,
    }
    return result, stats


def make_product_lookup(products: pd.DataFrame) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for record in products.to_dict("records"):
        for field in ("Codigo_Barra", "IdArticulo"):
            key = normalize_code(record.get(field, ""))
            if key and key not in lookup:
                lookup[key] = record
    return lookup


def process_scan(raw_code: object, lookup: dict[str, dict], queue: list[dict], not_found: list[str]) -> bool:
    code = clean_code(raw_code)
    product = lookup.get(normalize_code(code))
    if product is None:
        if code:
            not_found.append(code)
        return False
    barcode = clean_code(product.get("Codigo_Barra"))
    article_id = clean_code(product.get("IdArticulo"))
    queue.append({
        "Imprimir": True,
        "Codigo_Barra": barcode or article_id,
        "IdArticulo": article_id,
        "Descripcion": fix_encoding(product.get("Descripcion", "")),
        "Precio": product.get("Precio", ""),
        "Fecha": product.get("Fecha") or date.today().strftime("%d/%m/%y"),
    })
    return True


def parse_product_csv_bytes(data: bytes) -> pd.DataFrame:
    text = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("No se pudo decodificar el CSV.")
    first = text.splitlines()[0] if text.splitlines() else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows:
        return pd.DataFrame(columns=["Codigo_Barra", "IdArticulo", "Descripcion", "Precio", "Fecha"])
    header = [fix_encoding(value).strip().casefold().replace(" ", "_") for value in rows[0]]
    aliases = {
        "Codigo_Barra": ("codigo_barra", "código_de_barras", "codigo_de_barras", "codigo_catalogo", "sku"),
        "IdArticulo": ("idarticulo", "id_articulo", "id_artículo"),
        "Descripcion": ("descripcion", "descripción", "producto", "nombre"),
        "Precio": ("precio_venta_final", "precio", "importe"),
        "Fecha": ("fecha",),
    }
    def index_for(names):
        return next((i for i, value in enumerate(header) if value in names), None)
    indices = {key: index_for(names) for key, names in aliases.items()}
    if indices["Codigo_Barra"] is None and indices["IdArticulo"] is None:
        raise ValueError("El CSV debe contener Codigo_Barra o IdArticulo.")
    records = []
    for row in rows[1:]:
        def get(name):
            index = indices[name]
            return row[index].strip() if index is not None and index < len(row) else ""
        barcode, article_id = get("Codigo_Barra"), get("IdArticulo")
        if not barcode and not article_id:
            continue
        records.append({"Codigo_Barra": barcode, "IdArticulo": article_id, "Descripcion": fix_encoding(get("Descripcion")), "Precio": get("Precio"), "Fecha": get("Fecha") or date.today().strftime("%d/%m/%y")})
    return pd.DataFrame(records)


def replace_tracking_remote(url: str, items: list[dict], post=requests.post) -> tuple[bool, str]:
    """Confirma el seguimiento sin propagar errores de red a Streamlit."""
    if not url:
        return False, "Falta APPS_SCRIPT_URL."
    try:
        response = post(url, json={"action": "replace_tracking", "items": items}, timeout=(4, 20))
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            return False, str(payload.get("error", "Respuesta inválida de Apps Script"))
        return True, f"Seguimiento actualizado: {payload.get('count', len(items))} productos."
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        return False, f"Apps Script no respondió. El PDF sigue disponible. Detalle: {exc}"
