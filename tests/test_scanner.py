import pandas as pd

from cotyland_core import make_product_lookup, process_scan


def products():
    return pd.DataFrame([
        {"Codigo_Barra": "DL0026", "IdArticulo": "SKU-1", "Descripcion": "Uno", "Precio": "10", "Fecha": "12/07/26"},
        {"Codigo_Barra": "DL6000", "IdArticulo": "00123", "Descripcion": "Dos", "Precio": "20", "Fecha": "12/07/26"},
        {"Codigo_Barra": ".10200261", "IdArticulo": "QL.10234027", "Descripcion": "Tres", "Precio": "30", "Fecha": "12/07/26"},
        {"Codigo_Barra": "AB-123", "IdArticulo": "7791234567890", "Descripcion": "Cuatro", "Precio": "40", "Fecha": "12/07/26"},
    ])


def test_fifty_consecutive_scans_and_duplicates():
    lookup = make_product_lookup(products())
    queue, missing = [], []
    for _ in range(50):
        assert process_scan("DL0026", lookup, queue, missing)
    assert len(queue) == 50
    assert all(item["Codigo_Barra"] == "DL0026" for item in queue)
    assert missing == []


def test_missing_then_valid_continues():
    lookup = make_product_lookup(products())
    queue, missing = [], []
    assert not process_scan("NO-EXISTE", lookup, queue, missing)
    assert process_scan("DL6000", lookup, queue, missing)
    assert missing == ["NO-EXISTE"]
    assert [item["Codigo_Barra"] for item in queue] == ["DL6000"]


def test_codes_preserve_punctuation_letters_and_zeroes_and_search_both_fields():
    lookup = make_product_lookup(products())
    queue, missing = [], []
    for code in ["00123", ".10200261", "QL.10234027", "AB-123", "7791234567890"]:
        assert process_scan(code, lookup, queue, missing)
    assert [item["Codigo_Barra"] for item in queue] == ["DL6000", ".10200261", ".10200261", "AB-123", "AB-123"]


def test_scanner_function_keys_are_removed_without_breaking_code():
    lookup = make_product_lookup(products())
    queue, missing = [], []
    assert process_scan("F2DL0026F11", lookup, queue, missing)
    assert queue[0]["Codigo_Barra"] == "DL0026"

