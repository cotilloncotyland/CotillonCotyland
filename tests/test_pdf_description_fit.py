from reportlab.pdfbase import pdfmetrics

from cotyland_core import fit_description, generar_pdf_por_tamanio, wrap_text_to_width


LONG_DESCRIPTION = "GALLETITAS OREO X118GRS ETITAS/TURRONES/POCHOCLOS/BARRITAS/VARIOS"


def test_long_separator_token_is_split_by_real_reportlab_width():
    max_width = 115
    lines = wrap_text_to_width(LONG_DESCRIPTION, "Helvetica-Bold", 12, max_width)

    assert len(lines) > 1
    assert all(pdfmetrics.stringWidth(line, "Helvetica-Bold", 12) <= max_width for line in lines)


def test_truncated_description_adds_ellipsis_inside_width():
    max_width = 90
    font_size, lines = fit_description(LONG_DESCRIPTION * 4, max_width, 10, 1, 10, 7)

    assert len(lines) == 1
    assert lines[0].endswith("...")
    assert pdfmetrics.stringWidth(lines[0], "Helvetica-Bold", font_size) <= max_width


def test_separator_description_generates_all_three_pdf_sizes():
    product = [("7622201735296", LONG_DESCRIPTION, "2950,35", "13/07/26", "ART-OREO")]

    for size in ("Chica", "Mediana", "Gigante"):
        pdf, name = generar_pdf_por_tamanio(size, product)
        assert pdf.startswith(b"%PDF")
        assert name.endswith(".pdf")
