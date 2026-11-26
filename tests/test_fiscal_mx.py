from datetime import date

import pytest


def test_tarifas_consistentes_renglon_a_renglon(fiscal):
    # La cuota fija de cada renglón debe salir del renglón anterior (tolerancia de redondeo oficial)
    for tipo in ("mensual", "anual"):
        for anio in fiscal.ejercicios_disponibles(tipo):
            filas = fiscal.tarifa(tipo, anio)
            for (li, cuota, tasa), (li2, cuota2, _) in zip(filas, filas[1:]):
                assert cuota + (li2 - li) * tasa == pytest.approx(cuota2, abs=0.06), (tipo, anio, li2)


def test_isr_anual_2022_por_tarifa(fiscal):
    assert fiscal.isr(400000.00, fiscal.tarifa("anual", 2022)) == pytest.approx(69790.67, abs=0.01)


def test_isr_anual_2025_y_mensual_2026(fiscal):
    assert fiscal.isr(600000.00, fiscal.tarifa("anual", 2025)) == pytest.approx(113603.94, abs=0.01)
    assert fiscal.isr(50000.00, fiscal.tarifa("mensual", 2026)) == pytest.approx(9107.82, abs=0.01)


def test_tarifa_de_ejercicio_inexistente_falla_explicito(fiscal):
    with pytest.raises(KeyError):
        fiscal.tarifa("mensual", 1999)


@pytest.mark.parametrize("anio,mes,esperado", [
    (2025, 10, date(2025, 11, 18)),   # 17/11/2025 inhábil (tercer lunes de noviembre)
    (2025, 12, date(2026, 1, 19)),    # 17/01/2026 cae en sábado
    (2026, 9, date(2026, 10, 19)),    # 17/10/2026 cae en sábado
    (2026, 10, date(2026, 11, 17)),
])
def test_vencimiento_dia_17_recorrido(fiscal, anio, mes, esperado):
    assert fiscal.vencimiento_mensual(anio, mes) == esperado


def test_recargos_por_mes_o_fraccion_con_tasa_de_cada_anio(fiscal):
    # 3 meses de 2025 a 1.47% + 10 de 2026 a 2.07%
    assert fiscal.recargos_pct(date(2025, 10, 17), date(2026, 11, 17)) == pytest.approx(0.2511, abs=1e-6)
    assert fiscal.recargos_pct(date(2026, 10, 19), date(2026, 11, 17)) == pytest.approx(0.0207, abs=1e-6)
    assert fiscal.recargos_pct(date(2026, 11, 17), date(2026, 11, 17)) == 0


def test_parcialidad_amortiza_el_saldo(fiscal):
    cuota = fiscal.parcialidad(100000, 24, 0.0163)
    saldo = 100000
    for _ in range(24):
        saldo = saldo * 1.0163 - cuota
    assert saldo == pytest.approx(0, abs=0.01)


def test_provisionales_usa_tipo_de_cambio_del_dia_y_tarifa_del_anio(fiscal):
    depositos = [
        {"fecha": "2025-12-15", "usd": "3500.00", "mxn": "", "nota": ""},
        {"fecha": "2025-09-30", "usd": "", "mxn": "20000", "nota": "solo pesos"},
    ]
    tc = {"2025-12-15": 18.25}
    meses = fiscal.provisionales(depositos, tc, hoy=date(2026, 10, 26), pago=date(2026, 11, 17))
    dic = next(m for m in meses if m["mes"] == "2025-12")
    assert dic["detalle"][0]["tc"] == 18.25
    assert dic["mxn"] == pytest.approx(63875.00, abs=0.01)
    assert dic["isr"] == pytest.approx(13629.49, abs=0.01)
    assert dic["vence"] == date(2026, 1, 19) and dic["vencido"]
    assert dic["recargos"] == pytest.approx(13629.49 * fiscal.recargos_pct(date(2026, 1, 19), date(2026, 11, 17)), abs=0.01)
    sep = next(m for m in meses if m["mes"] == "2025-09")
    assert sep["mxn"] == 20000 and sep["detalle"][0]["tc"] is None
    assert sep["isr"] == pytest.approx(2604.00, abs=0.01)


def test_provisionales_suma_depositos_del_mismo_mes(fiscal):
    depositos = [{"fecha": "2026-03-01", "usd": "", "mxn": "30000", "nota": ""},
                 {"fecha": "2026-03-20", "usd": "", "mxn": "30000", "nota": ""}]
    meses = fiscal.provisionales(depositos, {}, hoy=date(2026, 10, 26), pago=date(2026, 11, 17))
    assert len(meses) == 1 and len(meses[0]["detalle"]) == 2
    assert meses[0]["isr"] == pytest.approx(fiscal.isr(60000, fiscal.tarifa("mensual", 2026)), abs=0.01)


def test_mes_no_vencido_no_genera_recargos(fiscal):
    meses = fiscal.provisionales([{"fecha": "2026-10-16", "usd": "", "mxn": "65000", "nota": ""}], {},
                                 hoy=date(2026, 10, 26), pago=date(2026, 11, 17))
    assert not meses[0]["vencido"] and meses[0]["recargos"] == 0


@pytest.mark.parametrize("vence,solicitud,esperado", [
    (date(2025, 10, 17), date(2026, 11, 1), True),    # venció en 2025, más de 6 meses antes
    (date(2026, 1, 19), date(2026, 11, 1), False),    # año de calendario en curso
    (date(2026, 4, 30), date(2026, 11, 1), False),    # anual 2025: vence en el año en curso
    (date(2026, 10, 19), date(2027, 1, 15), False),   # dentro de los 6 meses anteriores
    (date(2026, 6, 17), date(2027, 1, 15), True),
])
def test_elegible_pago_a_plazos_cff_66a_vi(fiscal, vence, solicitud, esperado):
    assert fiscal.elegible_plazos(vence, solicitud) is esperado


def test_provisionales_marca_elegibilidad(fiscal):
    deps = [{"fecha": "2025-10-14", "usd": "", "mxn": "50000", "nota": ""},
            {"fecha": "2026-01-15", "usd": "", "mxn": "50000", "nota": ""}]
    meses = fiscal.provisionales(deps, {}, hoy=date(2026, 10, 26), pago=date(2026, 11, 17))
    assert [fiscal.elegible_plazos(m["vence"], date(2026, 11, 17)) for m in meses] == [True, False]


def test_tipo_de_cambio_faltante_falla_explicito(fiscal):
    with pytest.raises(KeyError):
        fiscal.provisionales([{"fecha": "2026-01-15", "usd": "100", "mxn": "", "nota": ""}], {},
                             hoy=date(2026, 10, 26), pago=date(2026, 11, 17))


def test_cli_anual(fiscal, capsys):
    fiscal.main(["anual", "--ejercicio", "2025", "--gravado", "600000", "--retenido", "130000"])
    salida = capsys.readouterr().out
    assert "113,603.94" in salida and "16,396.06" in salida
