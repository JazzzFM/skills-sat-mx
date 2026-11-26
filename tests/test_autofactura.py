import json
from datetime import date


def _cfg(autofactura, tmp_path, xmls):
    ruta = tmp_path / "personal" / "autofactura.json"
    ruta.parent.mkdir(parents=True)
    ruta.write_text(json.dumps({
        "carpeta": "facturas",
        "receptor": {"rfc": xmls.RFC_PF, "nombre": xmls.NOMBRE_PF, "cp": xmls.CP_PF},
        "perfiles": {"actividad": {"regimen": "626", "uso": "G03"}},
        "ventanas": {"Café Ejemplo": "5d", "gasolinera-ejemplo": "mes", "app-viajes": "sin-plazo"}}), encoding="utf-8")
    return autofactura.cargar_config(ruta)


def test_registrar_archivar_y_marcar_facturado(autofactura, xmls, tmp_path):
    cfg = _cfg(autofactura, tmp_path, xmls)
    ticket = tmp_path / "foto.JPG"
    ticket.write_bytes(b"jpg")
    destino = autofactura.registrar(cfg, ticket, "2026-11-03", "Café Ejemplo", 96.0, "actividad", "folio A386774")
    assert destino == cfg["_carpeta"] / "2026-11" / "2026-11-03" / "cafe-ejemplo_96.00_ticket.jpg"
    assert not ticket.exists()
    # el portal timbra días después y redondea dos centavos
    xml = xmls.escribir(tmp_path / "descarga.xml", xmls.comprobante(
        "DDDDDDDD-0000-0000-0000-000000000001", "I", "2026-11-06", 82.74, 95.98, ("CAF010101AA1", "CAFE SA", "601"),
        (xmls.RFC_PF, xmls.NOMBRE_PF, xmls.CP_PF, "626", "G03"), serie="SF", folio="61", forma="04"))
    pdf = tmp_path / "descarga.pdf"
    pdf.write_bytes(b"%PDF")
    x, p, aviso = autofactura.archivar(cfg, xml, pdf, "cafe-ejemplo")
    assert x.parent.name == "2026-11-03" and x.name == "cafe-ejemplo_95.98_SF61.xml" and p.suffix == ".pdf"
    assert aviso == ""
    readme = (cfg["_carpeta"] / "2026-11" / "README.md").read_text(encoding="utf-8")
    assert "| 2026-11-03 | cafe-ejemplo | $96.00 | Facturado | DDDDDDDD-0000-0000-0000-000000000001 | 04 |" in readme
    assert "redondeo del portal" in readme


def test_archivar_sin_ticket_usa_fecha_del_xml(autofactura, xmls, tmp_path):
    cfg = _cfg(autofactura, tmp_path, xmls)
    xml = xmls.escribir(tmp_path / "f.xml", xmls.comprobante(
        "DDDDDDDD-0000-0000-0000-000000000002", "I", "2026-11-09", 500, 580, (xmls.RFC_GAS, "GAS SA", "601"),
        (xmls.RFC_PF, xmls.NOMBRE_PF, xmls.CP_PF, "626", "G03")))
    x, _, aviso = autofactura.archivar(cfg, xml, None, "gasolinera-ejemplo")
    assert x.parent.name == "2026-11-09" and "sin ticket" in aviso


def test_vigencias_ordena_por_urgencia(autofactura, xmls, tmp_path):
    cfg = _cfg(autofactura, tmp_path, xmls)
    for i, (fecha, comercio) in enumerate([("2026-11-20", "Café Ejemplo"), ("2026-11-03", "gasolinera-ejemplo"),
                                           ("2026-11-24", "Café Ejemplo"), ("2026-11-10", "tienda-nueva"),
                                           ("2026-11-11", "app-viajes")]):
        t = tmp_path / f"t{i}.pdf"
        t.write_bytes(b"%PDF")
        autofactura.registrar(cfg, t, fecha, comercio, 100 + i)
    filas = autofactura.vigencias(cfg, "2026-11", date(2026, 11, 26))
    estados = [(f[3], f[1]) for f in filas]
    assert estados == [("cafe-ejemplo", "VENCIDO hace 1 días"), ("cafe-ejemplo", "quedan 3 días"),
                       ("gasolinera-ejemplo", "quedan 4 días"), ("app-viajes", "SIN PLAZO DURO"),
                       ("tienda-nueva", "VENTANA DESCONOCIDA")]


def test_no_sobrescribe(autofactura, xmls, tmp_path):
    cfg = _cfg(autofactura, tmp_path, xmls)
    for i in range(2):
        t = tmp_path / f"t{i}.pdf"
        t.write_bytes(b"%PDF")
        d = autofactura.registrar(cfg, t, "2026-11-05", "gasolinera-ejemplo", 500)
    assert d.name == "gasolinera-ejemplo_500.00_ticket-2.pdf"
