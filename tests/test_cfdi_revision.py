"""Casos de la revisión de noviembre de 2026: cada prueba reproduce un hallazgo verificado."""
import json

import pytest

U = "CCCCCCCC-0000-0000-0000-0000000000{:02d}".format


@pytest.fixture()
def base(xmls):
    return {
        "yo": xmls.YO_RESICO,
        "cliente": xmls.RECEPTOR_CLIENTE,
        "rec_pago": (xmls.RFC_CLIENTE, "ESCUELA KEMPER URGATE", "26015", "601", "CP01"),
        "proveedor": ("PRO010101AA1", "PROVEEDOR SA DE CV", "601"),
        "mi_receptor": lambda reg, uso: (xmls.RFC_PF, xmls.NOMBRE_PF, xmls.CP_PF, reg, uso),
    }


def _leer(cfdi, d):
    cfdis, avisos = cfdi.leer_varios(sorted(d.glob("*.xml")))
    return cfdis, avisos


def test_pago_que_liquida_documento_no_objeto_de_iva_cuenta_completo(cfdi, xmls, base, tmp_path):
    xmls.escribir(tmp_path / "ppd1.xml", xmls.comprobante(U(1), "I", "2026-09-10", 1000, 1160, base["yo"], base["cliente"],
                                                         metodo="PPD", forma="99", iva=160))
    xmls.escribir(tmp_path / "ppd2.xml", xmls.comprobante(U(2), "I", "2026-09-11", 500, 500, base["yo"], base["cliente"],
                                                         metodo="PPD", forma="99"))
    xmls.escribir(tmp_path / "rep.xml", xmls.comprobante(U(3), "P", "2026-10-16", 0, 0, base["yo"], base["rec_pago"],
                  metodo="", forma="", complemento=xmls.pagos20("2026-10-15", [
                      {"uuid": U(1), "pagado": 1160, "base": 1000, "iva": 160},
                      {"uuid": U(2), "pagado": 500, "objeto": "01"}])))
    meses, _, _ = cfdi.resico(_leer(cfdi, tmp_path)[0], xmls.RFC_PF)
    assert meses["2026-10"]["cobrado"] == pytest.approx(1500)
    assert meses["2026-10"]["iva_trasladado"] == pytest.approx(160)


def test_iva_de_pago_recibido_solo_se_acredita_si_la_factura_es_gasto(cfdi, xmls, base, tmp_path):
    prov = base["proveedor"]
    xmls.escribir(tmp_path / "medico.xml", xmls.comprobante(U(4), "I", "2026-10-01", 10000, 11600, prov,
                  base["mi_receptor"]("605", "D01"), metodo="PPD", forma="99", iva=1600))
    xmls.escribir(tmp_path / "insumo.xml", xmls.comprobante(U(5), "I", "2026-10-01", 1000, 1160, prov,
                  base["mi_receptor"]("626", "G03"), metodo="PPD", forma="99", iva=160))
    xmls.escribir(tmp_path / "pago.xml", xmls.comprobante(U(6), "P", "2026-10-21", 0, 0, prov,
                  base["mi_receptor"]("626", "CP01"), metodo="", forma="", complemento=xmls.pagos20("2026-10-20", [
                      {"uuid": U(4), "pagado": 11600, "base": 10000, "iva": 1600},
                      {"uuid": U(5), "pagado": 1160, "base": 1000, "iva": 160},
                      {"uuid": U(9), "pagado": 116, "base": 100, "iva": 16}])))
    meses, _, avisos = cfdi.resico(_leer(cfdi, tmp_path)[0], xmls.RFC_PF)
    assert meses["2026-10"]["iva_acreditable"] == pytest.approx(160)
    assert any("D01" in a for a in avisos)
    assert any("no está" in a for a in avisos)  # pago de una factura que no se descargó


def test_nota_de_credito_resta_tambien_sus_retenciones(cfdi, xmls, base, tmp_path):
    xmls.escribir(tmp_path / "pue.xml", xmls.comprobante(U(7), "I", "2026-10-03", 30000, 31225, base["yo"],
                  base["cliente"], iva=4800, ret_isr=375, ret_iva=3200))
    xmls.escribir(tmp_path / "nc.xml", xmls.comprobante(U(8), "E", "2026-10-20", 10000, 10408.33, base["yo"],
                  base["cliente"], iva=1600, ret_isr=125, ret_iva=1066.67))
    m = cfdi.resico(_leer(cfdi, tmp_path)[0], xmls.RFC_PF)[0]["2026-10"]
    assert m["ret_isr"] == pytest.approx(250)
    assert m["ret_iva"] == pytest.approx(2133.33)


