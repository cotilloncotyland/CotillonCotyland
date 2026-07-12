"""Cotyland - etiquetas, escáner y comparación de precios."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import date

import pandas as pd
import requests
import streamlit as st

from cotyland_core import (
    compare_price_lists,
    generar_pdf_por_tamanio,
    make_product_lookup,
    parse_product_csv_bytes,
    process_scan,
    replace_tracking_remote,
)

ID_DRIVE = "1z1naxcQyryThMHj3H9K3xi27EDuugBPnFKrrwrJ8v1Y"
URL_DRIVE = f"https://docs.google.com/spreadsheets/d/{ID_DRIVE}/export?format=csv"
REQUEST_TIMEOUT = (4, 20)


def apps_script_url() -> str:
    try:
        return str(st.secrets.get("APPS_SCRIPT_URL", "")).strip()
    except (FileNotFoundError, KeyError):
        return ""


@st.cache_data(ttl=120, show_spinner=False)
def download_products(url: str) -> tuple[pd.DataFrame, str]:
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        frame = parse_product_csv_bytes(response.content)
        if frame.empty:
            return frame, "La base descargada no contiene productos."
        return frame, ""
    except (requests.RequestException, ValueError) as exc:
        return pd.DataFrame(), f"No se pudo cargar la base: {exc}"


@st.cache_data(ttl=120, show_spinner=False)
def load_tracking(url: str) -> tuple[set[str], str]:
    if not url:
        return set(), ""
    try:
        response = requests.get(url, params={"action": "get_tracking"}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise ValueError(payload.get("error", "Respuesta inválida de Apps Script"))
        keys = set()
        for item in payload.get("items", []):
            for field in ("Codigo_Barra", "IdArticulo"):
                value = str(item.get(field, "")).strip().casefold()
                if value:
                    keys.add(value)
        return keys, ""
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        return set(), f"No se pudo leer ETIQUETAS_SEGUIDAS: {exc}"


def save_tracking(url: str, selected: pd.DataFrame) -> tuple[bool, str]:
    items = selected[["Codigo_Impresion", "IdArticulo"]].rename(columns={"Codigo_Impresion": "Codigo_Barra"}).to_dict("records")
    ok, message = replace_tracking_remote(url, items)
    if ok:
        load_tracking.clear()
    return ok, message


def install_scanner_key_guard() -> None:
    """Componente mínimo: bloquea F2/F11; no hace fetch ni inyecta el PDF."""
    st.iframe(
        """
        <script>
        (() => {
          const doc = window.parent.document;
          if (!window.parent.__cotylandKeyGuard) {
            doc.addEventListener('keydown', (event) => {
              if (event.key === 'F2' || event.key === 'F11') {
                event.preventDefault();
                event.stopImmediatePropagation();
              }
            }, true);
            window.parent.__cotylandKeyGuard = true;
          }
          setTimeout(() => {
            const input = [...doc.querySelectorAll('input')].find(
              element => (element.getAttribute('aria-label') || '').includes('ESCANEÁ ACÁ')
            );
            if (input) input.focus();
          }, 80);
        })();
        </script>
        """,
        height=1,
    )


def search_mask(frame: pd.DataFrame, query: str, columns: list[str]) -> pd.Series:
    if frame.empty or not query.strip():
        return pd.Series(True, index=frame.index)
    mask = pd.Series(False, index=frame.index)
    needle = query.strip().casefold()
    for column in columns:
        if column in frame:
            mask |= frame[column].fillna("").astype(str).str.casefold().str.contains(needle, regex=False)
    return mask


def update_visible_selection(state_key: str, edited: pd.DataFrame, selection_column: str) -> None:
    if edited.empty:
        return
    selection = edited.set_index("_id")[selection_column].to_dict()
    frame = st.session_state[state_key].copy()
    frame[selection_column] = [bool(selection.get(row_id, current)) for row_id, current in zip(frame["_id"], frame[selection_column])]
    st.session_state[state_key] = frame


def product_rows(frame: pd.DataFrame) -> list[tuple]:
    return [
        (row["Codigo_Barra"], row["Descripcion"], row["Precio"], row["Fecha"], row.get("IdArticulo", ""))
        for _, row in frame.iterrows()
    ]


def pdf_controls(prefix: str, selected: pd.DataFrame) -> None:
    size = st.radio("Tamaño de las etiquetas", ["Chica", "Mediana", "Gigante"], horizontal=True, key=f"{prefix}_size")
    if st.button(f"Generar PDF ({len(selected)} seleccionados)", type="primary", width="stretch", disabled=selected.empty, key=f"{prefix}_generate"):
        try:
            pdf_bytes, filename = generar_pdf_por_tamanio(size, product_rows(selected))
            st.session_state[f"{prefix}_pdf"] = pdf_bytes
            st.session_state[f"{prefix}_pdf_name"] = filename
        except Exception as exc:
            st.error(f"No se pudo generar el PDF: {exc}")
    if st.session_state.get(f"{prefix}_pdf"):
        st.download_button(
            "Descargar PDF",
            data=st.session_state[f"{prefix}_pdf"],
            file_name=st.session_state[f"{prefix}_pdf_name"],
            mime="application/pdf",
            width="stretch",
            key=f"{prefix}_download",
        )


st.set_page_config(page_title="Cotyland Nube", page_icon="🎈", layout="wide")
st.html(
    """
    <style>
      div[data-testid="stColumn"] button {min-height: 48px; font-size: 16px; font-weight: 700; border-radius: 10px;}
      div[data-testid="stDataFrame"] iframe {width: 100%;}
    </style>
    """
)
st.title("🎈 Cotyland - Panel Multiplataforma")
tab_scanner, tab_csv, tab_compare = st.tabs([
    "📱 Buscador Móvil",
    "🖨️ Generador de Etiquetas (CSV)",
    "📊 Comparador de Precios",
])


with tab_scanner:
    for key, default in {
        "scan_queue": [], "scan_not_found": [], "scan_message": "", "scanner_pdf": None, "scanner_pdf_name": ""
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    products, product_error = download_products(URL_DRIVE)
    if product_error:
        st.error(product_error)
    else:
        st.caption(f"🟢 Motor activo: {len(products)} artículos en caché.")
    lookup = make_product_lookup(products) if not products.empty else {}

    def handle_scan() -> None:
        raw = st.session_state.get("scanner_input", "")
        st.session_state.scanner_input = ""
        if not str(raw).strip():
            return
        found = process_scan(raw, lookup, st.session_state.scan_queue, st.session_state.scan_not_found)
        st.session_state.scan_message = "Producto agregado." if found else f"Código no encontrado: {raw}"
        st.session_state.scanner_pdf = None
        st.session_state.scanner_pdf_name = ""

    st.text_input(
        "🔎 ESCANEÁ ACÁ (MODO CORRELATIVO CONSTANTE):",
        key="scanner_input",
        on_change=handle_scan,
        placeholder="Hacé un clic y pasá los códigos de corrido...",
    )
    install_scanner_key_guard()
    if st.session_state.scan_message:
        if st.session_state.scan_message.startswith("Código no encontrado"):
            st.warning(st.session_state.scan_message)
        else:
            st.success(st.session_state.scan_message)
    if st.session_state.scan_not_found:
        with st.expander(f"No encontrados ({len(st.session_state.scan_not_found)})"):
            st.write(" · ".join(st.session_state.scan_not_found[-50:]))

    if st.session_state.scan_queue:
        st.subheader("📋 Lista Correlativa de Impresión Actual")
        query = st.text_input("Buscador", key="scanner_search", placeholder="Código o descripción")
        left, middle, right = st.columns(3)
        if left.button("Seleccionar todos", width="stretch", key="scanner_all"):
            for item in st.session_state.scan_queue:
                item["Imprimir"] = True
            st.rerun()
        if middle.button("Deseleccionar todos", width="stretch", key="scanner_none"):
            for item in st.session_state.scan_queue:
                item["Imprimir"] = False
            st.rerun()
        if right.button("Vaciar lista", width="stretch", key="scanner_clear"):
            st.session_state.scan_queue = []
            st.session_state.scan_not_found = []
            st.session_state.scanner_pdf = None
            st.rerun()
        queue_frame = pd.DataFrame(st.session_state.scan_queue)
        queue_frame.insert(0, "_id", range(len(queue_frame)))
        visible = queue_frame[search_mask(queue_frame, query, ["Codigo_Barra", "Descripcion"])].copy()
        edited = st.data_editor(
            visible,
            column_config={"Imprimir": st.column_config.CheckboxColumn(default=True), "_id": None},
            disabled=["Codigo_Barra", "IdArticulo", "Descripcion", "Precio", "Fecha"],
            hide_index=True,
            width="stretch",
            key="scanner_editor",
        )
        selected_ids = set(edited.loc[edited["Imprimir"], "_id"])
        visible_ids = set(edited["_id"])
        for index, item in enumerate(st.session_state.scan_queue):
            if index in visible_ids:
                item["Imprimir"] = index in selected_ids
        selected = pd.DataFrame([item for item in st.session_state.scan_queue if item["Imprimir"]])
        pdf_controls("scanner", selected)


with tab_csv:
    st.subheader("1. Arrastrá tu archivo de precios")
    upload = st.file_uploader("Subir CSV de Precios", type=["csv"], key="labels_upload")
    if upload:
        signature = hashlib.sha256(upload.getvalue()).hexdigest()
        if st.session_state.get("labels_signature") != signature:
            frame = parse_product_csv_bytes(upload.getvalue())
            frame.insert(0, "_id", range(len(frame)))
            frame.insert(1, "Imprimir", True)
            st.session_state.labels_frame = frame
            st.session_state.labels_signature = signature
            st.session_state.labels_pdf = None
        frame = st.session_state.labels_frame
        st.success(f"Archivo leído: {len(frame)} productos.")
        query = st.text_input("Buscador", key="labels_search")
        left, right = st.columns(2)
        if left.button("Seleccionar todos", width="stretch", key="labels_all"):
            st.session_state.labels_frame["Imprimir"] = True
            st.rerun()
        if right.button("Deseleccionar todos", width="stretch", key="labels_none"):
            st.session_state.labels_frame["Imprimir"] = False
            st.rerun()
        visible = frame[search_mask(frame, query, ["Codigo_Barra", "IdArticulo", "Descripcion"])].copy()
        edited = st.data_editor(
            visible,
            column_config={"Imprimir": st.column_config.CheckboxColumn(default=True), "_id": None},
            disabled=["Codigo_Barra", "IdArticulo", "Descripcion", "Precio", "Fecha"],
            hide_index=True,
            width="stretch",
            key="labels_editor",
        )
        update_visible_selection("labels_frame", edited, "Imprimir")
        selected = st.session_state.labels_frame[st.session_state.labels_frame["Imprimir"]]
        pdf_controls("labels", selected)


with tab_compare:
    st.subheader("📊 Comparar Cambios de Precios")
    col_a, col_b = st.columns(2)
    file_a = col_a.file_uploader("Subir Archivo de Lista (A)", type=["csv"], key="compare_a")
    file_b = col_b.file_uploader("Subir Archivo de Lista (B)", type=["csv"], key="compare_b")
    if file_a and file_b and st.button("Cruzar Listas y Detectar Cambios", type="primary", width="stretch"):
        try:
            changes, stats = compare_price_lists(io.BytesIO(file_a.getvalue()), io.BytesIO(file_b.getvalue()))
            followed, tracking_error = load_tracking(apps_script_url())
            changes.insert(0, "_id", range(len(changes)))
            changes.insert(1, "Imprimir", [
                str(row.Codigo_Impresion).casefold() in followed or str(row.IdArticulo).casefold() in followed
                for row in changes.itertuples()
            ])
            st.session_state.compare_frame = changes
            st.session_state.compare_stats = stats
            st.session_state.compare_tracking_error = tracking_error
            st.session_state.compare_pdf = None
        except Exception as exc:
            st.error(f"No se pudieron comparar los archivos: {exc}")

    if "compare_frame" in st.session_state:
        stats = st.session_state.compare_stats
        metric_cols = st.columns(4)
        metric_cols[0].metric("Coincidencias", stats["coincidencias"])
        metric_cols[1].metric("Cambios", stats["cambios"])
        metric_cols[2].metric("Aumentos", stats["aumentos"])
        metric_cols[3].metric("Bajas", stats["bajas"])
        if st.session_state.get("compare_tracking_error"):
            st.warning(st.session_state.compare_tracking_error)
        frame = st.session_state.compare_frame
        query = st.text_input("Buscador", key="compare_search")
        left, right = st.columns(2)
        if left.button("Seleccionar todos", width="stretch", key="compare_all"):
            st.session_state.compare_frame["Imprimir"] = True
            st.rerun()
        if right.button("Deseleccionar todos", width="stretch", key="compare_none"):
            st.session_state.compare_frame["Imprimir"] = False
            st.rerun()
        visible = frame[search_mask(frame, query, ["IdArticulo", "Codigo_Impresion", "Descripcion", "Movimiento"])].copy()
        edited = st.data_editor(
            visible,
            column_config={"Imprimir": st.column_config.CheckboxColumn(default=False), "_id": None},
            disabled=["IdArticulo", "Codigo_Impresion", "Descripcion", "Precio_num_Anterior", "Precio_num_Nuevo", "Movimiento"],
            hide_index=True,
            width="stretch",
            key="compare_editor",
        )
        update_visible_selection("compare_frame", edited, "Imprimir")
        selected = st.session_state.compare_frame[st.session_state.compare_frame["Imprimir"]].copy()
        selected_for_pdf = selected.rename(columns={"Codigo_Impresion": "Codigo_Barra", "Precio_num_Nuevo": "Precio"})
        selected_for_pdf["Fecha"] = date.today().strftime("%d/%m/%y")
        pdf_controls("compare", selected_for_pdf)
        if st.button("Confirmar seguimiento en Drive", width="stretch", disabled=selected.empty):
            ok, message = save_tracking(apps_script_url(), selected)
            (st.success if ok else st.warning)(message)
