from pathlib import Path


def test_no_obsolete_streamlit_width_or_embedded_pdf():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "use_container_width" not in source
    assert "st.components.v1.html" not in source
    assert "base64" not in source
    assert "dispatchEvent" not in source
    assert "fetch(" not in source
