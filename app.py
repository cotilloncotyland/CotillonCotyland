"""Cotyland - etiquetas, escáner y comparación de precios."""

from __future__ import annotations

import hashlib
import io
from datetime import date
from pathlib import Path
from uuid import uuid4

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

from cotyland_core import (
    apply_print_codes_from_catalog,
    compare_price_lists,
    fetch_tracking_items_remote,
    fetch_tracking_remote,
    generar_pdf_por_tamanio,
    make_product_lookup,
    mutate_tracking_remote,
    parse_product_csv_bytes,
    process_scan,
)

ID_DRIVE = "1z1naxcQyryThMHj3H9K3xi27EDuugBPnFKrrwrJ8v1Y"
URL_DRIVE = f"https://docs.google.com/spreadsheets/d/{ID_DRIVE}/export?format=csv"
REQUEST_TIMEOUT = (4, 20)
STATIC_PDF_DIR = Path(__file__).resolve().parent / "static" / "generated_pdfs"


def apps_script_url() -> str:
    try:
        return str(st.secrets.get("APPS_SCRIPT_URL", "")).strip()
    except (FileNotFoundError, KeyError):
        return ""


@st.cache_data(ttl=15, show_spinner=False)
def download_products(url: str) -> tuple[pd.DataFrame, str]:
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
        )
        response.raise_for_status()
        frame = parse_product_csv_bytes(response.content)
        if frame.empty:
            return frame, "La base descargada no contiene productos."
        return frame, ""
    except (requests.RequestException, ValueError) as exc:
        return pd.DataFrame(), f"No se pudo cargar la base: {exc}"


@st.cache_data(ttl=120, show_spinner=False)
def load_tracking(url: str) -> tuple[set[str], str]:
    return fetch_tracking_remote(url)


