"""Casos de la revisión de noviembre de 2026 para autofactura.py."""
import json
from datetime import date

import pytest

U = "DDDDDDDD-1111-0000-0000-0000000000{:02d}".format


@pytest.fixture()
def cfg(autofactura, xmls, tmp_path):
    ruta = tmp_path / "personal" / "autofactura.json"
    ruta.parent.mkdir(parents=True)
    ruta.write_text(json.dumps({
        "carpeta": "facturas",
        "receptor": {"rfc": xmls.RFC_PF, "nombre": xmls.NOMBRE_PF, "cp": xmls.CP_PF},
        "perfiles": {"actividad": {"regimen": "626", "uso": "G03"}, "medicos": {"regimen": "605", "uso": "D01"}},
        "ventanas": {"cafe": "5d", "gas": "mes", "tienda": "72h", "bar": "5D", "kiosko": "3 dias", "rara": "xyz"}}),
        encoding="utf-8")
    return autofactura.cargar_config(ruta)


def _ticket(tmp_path, nombre, contenido):
    t = tmp_path / nombre
    t.write_bytes(contenido)
    return t


def _cfdi(xmls, ruta, n, fecha, total, serie="A", folio="1", regimen="626", uso="G03"):
    return xmls.escribir(ruta, xmls.comprobante(U(n), "I", fecha, round(total / 1.16, 2), total,
                         ("EMI010101AA1", "COMERCIO SA", "601"), (xmls.RFC_PF, xmls.NOMBRE_PF, xmls.CP_PF, regimen, uso),
                         serie=serie, folio=folio, forma="04"))


def test_archivar_dos_veces_el_mismo_uuid_no_duplica(autofactura, cfg, xmls, tmp_path):
    autofactura.registrar(cfg, _ticket(tmp_path, "t.jpg", b"1"), "2026-11-03", "cafe", 96, "actividad")
    autofactura.archivar(cfg, _cfdi(xmls, tmp_path / "d.xml", 1, "2026-11-03", 96), None, "cafe")
    copia = _cfdi(xmls, tmp_path / "d (1).xml", 1, "2026-11-03", 96)
    with pytest.raises(autofactura.ErrorAutofactura, match="ya está archivado"):
        autofactura.archivar(cfg, copia, None, "cafe")
    assert copia.exists()


def test_no_empareja_con_tickets_viejos_ni_posteriores(autofactura, cfg, xmls, tmp_path):
    autofactura.registrar(cfg, _ticket(tmp_path, "a.jpg", b"a"), "2026-08-14", "gas", 500, "actividad")
    autofactura.registrar(cfg, _ticket(tmp_path, "b.jpg", b"b"), "2026-12-01", "gas", 500, "actividad")
    x, _, avisos = autofactura.archivar(cfg, _cfdi(xmls, tmp_path / "g.xml", 2, "2026-11-20", 500), None, "gas")
    assert x.parent.name == "2026-11-20" and any("sin ticket" in a for a in avisos)
    agosto = (cfg["_carpeta"] / "2026-08" / "README.md").read_text(encoding="utf-8")
    assert "| Pendiente |" in agosto


def test_vigencias_incluye_pendientes_del_mes_anterior(autofactura, cfg, tmp_path):
    autofactura.registrar(cfg, _ticket(tmp_path, "c.jpg", b"c"), "2026-11-28", "cafe", 50)
    filas = autofactura.vigencias(cfg, date(2026, 12, 2), "2026-12")
    assert [(f[3], f[1]) for f in filas] == [("cafe", "quedan 1 días")]


@pytest.mark.parametrize("comercio,esperado", [("tienda", date(2026, 11, 13)), ("bar", date(2026, 11, 15)),
                                              ("kiosko", date(2026, 11, 13))])
def test_ventanas_en_horas_y_mayusculas(autofactura, cfg, comercio, esperado):
    assert autofactura.limite("2026-11-10", autofactura.ventana(cfg, comercio)) == ("ok", esperado)


def test_ventana_que_no_se_entiende_no_pasa_por_sin_plazo(autofactura, cfg, tmp_path):
    autofactura.registrar(cfg, _ticket(tmp_path, "r.jpg", b"r"), "2026-11-10", "rara", 10)
    assert autofactura.vigencias(cfg, date(2026, 11, 26))[0][1] == "VENTANA INVÁLIDA"


def test_cfdi_sin_serie_ni_folio_queda_emparejado(autofactura, cfg, xmls, tmp_path):
    autofactura.registrar(cfg, _ticket(tmp_path, "g.jpg", b"g"), "2026-11-03", "gas", 500, "actividad")
    x, _, _ = autofactura.archivar(cfg, _cfdi(xmls, tmp_path / "g.xml", 3, "2026-11-03", 500, serie="", folio=""),
                                   None, "gas")
    assert x.name == f"gas_500.00_{U(3)[:8]}.xml"
    assert autofactura._tickets_sin_cfdi(cfg["_carpeta"], "gas", 500, "2026-11-20") == []


