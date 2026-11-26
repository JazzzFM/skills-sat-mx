import csv

import pytest

# Formato real de Banxico (tipCamIHAction.do): tablas separadas por columna, mismo orden de filas.
HTML = """<html><body>
<table><tr><td>Fecha</td></tr><tr><td>26/10/2026</td></tr><tr><td>25/10/2026</td></tr><tr><td>23/10/2026</td></tr></table>
<table><tr><td>FIX</td></tr><tr><td>18.5798</td></tr><tr><td>N/E</td></tr><tr><td>18.6670</td></tr></table>
<table><tr><td>Publicación DOF</td></tr><tr><td>18.6670</td></tr><tr><td>N/E</td></tr><tr><td>18.7005</td></tr></table>
<table><tr><td>Para pagos</td></tr><tr><td>18.7005</td></tr><tr><td>18.7005</td></tr><tr><td>18.6425</td></tr></table>
</body></html>"""


def test_parsear_tablas_por_columna(tipo_cambio):
    filas = tipo_cambio.parsear(HTML)
    assert filas[0] == {"fecha": "2026-10-23", "fix": "18.6670", "dof": "18.7005", "pagos": "18.6425"}
    assert filas[1]["fix"] == "" and filas[1]["pagos"] == "18.7005"  # fin de semana: sin FIX, sí "para pagos"
    assert [f["fecha"] for f in filas] == ["2026-10-23", "2026-10-25", "2026-10-26"]


def test_tc_fiscal_usa_para_pagos_y_cae_al_ultimo_disponible(tipo_cambio):
    filas = tipo_cambio.parsear(HTML)
    assert tipo_cambio.tc_fiscal("2026-10-26", filas) == pytest.approx(18.7005)
    assert tipo_cambio.tc_fiscal("2026-10-24", filas) == pytest.approx(18.6425)  # sin dato: el anterior publicado
    with pytest.raises(KeyError):
        tipo_cambio.tc_fiscal("2020-01-01", filas)


def test_escribir_csv(tipo_cambio, tmp_path):
    ruta = tmp_path / "tc.csv"
    tipo_cambio.escribir_csv(tipo_cambio.parsear(HTML), ruta)
    filas = list(csv.DictReader(open(ruta)))
    assert filas[0].keys() == {"fecha", "fix", "dof", "pagos"} and len(filas) == 3