def test_factura_global_va_al_periodo_que_ampara(cfdi, xmls, base, tmp_path):
    publico = ("XAXX010101000", "PUBLICO EN GENERAL", "06700", "616", "S01")
    xmls.escribir(tmp_path / "global.xml", xmls.comprobante(U(10), "I", "2026-11-01", 40000, 46400, base["yo"], publico,
                  iva=6400, informacion_global=("04", "10", "2026")))
    meses, _, avisos = cfdi.resico(_leer(cfdi, tmp_path)[0], xmls.RFC_PF)
    assert list(meses) == ["2026-10"] and meses["2026-10"]["cobrado"] == pytest.approx(40000)
    assert any("global" in a for a in avisos)


def test_retenciones_2_0_se_suman_si_la_factura_no_las_expresa(cfdi, xmls, base, tmp_path):
    xmls.escribir(tmp_path / "pue.xml", xmls.comprobante(U(11), "I", "2026-10-03", 30000, 34800, base["yo"],
                  base["cliente"], iva=4800))
    xmls.escribir(tmp_path / "ret.xml", xmls.retenciones20(U(12), "2026-11-02", (xmls.RFC_CLIENTE, "ESCUELA KEMPER URGATE"),
                  xmls.RFC_PF, 10, 10, 2026, isr=375, iva=3200, base=30000))
    cfdis, avisos = _leer(cfdi, tmp_path)
    assert [c["tipo"] for c in cfdis] == ["I", "R"] and not any("ignorado" in a for a in avisos)
    m = cfdi.resico(cfdis, xmls.RFC_PF)[0]["2026-10"]
    assert m["ret_isr"] == pytest.approx(375) and m["ret_iva"] == pytest.approx(3200)


def test_retenciones_2_0_no_se_cuentan_dos_veces(cfdi, xmls, base, tmp_path):
    xmls.escribir(tmp_path / "pue.xml", xmls.comprobante(U(13), "I", "2026-10-03", 30000, 31225, base["yo"],
                  base["cliente"], iva=4800, ret_isr=375, ret_iva=3200))
    xmls.escribir(tmp_path / "ret.xml", xmls.retenciones20(U(14), "2026-11-02", (xmls.RFC_CLIENTE, "ESCUELA KEMPER URGATE"),
                  xmls.RFC_PF, 10, 10, 2026, isr=375, iva=3200, base=30000))
    meses, _, avisos = cfdi.resico(_leer(cfdi, tmp_path)[0], xmls.RFC_PF)
    assert meses["2026-10"]["ret_isr"] == pytest.approx(375)
    assert any("ya está expresada" in a for a in avisos)


@pytest.mark.parametrize("cambio,motivo", [
    ('<!DOCTYPE x [<!ENTITY t "300000.00">]>', "DOCTYPE"),
    ("", "fecha"),
])
def test_xml_hostil_o_malformado_se_ignora(cfdi, xmls, base, tmp_path, cambio, motivo):
    texto = xmls.comprobante(U(15), "I", "2026-10-03", 1000, 1160, base["yo"], base["cliente"], iva=160,
                             antes_raiz=cambio)
    if motivo == "fecha":
        texto = texto.replace('Fecha="2026-10-03T12:00:00"', 'Fecha="2026-13-01T12:00:00"')
    xmls.escribir(tmp_path / "x.xml", texto)
    cfdis, avisos = _leer(cfdi, tmp_path)
    assert cfdis == [] and any("ignorado" in a and motivo.lower() in a.lower() for a in avisos)


def test_cfdi_sin_timbre_no_cuenta(cfdi, xmls, base, tmp_path):
    for n in ("a", "b"):
        xmls.escribir(tmp_path / f"{n}.xml", xmls.comprobante("", "I", "2026-10-03", 30000, 34800, base["yo"],
                                                             base["cliente"], iva=4800))
    cfdis, avisos = _leer(cfdi, tmp_path)
    assert cfdis == [] and any("sin timbre" in a for a in avisos)


def test_verificar_diferencia_de_forma_en_el_nombre_no_bloquea(cfdi, xmls, base, tmp_path):
    xmls.escribir(tmp_path / "f.xml", xmls.comprobante(U(16), "I", "2026-10-03", 100, 116, base["proveedor"],
                  base["mi_receptor"]("626", "G03"), iva=16))
    c = _leer(cfdi, tmp_path)[0][0]
    problemas, notas = cfdi.verificar(c, {"rfc": xmls.RFC_PF, "nombre": "Ana López Pérez", "cp": xmls.CP_PF,
                                          "regimen": "626", "uso": "G03"})
    assert problemas == [] and notas


