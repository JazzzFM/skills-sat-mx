import pytest


def _octubre(cfdi, xmls, tmp_path):
    d = xmls.octubre_resico(tmp_path / "x")
    cfdis, avisos = cfdi.leer_varios(sorted(d.glob("*.xml")))
    return cfdis, avisos


def test_lee_cfdi_con_bom_y_deduplica_por_uuid(cfdi, xmls, tmp_path):
    cfdis, avisos = _octubre(cfdi, xmls, tmp_path)
    assert len(cfdis) == 6
    assert any("duplicado" in a for a in avisos)
    pue = next(c for c in cfdis if c["uuid"].endswith("001"))
    assert pue["tipo"] == "I" and pue["metodo"] == "PUE"
    assert pue["retenciones"]["001"] == pytest.approx(375)
    assert pue["traslados"]["002"] == pytest.approx(4800)


def test_resico_octubre_tasa_unica_retenciones_y_complemento(cfdi, xmls, tmp_path):
    cfdis, _ = _octubre(cfdi, xmls, tmp_path)
    meses, sin_comp, avisos = cfdi.resico(cfdis, xmls.RFC_PF)
    assert list(meses) == ["2026-10"]  # la PPD de septiembre no cuenta hasta su pago
    m = meses["2026-10"]
    assert m["cobrado"] == pytest.approx(50000)
    assert m["descuentos"] == pytest.approx(2000)
    assert m["ingresos"] == pytest.approx(48000)
    assert m["tasa"] == pytest.approx(0.011)          # una sola tasa sobre todo, no marginal
    assert m["isr"] == pytest.approx(528)
    assert m["isr_cargo"] == pytest.approx(-97)       # retenciones de 1.25% superan el ISR: saldo a favor
    assert m["iva_trasladado"] == pytest.approx(7680)
    assert m["iva_acreditable"] == pytest.approx(2400)  # laptop sí, consulta médica D01 no
    assert m["iva_cargo"] == pytest.approx(7680 - 2400 - 5333.33)
    assert str(m["vence"]) == "2026-11-17"
    assert not sin_comp
    assert any("después del límite 2026-11-05" in a for a in avisos)
    assert any("uso D01" in a for a in avisos)


def test_resico_ppd_sin_complemento_y_cancelados(cfdi, xmls, tmp_path):
    cfdis, _ = _octubre(cfdi, xmls, tmp_path)
    sin_rep = [c for c in cfdis if c["tipo"] != "P"]
    meses, sin_comp, _ = cfdi.resico(sin_rep, xmls.RFC_PF, excluir=["AAAAAAAA-0000-0000-0000-000000000004"])
    assert [p["uuid"][-3:] for p in sin_comp] == ["002"]
    assert meses["2026-10"]["ingresos"] == pytest.approx(30000)  # sin pago ni nota de crédito excluida


@pytest.mark.parametrize("ingreso,tasa", [(25000, 0.01), (25000.01, 0.011), (83333.33, 0.015), (208333.34, 0.025)])
def test_tasa_resico_por_tramo(cfdi, ingreso, tasa):
    assert cfdi.tasa_resico(ingreso, 2026) == pytest.approx(tasa)


def test_limite_complemento_dia_5_natural(cfdi):
    assert str(cfdi.limite_complemento("2026-12-28")) == "2027-01-05"


@pytest.mark.parametrize("uso,regimen,ok", [("D01", "605", True), ("D01", "626", False), ("G03", "626", True),
                                            ("G03", "605", False), ("S01", "605", True), ("CN01", "626", False)])
def test_compatibilidad_uso_regimen(cfdi, uso, regimen, ok):
    admitidos = cfdi.regimenes_admitidos(uso)
    assert (admitidos is None or regimen in admitidos) is ok


def test_verificar_receptor(cfdi, xmls, tmp_path):
    cfdis, _ = _octubre(cfdi, xmls, tmp_path)
    laptop = next(c for c in cfdis if c["uuid"].endswith("005"))
    esperado = {"rfc": xmls.RFC_PF, "nombre": "Ana López Pérez", "cp": xmls.CP_PF, "regimen": "626", "uso": "I04"}
    problemas, notas = cfdi.verificar(laptop, esperado)
    assert problemas == [] and notas == ["el nombre solo difiere en mayúsculas, acentos o espacios: 'ANA LOPEZ PEREZ'"]
    assert any("régimen" in p for p in cfdi.verificar(laptop, {**esperado, "nombre": "", "regimen": "605"})[0])
    assert any("RFC" in p for p in cfdi.verificar(laptop, {**esperado, "rfc": "XAXX010101000"})[0])


def test_mascara_rfc(cfdi):
    assert cfdi.mascara_rfc("LOPA900101AB1") == "LOPA******AB1"
    assert cfdi.mascara_rfc("GAS010101AA1") == "GAS010101AA1"   # persona moral: dato público del ticket


def test_nomina_suma_por_patron_y_tope_de_aguinaldo(cfdi, xmls, tmp_path):
    rec = (xmls.RFC_PF, xmls.NOMBRE_PF, xmls.CP_PF, "605", "CN01")
    for i, (fecha, ag) in enumerate([("2026-11-30", 0.0), ("2026-12-15", 4000.0)]):
        xmls.escribir(tmp_path / f"n{i}.xml", xmls.comprobante(
            f"BBBBBBBB-0000-0000-0000-00000000000{i}", "N", fecha, 20000 + ag, 17000, (xmls.RFC_PATRON, "PATRON SA", "601"),
            rec, metodo="PUE", forma="99", complemento=xmls.nomina(fecha, 20000, ag, 3000, aguinaldo_exento=ag)))
    cfdis, _ = cfdi.leer_varios(sorted(tmp_path.glob("n*.xml")))
    filas, _, alertas = cfdi.nomina(cfdis)
    f = filas[("2026", xmls.RFC_PATRON, "PATRON SA")]
    assert f["recibos"] == 2 and f["gravado"] == pytest.approx(40000) and f["isr"] == pytest.approx(6000)
    assert f["aguinaldo_exento"] == pytest.approx(4000)   # rebasa 30 UMA 2026 = 3,519.30
    assert any("aguinaldo" in x and "rebasa" in x for x in alertas)


def test_deducciones_detecta_regimen_efectivo_y_ejercicio(cfdi, xmls, tmp_path):
    def fac(n, regimen, forma, fecha, uso="D01"):
        return xmls.escribir(tmp_path / f"d{n}.xml", xmls.comprobante(
            f"CCCCCCCC-0000-0000-0000-00000000000{n}", "I", fecha, 1000, 1000, ("MEDA800101AB1", "DRA MEDICA", "612"),
            (xmls.RFC_PF, xmls.NOMBRE_PF, xmls.CP_PF, regimen, uso), forma=forma))
    fac(1, "605", "04", "2026-03-01")
    fac(2, "626", "04", "2026-03-02")
    fac(3, "605", "01", "2026-03-03")
    fac(4, "605", "28", "2025-12-30")
    fac(5, "605", "03", "2026-08-01", uso="D10")
    cfdis, _ = cfdi.leer_varios(sorted(tmp_path.glob("d*.xml")))
    revisadas, _ = cfdi.deducciones(cfdis, xmls.RFC_PF, 2026)
    res = {c["uuid"][-1]: p for c, p in revisadas}
    assert res["1"] == []
    assert "605" in res["2"][0]
    assert "efectivo" in res["3"][0]
    assert "fuera del ejercicio" in res["4"][0]
    assert "complemento de instituciones educativas" in res["5"][0]
