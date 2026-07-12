import requests
from pypdf import PdfReader

from cotyland_core import generar_pdf_por_tamanio, replace_tracking_remote


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


def test_apps_script_network_error_does_not_raise():
    def failing_post(*args, **kwargs):
        raise requests.ConnectionError("red simulada fuera de servicio")

    ok, message = replace_tracking_remote("https://invalid.example", [{"Codigo_Barra": "AB-123", "IdArticulo": "1"}], post=failing_post)
    assert ok is False
    assert "PDF sigue disponible" in message

