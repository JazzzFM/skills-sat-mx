"""Casos de la revisión de noviembre de 2026 para fiscal_mx.py."""
from datetime import date

import pytest


def test_inhabiles_por_reglas_del_cff_12_en_cualquier_anio(fiscal):
    # tercer lunes de marzo de 2029 es 19/03: el pago de febrero se recorre al martes 20
    assert fiscal.vencimiento_mensual(2029, 2) == date(2029, 3, 20)
    assert date(2031, 11, 17) in fiscal.inhabiles(2031)  # tercer lunes de noviembre


def test_recargos_de_anio_sin_tasa_se_marcan(fiscal):
    supuestos = set()
    fiscal.recargos_pct(date(2027, 1, 18), date(2027, 6, 17), supuestos)
    assert supuestos == {(2027, "2026")}


def test_provisionales_marca_recargos_supuestos(fiscal):
    meses = fiscal.provisionales([{"fecha": "2026-12-10", "usd": "", "mxn": "50000", "nota": ""}], {},
                                 hoy=date(2027, 3, 1), pago=date(2027, 6, 30))
    assert meses[0]["supuestos"] == {(2027, "2026")}


def test_tipo_de_cambio_faltante_usa_el_ultimo_publicado(fiscal):
    meses = fiscal.provisionales([{"fecha": "2026-05-16", "usd": "100", "mxn": "", "nota": ""}],
                                 {"2026-05-15": 17.42}, hoy=date(2026, 11, 26), pago=date(2026, 11, 26))
    det = meses[0]["detalle"][0]
    assert det["tc"] == 17.42 and det["tc_fecha"] == "2026-05-15"


def test_plazos_de_anio_sin_tasas_falla_explicito(fiscal):
    with pytest.raises(KeyError):
        fiscal.tasa_plazos(12, 2031)


def test_cli_resico_sin_xml(fiscal, capsys):
    fiscal.main(["resico", "--mes", "2026-10", "--ingresos", "48000", "--retenido-isr", "625",
                 "--iva-trasladado", "7680", "--iva-acreditable", "2400", "--iva-retenido", "5333.33"])
    out = capsys.readouterr().out
    assert "1.10%" in out and "528.00" in out and "a favor 97.00" in out and "a favor 53.33" in out
    assert "2026-11-17" in out


def test_cli_vigencia(fiscal, capsys):
    fiscal.main(["vigencia", "--ejercicio", "2026"])
    assert "FALTA" not in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        fiscal.main(["vigencia", "--ejercicio", "2027"])
    assert e.value.code == 1