def test_serie_o_folio_con_diagonal_se_limpia(autofactura, cfg, xmls, tmp_path):
    autofactura.registrar(cfg, _ticket(tmp_path, "f.jpg", b"f"), "2026-11-03", "cafe", 96, "actividad")
    x, _, _ = autofactura.archivar(cfg, _cfdi(xmls, tmp_path / "f.xml", 4, "2026-11-03", 96, serie="FAC",
                                              folio="2026/000123"), None, "cafe")
    assert x.name == "cafe_96.00_FAC2026-000123.xml"


def test_archivar_sin_pdf_existente_no_mueve_nada(autofactura, cfg, xmls, tmp_path):
    xml = _cfdi(xmls, tmp_path / "s.xml", 5, "2026-11-03", 96)
    with pytest.raises(autofactura.ErrorAutofactura, match="PDF"):
        autofactura.archivar(cfg, xml, tmp_path / "s.PDF", "cafe")
    assert xml.exists()


def test_fecha_hostil_en_el_xml_no_escribe_fuera(autofactura, cfg, xmls, tmp_path):
    xml = _cfdi(xmls, tmp_path / "h.xml", 6, "2026-11-03", 10)
    xml.write_text(xml.read_text(encoding="utf-8").replace('Fecha="2026-11-03T12:00:00"', 'Fecha="../../../q"'),
                   encoding="utf-8")
    with pytest.raises(autofactura.ErrorAutofactura):
        autofactura.archivar(cfg, xml, None, "cafe")
    assert xml.exists() and not (tmp_path / "q").exists()


def test_registrar_limpia_barras_y_respeta_readme_sin_salto_final(autofactura, cfg, tmp_path):
    autofactura.registrar(cfg, _ticket(tmp_path, "1.jpg", b"1"), "2026-11-03", "cafe", 10, notas="folio 1 | token X")
    readme = cfg["_carpeta"] / "2026-11" / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")  # editado a mano
    autofactura.registrar(cfg, _ticket(tmp_path, "2.jpg", b"2"), "2026-11-05", "gas", 20)
    filas = autofactura._filas(readme.read_text(encoding="utf-8"))
    assert [f[1][1] for f in filas] == ["cafe", "gas"]
    assert filas[0][1][7] == "folio 1 / token X"


def test_registrar_rechaza_el_mismo_ticket_dos_veces(autofactura, cfg, tmp_path):
    autofactura.registrar(cfg, _ticket(tmp_path, "foto.jpg", b"igual"), "2026-11-03", "cafe", 10)
    with pytest.raises(autofactura.ErrorAutofactura, match="ya está registrado"):
        autofactura.registrar(cfg, _ticket(tmp_path, "foto (1).jpg", b"igual"), "2026-11-03", "cafe", 10)


def test_registrar_exige_fecha_iso(autofactura, cfg, tmp_path):
    with pytest.raises(autofactura.ErrorAutofactura, match="fecha"):
        autofactura.registrar(cfg, _ticket(tmp_path, "x.jpg", b"x"), "20261103", "cafe", 10)


def test_ticket_sin_extension_cuenta(autofactura, cfg, xmls, tmp_path):
    autofactura.registrar(cfg, _ticket(tmp_path, "foto", b"sin-ext"), "2026-11-03", "cafe", 96, "actividad")
    x, _, avisos = autofactura.archivar(cfg, _cfdi(xmls, tmp_path / "e.xml", 7, "2026-11-03", 96), None, "cafe")
    assert x.parent.name == "2026-11-03" and not any("sin ticket" in a for a in avisos)


def test_archivar_verifica_el_receptor_segun_el_perfil_del_ticket(autofactura, cfg, xmls, tmp_path):
    autofactura.registrar(cfg, _ticket(tmp_path, "m.jpg", b"m"), "2026-11-03", "medico", 1200, "medicos")
    malo = _cfdi(xmls, tmp_path / "m.xml", 8, "2026-11-03", 1200, regimen="626", uso="D01")
    with pytest.raises(autofactura.ErrorAutofactura, match="receptor incorrecto"):
        autofactura.archivar(cfg, malo, None, "medico")
    assert malo.exists()
    x, _, avisos = autofactura.archivar(cfg, malo, None, "medico", forzar=True)
    assert x.exists() and any("--forzar" in a for a in avisos)


def test_carpeta_dentro_del_repo_fuera_de_personal_se_rechaza(autofactura, tmp_path):
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps({"carpeta": str(autofactura.rutas.RAIZ / "ejemplos" / "facturas")}), encoding="utf-8")
    with pytest.raises(autofactura.ErrorAutofactura, match="personal/"):
        autofactura.cargar_config(ruta)


def test_configuracion_inexistente_da_instrucciones(autofactura, tmp_path):
    with pytest.raises(autofactura.ErrorAutofactura, match="ejemplos/autofactura.ejemplo.json"):
        autofactura.cargar_config(tmp_path / "no-existe.json")