def test_verificar_sin_cfdi_validos_sale_con_2(cfdi, tmp_path):
    (tmp_path / "error.xml").write_text("<html>Error 500</html>", encoding="utf-8")
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"receptor": {"rfc": "LOPA900101AB1"}}), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cfdi.main(["verificar", "--config", str(cfg), str(tmp_path / "error.xml")])
    assert e.value.code == 2


def test_salida_enmascara_el_rfc_del_emisor_persona_fisica(cfdi, xmls, base, tmp_path, capsys):
    medico = ("MEDA800101AB1", "", "612")
    xmls.escribir(tmp_path / "m.xml", xmls.comprobante(U(17), "I", "2026-10-03", 1000, 1000, medico,
                  base["mi_receptor"]("605", "D01"), forma="04"))
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"receptor": {"rfc": xmls.RFC_PF}}), encoding="utf-8")
    cfdi.main(["verificar", "--config", str(cfg), str(tmp_path / "m.xml")])
    cfdi.main(["deducciones", "--rfc", xmls.RFC_PF, "--ejercicio", "2026", str(tmp_path / "m.xml")])
    salida = capsys.readouterr().out
    assert "MEDA800101AB1" not in salida and "MEDA******AB1" in salida


def test_ppd_con_saldo_insoluto_se_reporta_pendiente(cfdi, xmls, base, tmp_path):
    xmls.escribir(tmp_path / "ppd.xml", xmls.comprobante(U(18), "I", "2026-09-01", 10000, 11600, base["yo"],
                  base["cliente"], metodo="PPD", forma="99", iva=1600))
    xmls.escribir(tmp_path / "rep.xml", xmls.comprobante(U(19), "P", "2026-10-02", 0, 0, base["yo"], base["rec_pago"],
                  metodo="", forma="", complemento=xmls.pago20("2026-10-01", 5800, 5000, 800, 0, 0, U(18),
                                                                saldo_insoluto=5800)))
    _, pendientes, _ = cfdi.resico(_leer(cfdi, tmp_path)[0], xmls.RFC_PF)
    assert [(p["uuid"], p["saldo"]) for p in pendientes] == [(U(18), pytest.approx(5800))]


def test_sustitucion_excluye_la_factura_original(cfdi, xmls, base, tmp_path):
    xmls.escribir(tmp_path / "orig.xml", xmls.comprobante(U(20), "I", "2026-10-05", 30000, 34800, base["yo"],
                  base["cliente"], iva=4800))
    xmls.escribir(tmp_path / "sust.xml", xmls.comprobante(U(21), "I", "2026-10-06", 30000, 34800, base["yo"],
                  base["cliente"], iva=4800, relacionados=[("04", [U(20)])]))
    meses, _, avisos = cfdi.resico(_leer(cfdi, tmp_path)[0], xmls.RFC_PF)
    assert meses["2026-10"]["cobrado"] == pytest.approx(30000)
    assert any("sustituida" in a for a in avisos)


def test_mes_por_encima_del_tope_no_truena(cfdi, xmls, base, tmp_path):
    xmls.escribir(tmp_path / "g.xml", xmls.comprobante(U(22), "I", "2026-10-03", 4_000_000, 4_640_000, base["yo"],
                  base["cliente"], iva=640_000))
    meses, _, avisos = cfdi.resico(_leer(cfdi, tmp_path)[0], xmls.RFC_PF)
    assert meses["2026-10"]["tasa"] == pytest.approx(0.025)
    assert any("tope" in a for a in avisos)


def test_ejercicio_sin_tabla_resico_no_se_calcula_en_silencio(cfdi, xmls, base, tmp_path):
    xmls.escribir(tmp_path / "f.xml", xmls.comprobante(U(23), "I", "2031-01-10", 1000, 1160, base["yo"],
                  base["cliente"], iva=160))
    meses, _, avisos = cfdi.resico(_leer(cfdi, tmp_path)[0], xmls.RFC_PF)
    assert meses["2031-01"]["tasa"] is None and meses["2031-01"]["isr"] is None
    assert any("2031" in a and "tabla" in a for a in avisos)


