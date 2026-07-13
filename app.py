from pathlib import Path
import ast


def test_no_obsolete_streamlit_width_or_embedded_pdf():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "use_container_width" not in source
    assert "st.components.v1.html" not in source
    assert "base64" not in source
    assert "dispatchEvent" not in source
    assert "fetch(" not in source
    assert "window.open(pdfUrl, '_blank')" in source
    assert "El navegador bloqueó la ventana" in source
    assert "st.iframe(" in source


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
