import shutil
import csv
import hashlib

import pytest

pytestmark = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="requiere pdftotext (poppler)")


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


def test_clasificar_tipos_conocidos(documentos, fx):
    d = fx / "estados_desordenados"
    assert documentos.clasificar(d / "EstadodeCuenta-3.pdf")["destino"] == "banamex/2026-01-04_banamex-micuenta_estado-cuenta.pdf"
    assert documentos.clasificar(d / "Estado de cuenta ARQ - 2026-05.pdf")["destino"] == "dolarapp/2026-05-31_dolarapp-usd_estado-cuenta.pdf"
    assert documentos.clasificar(d / "Estado de cuenta ARQ - 2026-04.pdf")["destino"] == "dolarapp/2026-04-30_dolarapp-usd_estado-cuenta.pdf"
    assert documentos.clasificar(d / "Estado de cuenta ARQ - 2026-09.pdf")["destino"] == "dolarapp/2026-09-30_dolarapp-usd_estado-cuenta.pdf"
    assert documentos.clasificar(d / "EstadodeCuenta.xml")["destino"] == "banco-ficticio/2025-11-05_banco-ficticio_cfdi.xml"
    assert documentos.clasificar(d / "._EstadodeCuenta.pdf")["tipo"] == "metadatos_macos"
    assert documentos.clasificar(d / "Finanzas_Legal" / "IMG_0001.PNG")["destino"] is None
    anual = documentos.clasificar(fx / "sat" / "Anual.LOPA900101AB1.2024.pdf")
    assert anual["tipo"] == "visor_anual" and anual["ejercicio"] == 2024


def test_plan_no_borra_y_aparta_duplicados(documentos, fx):
    plan = documentos.planear(fx / "estados_desordenados", referencia=fx / "referencia")
    por_origen = {p["original"]: p for p in plan}
    assert len(plan) == 12  # todos los archivos tienen destino; nada se omite
    dups = [p for p in plan if p["motivo"].startswith("duplicado")]
    assert len(dups) == 1 and dups[0]["nuevo"].startswith("_duplicados/")
    assert por_origen["._EstadodeCuenta.pdf"]["nuevo"].startswith("_metadatos_macos/")
    assert por_origen["Finanzas_Legal/credit-statement-123456.pdf"]["nuevo"] == "klar/2025-10-31_klar-tdc_estado-cuenta.pdf"
    assert por_origen["Finanzas_Legal/IMG_0001.PNG"]["nuevo"].startswith("_por_clasificar/")
    assert len({p["nuevo"] for p in plan}) == len(plan)


def test_mapa_manual_sobrescribe_clasificacion(documentos, fx):
    mapa = {"Finanzas_Legal/Factura_Oct 2025.pdf": "telefonia/2025-10-30_telefonia_estado-cuenta.pdf"}
    plan = documentos.planear(fx / "estados_desordenados", referencia=fx / "referencia", mapa=mapa)
    assert {p["original"]: p["nuevo"] for p in plan}["Finanzas_Legal/Factura_Oct 2025.pdf"] == mapa["Finanzas_Legal/Factura_Oct 2025.pdf"]


def test_ejecutar_mueve_copia_canonicos_y_deja_manifiesto(documentos, fx, tmp_path):
    origen, repo = fx / "estados_desordenados", tmp_path / "repo"
    hashes_antes = sorted(md5(p) for p in origen.rglob("*") if p.is_file())
    plan = documentos.planear(origen, referencia=fx / "referencia")
    documentos.ejecutar(plan, origen, copia=repo)
    hashes_despues = sorted(md5(p) for p in origen.rglob("*") if p.is_file() and p.name != "MANIFIESTO.csv")
    assert hashes_antes == hashes_despues  # nada se perdió ni cambió
    manifiesto = list(csv.DictReader(open(origen / "MANIFIESTO.csv")))
    assert len(manifiesto) == len(plan)
    copiados = [p for p in repo.rglob("*") if p.is_file() and p.name != "MANIFIESTO.csv"]
    assert all(not str(p.relative_to(repo)).startswith(("_duplicados", "_metadatos_macos", "_por_clasificar")) for p in copiados)
    assert (repo / "banamex" / "2025-12-04_banamex-micuenta_estado-cuenta.pdf").exists()
    assert not any(origen.glob("Finanzas_Legal/*"))  # carpetas vaciadas


def test_ejecutar_no_sobrescribe(documentos, fx, tmp_path):
    origen = fx / "estados_desordenados"
    plan = documentos.planear(origen, referencia=fx / "referencia")
    destino = origen / plan[0]["nuevo"]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(b"ya existia")
    with pytest.raises(FileExistsError):
        documentos.ejecutar(plan, origen, copia=tmp_path / "repo")


def test_depositos_del_extranjero_sin_duplicar_y_con_anio_correcto(documentos, fx):
    d = fx / "estados_desordenados"
    pdfs = [d / "EstadodeCuenta.pdf", d / "EstadodeCuenta-1.pdf", d / "EstadodeCuenta-2.pdf",
            d / "EstadodeCuenta-3.pdf", d / "Estado de cuenta ARQ - 2026-05.pdf", d / "Estado de cuenta ARQ - 2026-04.pdf",
            d / "Estado de cuenta ARQ - 2026-09.pdf"]
    deps = documentos.depositos(pdfs, pagador="ACME LABS")
    assert [(x["fecha"], x["usd"]) for x in deps] == [
        ("2025-10-14", 2500.0), ("2025-11-14", 2500.0), ("2025-12-15", 2800.0), ("2026-04-15", 2500.0),
        ("2026-05-15", 2700.0), ("2026-09-15", 2700.0)]
    dic = deps[2]
    assert dic["tc_banco"] == 17.80 and dic["mxn_banco"] == 49840.00 and dic["cuenta"] == "banamex"
    assert deps[4]["cuenta"] == "dolarapp" and deps[4]["comision_usd"] == 3.0


def test_visor_anual(documentos, fx):
    filas = documentos.visor([fx / "sat" / f"Anual.LOPA900101AB1.{a}.pdf" for a in (2023, 2024, 2025, "2025-1")])
    assert [f["ejercicio"] for f in filas] == [2023, 2024, 2025]  # la descarga repetida no se cuenta dos veces
    a2024 = next(f for f in filas if f["ejercicio"] == 2024)
    assert (a2024["total"], a2024["exento"], a2024["isr_retenido"]) == (450000.00, 25000.00, 90000.00)
    assert a2024["patrones"] == ["EMPRESA FICTICIA SA DE CV", "OTRA FICTICIA SA DE CV"]
    assert next(f for f in filas if f["ejercicio"] == 2025)["periodo"] == "Enero-Julio"


def test_csf(documentos, fx):
    csf = documentos.csf(fx / "sat" / "Csf_LOPA900101AB1.pdf")
    assert csf["regimenes"] == ["Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios"]
    assert csf["estatus"] == "ACTIVO" and csf["rfc"] == "LOPA******AB1"


@pytest.mark.parametrize("entrada,esperado", [
    ("RFC LOPA900101AB1", "RFC LOPA******AB1"),
    ("Folio: LOPA900101AB10001", "Folio: LOPA******AB10001"),  # acuses del Buzón: RFC + consecutivo
    ("CURP LOPA900101MDFPRN01", "CURP [CURP]"),
    ("CLABE 012180001234567890", "CLABE ####7890"),
    ("Cuenta 987654321012", "Cuenta ####1012"),
])
def test_mascara(documentos, entrada, esperado):
    assert documentos.mascara(entrada) == esperado