def install_scanner_key_guard() -> None:
    """Recupera el guard AV2, limitado exclusivamente al campo del escáner."""
    components.html(
        """
        <script>
        (() => {
          const doc = window.parent.document;
          const previous = window.parent.__cotylandKeyGuardHandler;
          if (previous) {
            doc.removeEventListener('keydown', previous, true);
          }
          const handler = (event) => {
            const scanner = [...doc.querySelectorAll('input')].find(
              element => (element.getAttribute('aria-label') || '').includes('ESCANEÁ ACÁ')
            );
            const isScannerActive = scanner && (event.target === scanner || doc.activeElement === scanner);
            const isReaderFunction = event.key === 'F2' || event.key === 'F11' ||
              event.keyCode === 113 || event.keyCode === 122;
            if (isScannerActive && isReaderFunction) {
              event.preventDefault();
              event.stopImmediatePropagation();
              setTimeout(() => scanner.focus({preventScroll: true}), 10);
            }
          };
          window.parent.__cotylandKeyGuardHandler = handler;
          doc.addEventListener('keydown', handler, true);
          setTimeout(() => {
            const input = [...doc.querySelectorAll('input')].find(
              element => (element.getAttribute('aria-label') || '').includes('ESCANEÁ ACÁ')
            );
            if (input) input.focus();
          }, 80);
        })();
        </script>
        """,
        height=0,
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


def publish_generated_pdf(prefix: str, pdf_bytes: bytes) -> str:
    """Publica bytes ya generados sin incorporarlos al HTML ni regenerarlos."""
    STATIC_PDF_DIR.mkdir(parents=True, exist_ok=True)
    token = st.session_state.setdefault("pdf_session_token", uuid4().hex)
    filename = f"{token}_{prefix}_{uuid4().hex}.pdf"
    target = STATIC_PDF_DIR / filename
    target.write_bytes(pdf_bytes)
    return f"/app/static/generated_pdfs/{filename}"


def direct_print_control(pdf_url: str, prefix: str) -> None:
    """Abre el PDF ya generado con un control nativo y sin regenerarlo."""
    st.link_button("Abrir PDF para imprimir", pdf_url, width="stretch", type="primary")
    st.caption("El PDF se abre en otra pestaña. Presioná Ctrl+P para imprimir.")


def pdf_controls(prefix: str, selected: pd.DataFrame) -> None:
    size = st.radio("Tamaño de las etiquetas", ["Chica", "Mediana", "Gigante"], horizontal=True, key=f"{prefix}_size")
    if st.button(f"Generar PDF ({len(selected)} seleccionados)", type="primary", width="stretch", disabled=selected.empty, key=f"{prefix}_generate"):
        try:
            pdf_bytes, filename = generar_pdf_por_tamanio(size, product_rows(selected))
            st.session_state[f"{prefix}_pdf"] = pdf_bytes
            st.session_state[f"{prefix}_pdf_name"] = filename
            st.session_state[f"{prefix}_pdf_url"] = publish_generated_pdf(prefix, pdf_bytes)
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
        direct_print_control(st.session_state[f"{prefix}_pdf_url"], prefix)


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
        "scan_queue": [], "scan_not_found": [], "scan_message": "", "scanner_pdf": None, "scanner_pdf_name": "", "scanner_pdf_url": "", "product_base_ready": False
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    products = pd.DataFrame()
    product_error = ""
    if st.session_state.product_base_ready:
        products, product_error = download_products(URL_DRIVE)
    if product_error:
        st.warning(product_error)
    elif not products.empty:
        st.caption(f"🟢 Motor activo: {len(products)} artículos en caché.")
    lookup = make_product_lookup(products) if not products.empty else {}

    def handle_scan() -> None:
        raw = st.session_state.get("scanner_input", "")
        st.session_state.scanner_input = ""
        if not str(raw).strip():
            return
        callback_products, callback_error = download_products(URL_DRIVE)
        st.session_state.product_base_ready = True
        if callback_error or callback_products.empty:
            st.session_state.scan_message = callback_error or "La base de productos está vacía."
            return
        callback_lookup = make_product_lookup(callback_products)
        found = process_scan(raw, callback_lookup, st.session_state.scan_queue, st.session_state.scan_not_found)
        if found and st.session_state.scan_queue:
            # El escaneo nunca espera a Google Drive.
            # El producto queda en memoria y se envía después, junto con los demás.
            latest = st.session_state.scan_queue[-1]
            if "_DriveStatus" not in latest:
                latest["_DriveStatus"] = "Pendiente de guardar"
                latest.pop("_DriveError", None)
        st.session_state.scan_message = "Producto agregado." if found else f"Código no encontrado: {raw}"
        st.session_state.scanner_pdf = None
        st.session_state.scanner_pdf_name = ""
        st.session_state.scanner_pdf_url = ""

    st.text_input(
        "🔎 ESCANEÁ ACÁ (MODO CORRELATIVO CONSTANTE):",
        key="scanner_input",
        on_change=handle_scan,
        placeholder="Hacé un clic y pasá los códigos de corrido...",
    )
    install_scanner_key_guard()
    if st.session_state.scan_queue:
        # IMPORTANTE:
        # No se llama a Apps Script durante cada escaneo.
        # Todos los productos pendientes se envían juntos en una sola operación.
        pending_items = [
            item
            for item in st.session_state.scan_queue
            if item.get("_DriveStatus") not in {"Guardado en Drive", "Ya estaba guardado"}
        ]

        if pending_items:
            st.caption(
                f"⚡ Escaneo rápido activo: {len(pending_items)} producto(s) "
                "quedaron listos para guardar juntos."
            )

            if st.button(
                f"💾 Guardar pendientes en Drive ({len(pending_items)})",
                key="save_tracking_batch",
                type="primary",
            ):
                payload_items = [
                    {
                        field: item.get(field, "")
                        for field in ("Codigo_Barra", "IdArticulo", "Descripcion")
                    }
                    for item in pending_items
                ]

                ok, payload, message = mutate_tracking_remote(
                    apps_script_url(),
                    "upsert_tracking",
                    payload_items,
                )

                if ok:
                    for item in pending_items:
                        item["_DriveStatus"] = "Guardado en Drive"
                        item.pop("_DriveError", None)

                    load_tracking.clear()
                    added = int(payload.get("added", 0) or 0)
                    existing = int(payload.get("existing", 0) or 0)
                    st.success(
                        f"Guardado en una sola operación: "
                        f"{added} nuevo(s), {existing} ya existente(s)."
                    )
                    st.rerun()
                else:
                    for item in pending_items:
                        item["_DriveStatus"] = "Pendiente de guardar"
                        item["_DriveError"] = message
                    st.warning(
                        "No se pudo guardar el lote todavía. "
                        "Los productos siguen en la lista y no se perdieron. "
                        f"Detalle: {message}"
                    )

    if st.session_state.scan_message:
        if st.session_state.scan_message.startswith("Código no encontrado") or "No se pudo" in st.session_state.scan_message or "vacía" in st.session_state.scan_message:
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
            st.session_state.scanner_pdf_url = ""
            st.rerun()
        queue_frame = pd.DataFrame(st.session_state.scan_queue)
        queue_frame["Estado Drive"] = queue_frame.get("_DriveStatus", "")
        queue_frame = queue_frame.drop(columns=["_DriveStatus", "_DriveError"], errors="ignore")
        queue_frame.insert(0, "_id", range(len(queue_frame)))
        visible = queue_frame[search_mask(queue_frame, query, ["Codigo_Barra", "Descripcion"])].copy()
        edited = st.data_editor(
            visible,
            column_config={"Imprimir": st.column_config.CheckboxColumn(default=True), "_id": None},
            disabled=["Codigo_Barra", "IdArticulo", "Descripcion", "Precio", "Fecha", "Estado Drive"],
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
            st.session_state.labels_pdf_url = ""
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
            catalog_products, catalog_error = download_products(URL_DRIVE)
            changes = apply_print_codes_from_catalog(changes, catalog_products)
            tracked_items, tracking_error = fetch_tracking_items_remote(apps_script_url())
            followed = {
                str(item.get(field, "")).strip().casefold()
                for item in tracked_items for field in ("Codigo_Barra", "IdArticulo")
                if str(item.get(field, "")).strip()
            }
            changes.insert(0, "_id", range(len(changes)))
            followed_flags = [
                str(row.Codigo_Impresion).casefold() in followed or str(row.IdArticulo).casefold() in followed
                for row in changes.itertuples()
            ]
            changes.insert(1, "Imprimir", followed_flags)
            changes.insert(2, "En seguimiento", followed_flags)
            st.session_state.compare_frame = changes
            st.session_state.compare_original_followed = set(changes.loc[changes["En seguimiento"], "_id"])
            st.session_state.tracking_admin_items = tracked_items
            st.session_state.compare_stats = stats
            st.session_state.compare_tracking_error = " · ".join(message for message in (catalog_error, tracking_error) if message)
            st.session_state.compare_pdf = None
            st.session_state.compare_pdf_url = ""
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
        with st.form("compare_selection_form"):
            edited = st.data_editor(
                visible,
                column_config={
                    "Imprimir": st.column_config.CheckboxColumn(default=False),
                    "En seguimiento": st.column_config.CheckboxColumn(default=False),
                    "_id": None,
                },
                disabled=["IdArticulo", "Codigo_Impresion", "Descripcion", "Precio_num_Anterior", "Precio_num_Nuevo", "Movimiento"],
                hide_index=True,
                width="stretch",
                key="compare_editor",
            )
            apply_selection = st.form_submit_button("Aplicar selección", width="stretch")
        if apply_selection:
            update_visible_selection("compare_frame", edited, "Imprimir")
            update_visible_selection("compare_frame", edited, "En seguimiento")
        selected = st.session_state.compare_frame[st.session_state.compare_frame["Imprimir"]].copy()
        selected_for_pdf = selected.rename(columns={"Codigo_Impresion": "Codigo_Barra", "Precio_num_Nuevo": "Precio"})
        selected_for_pdf["Fecha"] = date.today().strftime("%d/%m/%y")
        pdf_controls("compare", selected_for_pdf)
        current_followed = set(st.session_state.compare_frame.loc[st.session_state.compare_frame["En seguimiento"], "_id"])
        original_followed = set(st.session_state.get("compare_original_followed", set()))
        additions = st.session_state.compare_frame[st.session_state.compare_frame["_id"].isin(current_followed - original_followed)]
        removals = st.session_state.compare_frame[st.session_state.compare_frame["_id"].isin(original_followed - current_followed)]
        if st.button("Guardar altas y bajas del seguimiento", width="stretch", disabled=additions.empty and removals.empty):
            add_items = additions.rename(columns={"Codigo_Impresion": "Codigo_Barra"})[["Codigo_Barra", "IdArticulo", "Descripcion"]].to_dict("records")
            remove_items = removals.rename(columns={"Codigo_Impresion": "Codigo_Barra"})[["Codigo_Barra", "IdArticulo", "Descripcion"]].to_dict("records")
            add_ok, add_payload, add_message = mutate_tracking_remote(apps_script_url(), "upsert_tracking", add_items) if add_items else (True, {"added": 0}, "")
            remove_ok, remove_payload, remove_message = mutate_tracking_remote(apps_script_url(), "remove_tracking", remove_items) if remove_items else (True, {"removed": 0}, "")
            if add_ok and remove_ok:
                st.session_state.compare_original_followed = current_followed
                load_tracking.clear()
                total = remove_payload.get("total", add_payload.get("total", len(current_followed)))
                st.success(f"Agregados: {add_payload.get('added', 0)} · Eliminados: {remove_payload.get('removed', 0)} · Total: {total}")
            else:
                st.warning(" · ".join(message for ok, message in ((add_ok, add_message), (remove_ok, remove_message)) if not ok))

    with st.expander("Administrar productos seguidos"):
        if st.button("Cargar o actualizar seguimiento", key="tracking_admin_load"):
            admin_items, admin_error = fetch_tracking_items_remote(apps_script_url())
            st.session_state.tracking_admin_items = admin_items
            st.session_state.tracking_admin_error = admin_error
        if st.session_state.get("tracking_admin_error"):
            st.warning(st.session_state.tracking_admin_error)
        admin_items = st.session_state.get("tracking_admin_items", [])
        if admin_items:
            admin_frame = pd.DataFrame(admin_items)
            admin_frame.insert(0, "_id", range(len(admin_frame)))
            admin_frame.insert(1, "Eliminar", False)
            admin_query = st.text_input("Buscar productos seguidos", key="tracking_admin_search")
            admin_visible = admin_frame[search_mask(admin_frame, admin_query, ["Codigo_Barra", "IdArticulo", "Descripcion"])]
            admin_edited = st.data_editor(admin_visible, column_config={"Eliminar": st.column_config.CheckboxColumn(default=False), "_id": None}, disabled=["Codigo_Barra", "IdArticulo", "Descripcion"], hide_index=True, width="stretch", key="tracking_admin_editor")
            to_remove = admin_edited[admin_edited["Eliminar"]][["Codigo_Barra", "IdArticulo", "Descripcion"]].to_dict("records")
            if st.button("Eliminar seleccionados", disabled=not to_remove, key="tracking_admin_remove"):
                ok, payload, message = mutate_tracking_remote(apps_script_url(), "remove_tracking", to_remove)
                if ok:
                    removed_keys = {(str(item["IdArticulo"]).casefold(), str(item["Codigo_Barra"]).casefold()) for item in to_remove}
                    st.session_state.tracking_admin_items = [item for item in admin_items if (str(item.get("IdArticulo", "")).casefold(), str(item.get("Codigo_Barra", "")).casefold()) not in removed_keys]
                    st.success(f"Eliminados: {payload.get('removed', 0)} · Total: {payload.get('total', 0)}")
                    st.rerun()
                else:
                    st.warning(message)
            confirm_empty = st.checkbox("Confirmo que deseo vaciar completamente el seguimiento", key="tracking_admin_confirm_empty")
            if st.button("Vaciar seguimiento", disabled=not confirm_empty, key="tracking_admin_empty"):
                ok, payload, message = mutate_tracking_remote(apps_script_url(), "remove_tracking", admin_items)
                if ok:
                    st.session_state.tracking_admin_items = []
                    st.success(f"Seguimiento vacío. Eliminados: {payload.get('removed', 0)}")
                    st.rerun()
                else:
                    st.warning(message)
        elif "tracking_admin_items" in st.session_state and not st.session_state.get("tracking_admin_error"):
            st.info("No hay productos en seguimiento.")
