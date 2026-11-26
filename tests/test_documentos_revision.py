"""Casos de la revisión de noviembre de 2026 para documentos.py."""
import shutil

import pytest

pytestmark = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="requiere pdftotext (poppler)")


def test_pdf_ilegible_o_sin_texto_se_avisa_y_no_cuenta(documentos, fx, tmp_path):
    fabrica_pdf = __import__("importlib").import_module("fabrica").pdf
    dañado = tmp_path / "danado.pdf"
    dañado.write_bytes(b"%PDF-1.4 esto no es un pdf")
    vacio = tmp_path / "escaneo.pdf"
    vacio.write_bytes(fabrica_pdf([]))
    bueno = fx / "estados_desordenados" / "EstadodeCuenta.pdf"
    avisos = []
    deps = documentos.depositos([dañado, vacio, bueno], "ACME LABS", avisos)
    assert len(deps) == 1
    assert any("no pudo leerlo" in a for a in avisos) and any("no tiene texto" in a for a in avisos)


def test_pdf_de_otro_banco_se_reporta(documentos, fx):
    avisos = []
    documentos.depositos([fx / "estados_desordenados" / "Finanzas_Legal" / "Factura_Oct 2025.pdf"], "ACME", avisos)
    assert any("no se reconoció" in a for a in avisos)


def test_salida_dentro_del_repo_fuera_de_personal_se_rechaza(documentos, fx):
    destino = documentos.rutas.RAIZ / "depositos-prueba.csv"
    with pytest.raises(SystemExit) as e:
        documentos.main(["depositos", "--pagador", "ACME", "--salida", str(destino),
                         str(fx / "estados_desordenados" / "EstadodeCuenta.pdf")])
    assert e.value.code == 1 and not destino.exists()


def test_fuente_de_depositos_sale_enmascarada(documentos, fx, tmp_path, capsys):
    origen = fx / "estados_desordenados" / "EstadodeCuenta.pdf"
    copia = tmp_path / "estado_012180001234567890.pdf"
    copia.write_bytes(origen.read_bytes())
    salida = tmp_path / "dep.csv"
    documentos.main(["depositos", "--pagador", "ACME", "--salida", str(salida), str(copia)])
    assert "012180001234567890" not in salida.read_text(encoding="utf-8")
    assert "012180001234567890" not in capsys.readouterr().out


@pytest.mark.parametrize("entrada,esperado", [
    ("estado_012180001234567890.pdf", "estado_####7890.pdf"),
    ("Anual.LOPA900101AB1.2024.pdf", "Anual.LOPA******AB1.2024.pdf"),
    ("2026-01-04_banamex-micuenta_estado-cuenta.pdf", "2026-01-04_banamex-micuenta_estado-cuenta.pdf"),
    ("curp_LOPA900101MDFPRN01.pdf", "curp_[CURP].pdf"),
])
def test_mascara_en_nombres_de_archivo(documentos, entrada, esperado):
    assert documentos.mascara(entrada) == esperado
