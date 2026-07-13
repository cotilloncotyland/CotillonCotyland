from pathlib import Path

from cotyland_core import compare_price_lists


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "viejo.csv"
NEW = ROOT / "nuevo.csv"
EXPECTED = {"coincidencias": 131037, "cambios": 294, "aumentos": 290, "bajas": 4}


def assert_expected(stats):
    assert {key: stats[key] for key in EXPECTED} == EXPECTED


def test_real_files_exact_counts():
    assert OLD.exists() and NEW.exists(), "Copiar viejo.csv y nuevo.csv junto a app.py antes de ejecutar la prueba."
    changes, stats = compare_price_lists(OLD, NEW)
    assert_expected(stats)
    assert len(changes) == 294
    assert list(changes["Descripcion"].str.casefold()) == sorted(changes["Descripcion"].str.casefold())


def test_real_files_reverse_order_same_result():
    changes, stats = compare_price_lists(NEW, OLD)
    assert_expected(stats)
    assert set(changes["Movimiento"]) == {"Aumento", "Baja"}

