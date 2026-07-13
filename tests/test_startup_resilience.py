from unittest.mock import patch

import pytest
import requests
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize(
    "secrets,network_effect",
    [
        ({}, AssertionError("No debe haber red sin secret")),
        ({"APPS_SCRIPT_URL": "https://script.google.com/valid"}, AssertionError("No debe haber red al arrancar")),
        ({"APPS_SCRIPT_URL": "https://invalid.example"}, requests.ConnectionError("URL inválida")),
        ({"APPS_SCRIPT_URL": "https://timeout.example"}, requests.Timeout("timeout simulado")),
    ],
    ids=["sin-secret", "url-valida", "url-invalida", "timeout"],
)
def test_app_renders_three_tabs_without_startup_network(secrets, network_effect):
    app = AppTest.from_file("app.py")
    app.secrets = secrets
    with patch("requests.get", side_effect=network_effect) as mocked_get:
        app.run(timeout=15)

    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "📱 Buscador Móvil",
        "🖨️ Generador de Etiquetas (CSV)",
        "📊 Comparador de Precios",
    ]
    assert app.title[0].value == "🎈 Cotyland - Panel Multiplataforma"
    mocked_get.assert_not_called()


def test_scanner_timeout_after_user_action_keeps_app_rendered():
    app = AppTest.from_file("app.py")
    app.secrets = {}
    app.run(timeout=15)

    with patch("requests.get", side_effect=requests.Timeout("timeout simulado")):
        app.text_input(key="scanner_input").set_value("DL0026").run(timeout=15)

    assert not app.exception
    assert len(app.tabs) == 3
    assert any("No se pudo cargar la base" in warning.value for warning in app.warning)
