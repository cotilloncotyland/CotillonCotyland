import pandas as pd
from pypdf import PdfReader

from cotyland_core import apply_print_codes_from_catalog, generar_pdf_por_tamanio, parse_product_csv_bytes


def comparison_changes():
    return pd.DataFrame([
        {"IdArticulo": "ART-1", "Codigo_Impresion": "ART-1", "Descripcion": "Uno"},
        {"IdArticulo": "ART-2", "Codigo_Impresion": "ART-2", "Descripcion": "Dos"},
        {"IdArticulo": "ART-3", "Codigo_Impresion": "ART-3", "Descripcion": "Tres"},
        {"IdArticulo": "NO-EXISTE", "Codigo_Impresion": "NO-EXISTE", "Descripcion": "Cuatro"},
    ])


def test_catalog_csv_preserves_quoted_description_and_text_codes():
    csv_data = (
        'Codigo_Barra;Descripcion;Precio_Venta_Final;IdArticulo\r\n'
        '"00123";"Producto, \"\"Especial\"\"; (grande) - azul";"1.234,56";"ART-1"\r\n'
        '"QL.10234027";"Cotillón (línea A-B)";"2.000,00";"ART-2"\r\n'
        '"AB-123";"Artículo con puntos... y guiones - internos";"3.000,00";"ART-3"\r\n'
        '"";"Sin código; usa fallback";"4.000,00";"ART-4"\r\n'
    ).encode("utf-8")

    catalog = parse_product_csv_bytes(csv_data)

    assert list(catalog["Codigo_Barra"]) == ["00123", "QL.10234027", "AB-123", ""]
    assert catalog.loc[0, "Descripcion"] == 'Producto, "Especial"; (grande) - azul'
    assert catalog.loc[0, "IdArticulo"] == "ART-1"
    assert catalog.loc[0, "Precio"] == "1.234,56"


def test_comparator_uses_catalog_barcode_and_falls_back_to_article_id():
    catalog = pd.DataFrame([
        {"IdArticulo": "ART-1", "Codigo_Barra": "00123"},
        {"IdArticulo": "ART-2", "Codigo_Barra": "QL.10234027"},
        {"IdArticulo": "ART-3", "Codigo_Barra": "AB-123"},
        {"IdArticulo": "NO-BARCODE", "Codigo_Barra": ""},
    ])

    result = apply_print_codes_from_catalog(comparison_changes(), catalog)

    assert result.loc[0, "Codigo_Impresion"] == "00123"
    assert result.loc[0, "Codigo_Impresion"] != result.loc[0, "IdArticulo"]
    assert result.loc[1, "Codigo_Impresion"] == "QL.10234027"
    assert result.loc[2, "Codigo_Impresion"] == "AB-123"
    assert result.loc[3, "Codigo_Impresion"] == "NO-EXISTE"
    assert list(comparison_changes()["Codigo_Impresion"]) == ["ART-1", "ART-2", "ART-3", "NO-EXISTE"]


def test_empty_catalog_barcode_uses_article_id_fallback():
    changes = pd.DataFrame([{"IdArticulo": "00077", "Codigo_Impresion": "incorrecto"}])
    catalog = pd.DataFrame([{"IdArticulo": "00077", "Codigo_Barra": ""}])

    result = apply_print_codes_from_catalog(changes, catalog)

    assert result.loc[0, "Codigo_Impresion"] == "00077"


def test_all_comparator_pdf_sizes_print_codigo_impresion(tmp_path):
    changes = pd.DataFrame([{
        "IdArticulo": "SKU-DISTINTO",
        "Codigo_Impresion": "SKU-DISTINTO",
        "Descripcion": "Producto comparado",
        "Precio_num_Nuevo": 1234.50,
    }])
    catalog = pd.DataFrame([{"IdArticulo": "SKU-DISTINTO", "Codigo_Barra": ".001-AB"}])
    mapped = apply_print_codes_from_catalog(changes, catalog)
    rows = [(mapped.loc[0, "Codigo_Impresion"], mapped.loc[0, "Descripcion"], mapped.loc[0, "Precio_num_Nuevo"], "12/07/26", mapped.loc[0, "IdArticulo"])]

    for size in ("Chica", "Mediana", "Gigante"):
        pdf_bytes, filename = generar_pdf_por_tamanio(size, rows)
        path = tmp_path / filename
        path.write_bytes(pdf_bytes)
        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        assert ".001-AB" in text
        assert "SKU-DISTINTO" not in text