def _recibo(xmls, d, n, fecha, patron, gravado, isr, **kw):
    rec = (xmls.RFC_PF, xmls.NOMBRE_PF, xmls.CP_PF, "605", "CN01")
    exento = kw.get("aguinaldo_exento", 0.0)
    xmls.escribir(d / f"n{n}.xml", xmls.comprobante(U(30 + n), "N", fecha, gravado + exento + kw.get("indemnizacion", 0),
                  gravado, patron, rec, forma="99", complemento=xmls.nomina(fecha, gravado, exento, isr, **kw)))


def test_nomina_separa_indemnizacion_y_cuenta_ingresos_totales(cfdi, xmls, tmp_path):
    patron = (xmls.RFC_PATRON, "PATRON SA", "601")
    _recibo(xmls, tmp_path, 1, "2026-06-30", patron, 370000, 70000, aguinaldo_exento=3000.0)
    _recibo(xmls, tmp_path, 2, "2026-07-15", patron, 20000, 4000, indemnizacion=100000.0)
    filas, por_anio, alertas = cfdi.nomina(_leer(cfdi, tmp_path)[0])
    t = por_anio["2026"]
    assert t["gravado_acumulable"] == pytest.approx(390000)   # sin la indemnización (art. 95)
    assert t["separacion"] == pytest.approx(100000)
    assert t["ingresos_totales"] == pytest.approx(493000)
    assert any("art. 95" in a for a in alertas)


def test_nomina_mas_de_400_mil_contando_exentos(cfdi, xmls, tmp_path):
    patron = (xmls.RFC_PATRON, "PATRON SA", "601")
    _recibo(xmls, tmp_path, 1, "2026-06-30", patron, 398000, 70000, aguinaldo_exento=3500.0)
    _, por_anio, _ = cfdi.nomina(_leer(cfdi, tmp_path)[0])
    assert por_anio["2026"]["obligado_400k"] is True


def test_nomina_avisa_subsidio_con_dos_patrones_y_uma_faltante(cfdi, xmls, tmp_path):
    _recibo(xmls, tmp_path, 1, "2031-03-31", (xmls.RFC_PATRON, "PATRON UNO", "601"), 9000, 100, subsidio=500.0)
    _recibo(xmls, tmp_path, 2, "2031-03-31", ("BET020202CD2", "PATRON DOS", "601"), 9000, 100, subsidio=500.0)
    _, _, alertas = cfdi.nomina(_leer(cfdi, tmp_path)[0])
    assert any("subsidio" in a.lower() for a in alertas)
    assert any("UMA" in a and "2031" in a for a in alertas)


def test_deducciones_cfdi_3_3_no_exige_regimen_del_receptor(cfdi, xmls, base, tmp_path):
    xmls.escribir(tmp_path / "v33.xml", xmls.comprobante(U(40), "I", "2022-05-10", 1500, 1500, ("MEDA800101AB1", "DRA", "612"),
                  base["mi_receptor"]("", "D01"), forma="04", version="3.3"))
    revisadas, _ = cfdi.deducciones(_leer(cfdi, tmp_path)[0], xmls.RFC_PF, 2022)
    assert [p for _, p in revisadas] == [[]]


def test_colegiaturas_se_topan_por_alumno_y_nivel(cfdi, xmls, base, tmp_path):
    for n, fecha in ((41, "2026-02-01"), (42, "2026-03-01")):
        xmls.escribir(tmp_path / f"c{n}.xml", xmls.comprobante(U(n), "I", fecha, 15000, 15000,
                      ("ESC010101AA1", "COLEGIO", "603"), base["mi_receptor"]("605", "D10"), forma="03",
                      colegiatura=("ALUM100101HDFLRS09", "Bachillerato o su equivalente")))
    revisadas, _ = cfdi.deducciones(_leer(cfdi, tmp_path)[0], xmls.RFC_PF, 2026)
    resumen = cfdi.resumen_deducciones(revisadas, 2026)
    assert resumen["colegiaturas"] == pytest.approx(24500)


def test_cli_resico_por_anio_lista_meses_sin_cfdi(cfdi, xmls, tmp_path, capsys):
    d = xmls.octubre_resico(tmp_path / "x")
    cfdi.main(["resico", "--rfc", xmls.RFC_PF, "--anio", "2026", "--hoy", "2026-11-26"] + [str(p) for p in sorted(d.glob("*.xml"))])
    out = capsys.readouterr().out
    assert out.count("presentar en ceros") == 9          # enero a septiembre
    assert "| 2026-10 | 50,000.00 |" in out and "Ingresos 2026 en estos XML: 48,000.00" in out
