import requests
import pytest
import io
from pypdf import PdfReader

from cotyland_core import (
    fetch_tracking_items_remote,
    fetch_tracking_remote,
    generar_pdf_por_tamanio,
    mutate_tracking_remote,
    replace_tracking_remote,
)


PRODUCTS = [
    (".10200261", "Producto de prueba con descripción extensa", "12.345,67", "12/07/26", "ID-1"),
    ("", "Usa IdArticulo si falta código", "999,50", "12/07/26", "00123"),
]


def test_generate_all_three_pdf_sizes(tmp_path):
    for size in ("Chica", "Mediana", "Gigante"):
        data, filename = generar_pdf_por_tamanio(size, PRODUCTS)
        path = tmp_path / filename
        path.write_bytes(data)
        reader = PdfReader(path)
        assert data.startswith(b"%PDF-")
        assert len(reader.pages) >= 1
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert ".10200261" in text
        assert "00123" in text


def pdf_text_positions(size, description):
    data, _ = generar_pdf_por_tamanio(size, [("AB-001", description, "12345,67", "12/07/26", "SKU")])
    fragments = []

    def visit(text, current_matrix, text_matrix, font_dictionary, font_size):
        if text.strip():
            fragments.append((text.strip(), float(text_matrix[5]), float(font_size)))

    PdfReader(io.BytesIO(data)).pages[0].extract_text(visitor_text=visit)
    return fragments


@pytest.mark.parametrize("size", ["Chica", "Mediana", "Gigante"])
def test_long_description_never_overlaps_or_moves_price(size):
    short = pdf_text_positions(size, "DESCRIPCION CORTA")
    long = pdf_text_positions(
        size,
        "DESCRIPCION EXTREMADAMENTE LARGA CON MUCHAS PALABRAS PARA VERIFICAR QUE NUNCA PISE EL PRECIO CENTRAL FIJO DE LA ETIQUETA",
    )
    short_price = next(item for item in short if item[0].startswith("$"))
    long_price = next(item for item in long if item[0].startswith("$"))
    description_fragments = [item for item in long if item[0].startswith(("DESCRIPCION", "MUCHAS", "PISE", "LARGA", "VERIFICAR", "CENTRAL"))]

    assert long_price[1:] == short_price[1:]
    assert description_fragments
    assert min(item[1] for item in description_fragments) > long_price[1] + long_price[2] * 0.75


def test_apps_script_network_error_does_not_raise():
    def failing_post(*args, **kwargs):
        raise requests.ConnectionError("red simulada fuera de servicio")

    ok, message = replace_tracking_remote("https://invalid.example", [{"Codigo_Barra": "AB-123", "IdArticulo": "1"}], post=failing_post)
    assert ok is False
    assert "PDF sigue disponible" in message


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_apps_script_tracking_valid_response():
    def fake_get(*args, **kwargs):
        assert kwargs["timeout"] == (4, 8)
        return FakeResponse({"ok": True, "items": [{"Codigo_Barra": "00123", "IdArticulo": "ART-1"}]})

    followed, warning = fetch_tracking_remote("https://valid.example", get=fake_get)
    assert followed == {"00123", "art-1"}
    assert warning == ""


def test_incremental_tracking_preserves_literal_codes_and_description():
    def fake_get(*args, **kwargs):
        return FakeResponse({"ok": True, "items": [{
            "Codigo_Barra": ".001-AB", "IdArticulo": "DL0026", "Descripcion": "Producto (prueba), especial"
        }]})

    items, warning = fetch_tracking_items_remote("https://valid.example", get=fake_get)
    assert warning == ""
    assert items == [{"Codigo_Barra": ".001-AB", "IdArticulo": "DL0026", "Descripcion": "Producto (prueba), especial"}]


@pytest.mark.parametrize("action", ["add_tracking", "upsert_tracking", "remove_tracking"])
def test_incremental_tracking_sends_only_requested_operation(action):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        return FakeResponse({"ok": True, "added": 0, "existing": 1, "removed": 0, "total": 3})

    ok, payload, _ = mutate_tracking_remote(
        "https://valid.example", action,
        [{"Codigo_Barra": "00123", "IdArticulo": "ART-1", "Descripcion": "Producto"}],
        post=fake_post,
    )
    assert ok
    assert calls[0]["json"]["action"] == action
    assert "replace_tracking" not in str(calls[0]["json"])
    assert payload["total"] == 3


def test_incremental_tracking_network_failure_leaves_pending():
    def failing_post(*args, **kwargs):
        raise requests.Timeout("timeout controlado")

    ok, payload, message = mutate_tracking_remote(
        "https://invalid.example", "upsert_tracking", [{"Codigo_Barra": "AB-123", "IdArticulo": "1"}], post=failing_post
    )
    assert not ok
    assert payload == {}
    assert "pendiente" in message


@pytest.mark.parametrize("error", [requests.ConnectionError("inválida"), requests.Timeout("timeout")])
def test_apps_script_tracking_failure_is_warning(error):
    def failing_get(*args, **kwargs):
        raise error

    followed, warning = fetch_tracking_remote("https://bad.example", get=failing_get)
    assert followed == set()
    assert "No se pudo leer ETIQUETAS_SEGUIDAS" in warning
