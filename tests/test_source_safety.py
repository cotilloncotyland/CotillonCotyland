from pathlib import Path
import ast


def test_no_obsolete_streamlit_width_or_embedded_pdf():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "use_container_width" not in source
    assert source.count("components.html(") == 1
    assert "__cotylandKeyGuardHandler" in source
    assert "removeEventListener('keydown', previous, true)" in source
    assert "addEventListener('keydown', handler, true)" in source
    assert "__cotylandKeyGuard = true" not in source
    assert "scanner.focus({preventScroll: true})" in source
    assert "dispatchEvent(new Event('change'" not in source
    assert "new KeyboardEvent('keydown'" not in source
    assert "Abrir PDF para imprimir" in source
    assert "st.link_button" in source
    assert "popup.print()" not in source
    assert "window.open" not in source
    assert "base64" not in source
    assert "dispatchEvent" not in source
    assert "fetch(" not in source
    assert "Presioná Ctrl+P para imprimir" in source


def test_direct_print_does_not_regenerate_or_rerun():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "direct_print_control")
    function_source = ast.get_source_segment(source, function)
    assert "generar_pdf_por_tamanio" not in function_source
    assert "st.rerun" not in function_source
    assert "base64" not in function_source


def test_static_serving_is_enabled():
    config = (Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "enableStaticServing = true" in config
