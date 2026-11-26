"""Lectura local de CFDI (XML 4.0 y 3.3, y Retenciones 2.0) para personas físicas, sin dependencias externas.

Subcomandos (`python3 -I herramientas/cfdi_mx.py <subcomando> --help`):
  ver          Resume uno o varios XML: tipo, fecha, emisor, receptor, totales e impuestos.
  verificar    Compara el receptor de cada XML contra tu configuración (después de una autofactura).
  resico       Ingresos cobrados, ISR e IVA por mes para RESICO PF, desde tus XML emitidos y recibidos.
  nomina       Suma recibos de nómina por año y patrón: gravado, exento, ISR retenido, subsidio.
  deducciones  Revisa si tus facturas de gastos personales cumplen los requisitos de la anual.

Los XML se tratan como datos no confiables: se rechazan DOCTYPE y entidades, se validan las fechas y solo se leen
atributos. Los XML sin timbre fiscal se ignoran. El RFC de persona física se enmascara en la salida salvo con
--sin-mascara en `ver`. Nada sale de tu equipo.
"""
import argparse
import csv
import importlib.util
import json
import pathlib
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict
from datetime import date

_AQUI = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("fiscal_mx", _AQUI / "fiscal_mx.py")
fiscal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fiscal)

NS_CFDI = ("http://www.sat.gob.mx/cfd/4", "http://www.sat.gob.mx/cfd/3")
NS_RETENCIONES = "http://www.sat.gob.mx/esquemas/retencionpago/2"
NS_RETENCIONES_1 = "http://www.sat.gob.mx/esquemas/retencionpago/1"
NS_TFD = "http://www.sat.gob.mx/TimbreFiscalDigital"
NS_PAGOS20 = "http://www.sat.gob.mx/Pagos20"
NS_PAGOS10 = "http://www.sat.gob.mx/Pagos"
NS_NOMINA = "http://www.sat.gob.mx/nomina12"
NS_IEDU = "http://www.sat.gob.mx/iedu"
RFC_PUBLICO = "XAXX010101000"

# Catálogo c_UsoCFDI del SAT (versión del 15/10/2026): regímenes de receptor admitidos por cada uso.
REG_DEDUCCIONES = {"605", "606", "607", "608", "611", "612", "614", "615", "625"}
REG_GASTOS = {"601", "603", "606", "612", "620", "621", "622", "623", "624", "625", "626"}
# Percepciones de nómina que se gravan por el art. 95 (separación, indemnización, jubilación en una exhibición).
PERCEPCIONES_ART_95 = {"022", "023", "025", "039"}
_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")


def regimenes_admitidos(uso):
    """Regímenes del receptor que el catálogo admite para un uso de CFDI; None si admite todos o no se conoce."""
    if uso.startswith("D"):
        return REG_DEDUCCIONES
    if uso in ("G01", "G03") or uso.startswith("I"):
        return REG_GASTOS
    if uso == "G02":
        return REG_GASTOS | {"616"}
    if uso == "CN01":
        return {"605"}
    return None  # S01, CP01: todos


def es_uso_de_gasto(uso):
    return uso.startswith("G") or uso.startswith("I")


# ---------- utilidades ----------

def _f(valor, defecto=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def _fecha(valor, campo, ruta):
    v = (valor or "")[:10]
    try:
        if not _FECHA.fullmatch(v):
            raise ValueError
        date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"{ruta}: fecha {campo} inválida ({valor!r})") from None
    return v


def mascara_rfc(rfc):
    """RFC de persona física (13 posiciones) -> ABCD******XY1. El de persona moral (12) es público en tickets."""
    rfc = (rfc or "").upper()
    if re.fullmatch(r"[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}", rfc) and rfc != RFC_PUBLICO:
        return rfc[:4] + "******" + rfc[-3:]
    return rfc


def normalizar_nombre(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split())


def _s(valor):
    """Texto de un XML listo para imprimir: sin saltos de línea ni '|' que rompan la salida o las tablas."""
    return re.sub(r"[\r\n|]+", " ", str(valor or "")).strip()


def _quien(parte):
    """Nombre del emisor o receptor, o su RFC enmascarado si no trae nombre."""
    return _s(parte["nombre"]) or mascara_rfc(parte["rfc"])


def _hijo(el, nombre, ns):
    return None if el is None else el.find(f"{{{ns}}}{nombre}")


def _hijos(el, nombre, ns):
    return [] if el is None else el.findall(f"{{{ns}}}{nombre}")


# ---------- lectura ----------

def leer(ruta):
    """Devuelve un dict con los datos fiscales de un CFDI o de un CFDI de Retenciones. ValueError si no lo es."""
    datos = pathlib.Path(ruta).read_bytes().lstrip(b"\xef\xbb\xbf \t\r\n")
    if re.search(rb"<!(DOCTYPE|ENTITY)", datos, re.IGNORECASE):
        raise ValueError(f"{ruta}: trae DOCTYPE o entidades; un CFDI nunca los usa")
    raiz = ET.fromstring(datos)
    ns = raiz.tag[1:].split("}")[0] if raiz.tag.startswith("{") else ""
    if ns == NS_RETENCIONES:
        return _leer_retenciones(raiz, ruta)
    if ns == NS_RETENCIONES_1:
        raise ValueError(f"{ruta}: CFDI de Retenciones 1.0 no soportado; revísalo a mano")
    if ns not in NS_CFDI or not raiz.tag.endswith("Comprobante"):
        raise ValueError(f"{ruta}: no es un CFDI 3.3/4.0")
    a = raiz.attrib
    tc = _f(a.get("TipoCambio"), 1.0) or 1.0
    emisor, receptor = _hijo(raiz, "Emisor", ns), _hijo(raiz, "Receptor", ns)
    tfd = raiz.find(f".//{{{NS_TFD}}}TimbreFiscalDigital")
    glob = _hijo(raiz, "InformacionGlobal", ns)
    relacionados = []
    for rel in _hijos(raiz, "CfdiRelacionados", ns):
        relacionados.append((rel.get("TipoRelacion", ""),
                             [r.get("UUID", "").upper() for r in _hijos(rel, "CfdiRelacionado", ns)]))
    c = {
        "archivo": str(ruta),
        "version": a.get("Version", ""),
        "tipo": a.get("TipoDeComprobante", ""),
        "fecha": _fecha(a.get("Fecha"), "Fecha", ruta),
        "serie": a.get("Serie", ""),
        "folio": a.get("Folio", ""),
        "uuid": (tfd.attrib.get("UUID", "") if tfd is not None else "").upper(),
        "moneda": a.get("Moneda", "MXN"),
        "tipo_cambio": tc,
        "subtotal": _f(a.get("SubTotal")),
        "descuento": _f(a.get("Descuento")),
        "total": _f(a.get("Total")),
        "metodo": a.get("MetodoPago", ""),
        "forma": a.get("FormaPago", ""),
        "emisor": {"rfc": (emisor.get("Rfc", "") if emisor is not None else "").upper(),
                   "nombre": emisor.get("Nombre", "") if emisor is not None else "",
                   "regimen": emisor.get("RegimenFiscal", "") if emisor is not None else ""},
        "receptor": {"rfc": (receptor.get("Rfc", "") if receptor is not None else "").upper(),
                     "nombre": receptor.get("Nombre", "") if receptor is not None else "",
                     "cp": receptor.get("DomicilioFiscalReceptor", "") if receptor is not None else "",
                     "regimen": receptor.get("RegimenFiscalReceptor", "") if receptor is not None else "",
                     "uso": receptor.get("UsoCFDI", "") if receptor is not None else ""},
        "global": None if glob is None else {"periodicidad": glob.get("Periodicidad", ""),
                                             "meses": glob.get("Meses", ""), "anio": glob.get("Año", "")},
        "relacionados": relacionados,
        "traslados": defaultdict(float),
        "retenciones": defaultdict(float),
        "pagos": [],
        "nomina": None,
        "colegiaturas": [{"curp": i.get("CURP", ""), "nivel": i.get("nivelEducativo", "")}
                         for i in raiz.iter(f"{{{NS_IEDU}}}instEducativas")],
    }
    imp = _hijo(raiz, "Impuestos", ns)  # solo el nodo del comprobante, no el de cada concepto
    for t in _hijos(_hijo(imp, "Traslados", ns), "Traslado", ns):
        c["traslados"][t.get("Impuesto", "")] += _f(t.get("Importe"))
    for r in _hijos(_hijo(imp, "Retenciones", ns), "Retencion", ns):
        c["retenciones"][r.get("Impuesto", "")] += _f(r.get("Importe"))
    c["pagos"] = _leer_pagos(raiz, ruta)
    c["nomina"] = _leer_nomina(raiz)
    return c


def _leer_pagos(raiz, ruta):
    pagos = []
    N = NS_PAGOS20
    for p in raiz.iter(f"{{{N}}}Pago"):
        fecha = _fecha(p.get("FechaPago"), "FechaPago", ruta)
        tc = _f(p.get("TipoCambioP"), 1.0) or 1.0
        monto = _f(p.get("Monto"))
        imp = _hijo(p, "ImpuestosP", N)
        traslados = _hijos(_hijo(imp, "TrasladosP", N), "TrasladoP", N)
        retenciones = _hijos(_hijo(imp, "RetencionesP", N), "RetencionP", N)
        iva = sum(_f(t.get("ImporteP")) for t in traslados if t.get("ImpuestoP") == "002")
        ret_isr = sum(_f(r.get("ImporteP")) for r in retenciones if r.get("ImpuestoP") == "001")
        ret_iva = sum(_f(r.get("ImporteP")) for r in retenciones if r.get("ImpuestoP") == "002")
        # Lo cobrado sin IVA: el monto recibido, menos los impuestos trasladados, más lo que retuvo el cliente.
        base = monto - sum(_f(t.get("ImporteP")) for t in traslados) + sum(_f(r.get("ImporteP")) for r in retenciones)
        docs = []
        for d in _hijos(p, "DoctoRelacionado", N):
            eq = _f(d.get("EquivalenciaDR"), 1.0) or 1.0
            tras_dr = _hijos(_hijo(_hijo(d, "ImpuestosDR", N), "TrasladosDR", N), "TrasladoDR", N)
            docs.append({"uuid": d.get("IdDocumento", "").upper(), "objeto": d.get("ObjetoImpDR", ""),
                         "iva": sum(_f(t.get("ImporteDR")) for t in tras_dr if t.get("ImpuestoDR") == "002") / eq * tc,
                         "saldo": _f(d.get("ImpSaldoInsoluto")), "moneda": d.get("MonedaDR", "MXN")})
        sin_desglose = not traslados and any(d["objeto"] == "02" for d in docs)
        pagos.append({"fecha": fecha, "moneda": p.get("MonedaP", "MXN"), "tc": tc, "monto": monto * tc,
                      "base": base * tc, "iva": iva * tc, "ret_isr": ret_isr * tc, "ret_iva": ret_iva * tc,
                      "sin_desglose": sin_desglose, "pagos10": False, "docs": docs})
    for p in raiz.iter(f"{{{NS_PAGOS10}}}Pago"):  # Pagos 1.0 (2022 y antes): sin desglose de impuestos
        tc = _f(p.get("TipoCambioP"), 1.0) or 1.0
        monto = _f(p.get("Monto")) * tc
        pagos.append({"fecha": _fecha(p.get("FechaPago"), "FechaPago", ruta), "moneda": p.get("MonedaP", "MXN"),
                      "tc": tc, "monto": monto, "base": monto, "iva": 0.0, "ret_isr": 0.0, "ret_iva": 0.0,
                      "sin_desglose": True, "pagos10": True,
                      "docs": [{"uuid": d.get("IdDocumento", "").upper(), "objeto": "", "iva": 0.0,
                                "saldo": _f(d.get("ImpSaldoInsoluto")), "moneda": d.get("MonedaDR", "MXN")}
                               for d in _hijos(p, "DoctoRelacionado", NS_PAGOS10)]})
    return pagos


def _leer_nomina(raiz):
    n = raiz.find(f".//{{{NS_NOMINA}}}Nomina")
    if n is None:
        return None
    per = _hijo(n, "Percepciones", NS_NOMINA)
    exentos, separacion = defaultdict(float), 0.0
    for p in _hijos(per, "Percepcion", NS_NOMINA):
        exentos[p.get("TipoPercepcion", "")] += _f(p.get("ImporteExento"))
        if p.get("TipoPercepcion") in PERCEPCIONES_ART_95:
            separacion += _f(p.get("ImporteGravado"))
    isr = sum(_f(d.get("Importe")) for d in _hijos(_hijo(n, "Deducciones", NS_NOMINA), "Deduccion", NS_NOMINA)
              if d.get("TipoDeduccion") == "002")
    subsidio = sum(_f(o.get("Importe")) for o in _hijos(_hijo(n, "OtrosPagos", NS_NOMINA), "OtroPago", NS_NOMINA)
                   if o.get("TipoOtroPago") == "002")
    return {"tipo": n.get("TipoNomina", ""), "fecha_pago": (n.get("FechaPago") or "")[:10],
            "gravado": _f(per.get("TotalGravado")) if per is not None else 0.0,
            "exento": _f(per.get("TotalExento")) if per is not None else 0.0,
            "separacion_gravada": separacion, "isr": isr, "subsidio": subsidio,
            "aguinaldo_exento": exentos["002"], "ptu_exento": exentos["003"], "prima_vac_exento": exentos["021"],
            "separacion": _f(per.get("TotalSeparacionIndemnizacion")) if per is not None else 0.0,
            "jubilacion": _f(per.get("TotalJubilacionPensionRetiro")) if per is not None else 0.0}


def _leer_retenciones(raiz, ruta):
    """CFDI de Retenciones e información de pagos 2.0 (esquema público retencionpago/2 del SAT)."""
    N = NS_RETENCIONES
    a = raiz.attrib
    tfd = raiz.find(f".//{{{NS_TFD}}}TimbreFiscalDigital")
    em, rec = _hijo(raiz, "Emisor", N), _hijo(raiz, "Receptor", N)
    nac, per, tot = _hijo(rec, "Nacional", N), _hijo(raiz, "Periodo", N), _hijo(raiz, "Totales", N)
    ret = defaultdict(float)
    for i in _hijos(tot, "ImpRetenidos", N):
        ret[i.get("ImpuestoRet", "")] += _f(i.get("MontoRet"))
    try:
        periodo = (int(per.get("Ejercicio")), int(per.get("MesIni")), int(per.get("MesFin")))
        if not all(1 <= m <= 12 for m in periodo[1:]):
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        raise ValueError(f"{ruta}: periodo de retención inválido") from None
    return {"archivo": str(ruta), "version": a.get("Version", ""), "tipo": "R",
            "fecha": _fecha(a.get("FechaExp"), "FechaExp", ruta), "serie": "", "folio": a.get("FolioInt", ""),
            "uuid": (tfd.attrib.get("UUID", "") if tfd is not None else "").upper(), "moneda": "MXN",
            "tipo_cambio": 1.0, "subtotal": _f(tot.get("MontoTotOperacion")) if tot is not None else 0.0,
            "descuento": 0.0, "total": _f(tot.get("MontoTotRet")) if tot is not None else 0.0, "metodo": "", "forma": "",
            "emisor": {"rfc": (em.get("RfcE", "") if em is not None else "").upper(),
                       "nombre": em.get("NomDenRazSocE", "") if em is not None else "",
                       "regimen": em.get("RegimenFiscalE", "") if em is not None else ""},
            "receptor": {"rfc": (nac.get("RfcR", "") if nac is not None else "").upper(),
                         "nombre": nac.get("NomDenRazSocR", "") if nac is not None else "",
                         "cp": nac.get("DomicilioFiscalR", "") if nac is not None else "", "regimen": "", "uso": ""},
            "global": None, "relacionados": [], "traslados": defaultdict(float), "retenciones": ret, "pagos": [],
            "nomina": None, "colegiaturas": [], "periodo": periodo, "clave": a.get("CveRetenc", "")}


def leer_varios(rutas):
    """Lee varios XML; descarta los que no son CFDI o no están timbrados y deduplica por UUID."""
    vistos, salida, avisos = set(), [], []
    for r in rutas:
        try:
            c = leer(r)
        except (ValueError, ET.ParseError, OSError) as e:
            avisos.append(f"ignorado {r}: {e}")
            continue
        if not c["uuid"]:
            avisos.append(f"sin timbre {r}: no trae TimbreFiscalDigital (borrador o vista previa); se ignora")
            continue
        if c["uuid"] in vistos:
            avisos.append(f"duplicado {r} (UUID {c['uuid']})")
            continue
        vistos.add(c["uuid"])
        salida.append(c)
    return salida, avisos


# ---------- ver ----------

def _cmd_ver(a):
    cfdis, avisos = leer_varios(a.xml)
    m = (lambda x: x) if a.sin_mascara else mascara_rfc
    print("| Archivo | Tipo | Fecha | UUID | Emisor | Receptor | Régimen/Uso | Método/Forma | SubTotal | IVA | Ret ISR | Total |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in cfdis:
        print(f"| {_s(pathlib.Path(c['archivo']).name)} | {c['tipo']} | {c['fecha']} | {c['uuid'][:8]}… | "
              f"{m(c['emisor']['rfc'])} {_s(c['emisor']['nombre'])} | {m(c['receptor']['rfc'])} "
              f"{_s(c['receptor']['nombre'])} | {_s(c['receptor']['regimen'])}/{_s(c['receptor']['uso'])} | "
              f"{_s(c['metodo'])}/{_s(c['forma'])} | {c['subtotal']:,.2f} | {c['traslados']['002']:,.2f} | "
              f"{c['retenciones']['001']:,.2f} | {c['total']:,.2f} {_s(c['moneda'])} |")
    for x in avisos:
        print(f"- {_s(x)}")


# ---------- verificar (autofactura) ----------

def cargar_receptor(ruta, perfil=None):
    """Lee el bloque `receptor` (y el `perfil` elegido) de la configuración de autofactura."""
    cfg = json.loads(pathlib.Path(ruta).read_text(encoding="utf-8"))
    base = dict(cfg.get("receptor", cfg))
    if perfil:
        perfiles = cfg.get("perfiles", {})
        if perfil not in perfiles:
            raise KeyError(f"perfil '{perfil}' no está en {ruta}; perfiles: {', '.join(perfiles) or 'ninguno'}")
        base.update(perfiles[perfil])
    return base


def verificar(c, esperado):
    """(problemas, notas) del receptor de un CFDI frente a los datos esperados.

    Los problemas impiden archivar; las notas no (por ejemplo, un nombre que solo difiere en mayúsculas o acentos,
    que el PAC ya validó contra el SAT al timbrar)."""
    r, problemas, notas = c["receptor"], [], []
    v33 = c["version"].startswith("3")
    if c["tipo"] != "I":
        problemas.append(f"tipo {c['tipo']} (se esperaba I, ingreso)")
    if r["rfc"] != esperado.get("rfc", "").upper():
        problemas.append("RFC del receptor distinto")
    if esperado.get("nombre"):
        if normalizar_nombre(r["nombre"]) != normalizar_nombre(esperado["nombre"]):
            problemas.append(f"nombre del receptor '{_s(r['nombre'])}'")
        elif r["nombre"] != esperado["nombre"]:
            notas.append(f"el nombre solo difiere en mayúsculas, acentos o espacios: '{_s(r['nombre'])}'")
    if v33:
        notas.append("CFDI 3.3: no trae código postal ni régimen del receptor; no se revisaron")
    else:
        if esperado.get("cp") and r["cp"] != esperado["cp"]:
            problemas.append(f"código postal {_s(r['cp'])}")
        if esperado.get("regimen") and r["regimen"] != esperado["regimen"]:
            problemas.append(f"régimen {_s(r['regimen'])} (se esperaba {esperado['regimen']})")
        admitidos = regimenes_admitidos(r["uso"])
        if admitidos is not None and r["regimen"] not in admitidos:
            problemas.append(f"el catálogo no admite uso {_s(r['uso'])} con régimen {_s(r['regimen'])}")
    if esperado.get("uso") and r["uso"] != esperado["uso"]:
        problemas.append(f"uso {_s(r['uso'])} (se esperaba {esperado['uso']})")
    return problemas, notas


def _cmd_verificar(a):
    esperado = cargar_receptor(a.config, a.perfil)
    cfdis, avisos = leer_varios(a.xml)
    for x in avisos:
        print(f"- {_s(x)}")
    if not cfdis:
        print("!! Ningún archivo es un CFDI timbrado válido: no hay nada que archivar.", file=sys.stderr)
        sys.exit(2)
    malos = 0
    for c in cfdis:
        problemas, notas = verificar(c, esperado)
        estado = "OK" if not problemas else "REVISAR: " + "; ".join(problemas)
        malos += bool(problemas)
        print(f"== {_s(pathlib.Path(c['archivo']).name)}: {estado}")
        print(f"   UUID {c['uuid']} | {c['fecha']} | emisor {mascara_rfc(c['emisor']['rfc'])} {_s(c['emisor']['nombre'])} | "
              f"total {c['total']:,.2f} {_s(c['moneda'])} | {_s(c['metodo'])} forma {_s(c['forma'])} | "
              f"receptor {mascara_rfc(c['receptor']['rfc'])} {_s(c['receptor']['regimen'])}/{_s(c['receptor']['uso'])}")
        for n in notas:
            print(f"   nota: {n}")
    if malos:
        print(f"!! {malos} CFDI con receptor incorrecto: no los archives; pide al comercio cancelar y reexpedir.",
              file=sys.stderr)
        sys.exit(1)


# ---------- resico ----------

def limite_complemento(fecha_pago):
    """Quinto día natural del mes siguiente al pago (RMF 2026 regla 2.7.1.32)."""
    d = date.fromisoformat(fecha_pago)
    a, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(a, m, 5)


def tasa_resico(ingreso, anio=None):
    """Compatibilidad: tasa del ejercicio (por omisión, el año en curso)."""
    return fiscal.tasa_resico(ingreso, anio or date.today().year)


def _mes_de_ingreso(c, avisos):
    """Mes al que corresponde una factura de ingreso PUE: el de su fecha o, si es global, el periodo que ampara."""
    g = c["global"]
    if not g:
        return c["fecha"][:7]
    if g["periodicidad"] in ("01", "02", "03", "04") and re.fullmatch(r"0[1-9]|1[0-2]", g["meses"] or "") \
            and re.fullmatch(r"\d{4}", g["anio"] or ""):
        mes = f"{g['anio']}-{g['meses']}"
        if mes != c["fecha"][:7]:
            avisos.append(f"global {c['uuid'][:8]} timbrada el {c['fecha']}: se asigna a {mes}, el periodo que ampara "
                          "(InformacionGlobal); confírmalo contra la precarga")
        return mes
    avisos.append(f"global {c['uuid'][:8]} con periodicidad {g['periodicidad']} y meses {g['meses']}: se asignó al mes "
                  f"de su fecha ({c['fecha'][:7]}); revísala a mano")
    return c["fecha"][:7]


def _nuevo_mes():
    return {"cobrado": 0.0, "descuentos": 0.0, "iva_trasladado": 0.0, "ret_isr": 0.0, "ret_iva": 0.0,
            "iva_acreditable": 0.0, "detalle": [], "gastos": []}


def resico(cfdis, rfc, excluir=()):
    """Agrupa por mes lo que el SAT precarga en la declaración RESICO PF y lo que falta para cuadrarla.

    Ingresos cobrados = facturas de ingreso PUE del mes (la global, en el periodo que ampara) + pagos del
    complemento con FechaPago en el mes, sin IVA; se restan las notas de crédito (egreso) del mes con sus
    retenciones. Las PPD solo cuentan con su complemento. Se suman las retenciones de los CFDI de Retenciones
    que no estén ya expresadas en tus facturas a ese cliente. IVA acreditable: facturas recibidas con uso de gasto
    (G o I) y pagos de facturas recibidas con ese uso; revisa que cada gasto sea deducible (regla 3.13.18).

    Devuelve (meses, pendientes, avisos). `pendientes` lista las PPD emitidas sin complemento o con saldo insoluto.
    """
    rfc = rfc.upper()
    manual = {u.upper() for u in excluir}
    excluir = set(manual)
    avisos = []
    presentes = {c["uuid"] for c in cfdis}
    for c in cfdis:
        for tipo_rel, uuids in c["relacionados"]:
            if tipo_rel == "04":
                for u in uuids:
                    if u in presentes and u not in excluir:
                        excluir.add(u)
                        avisos.append(f"{u[:8]} sustituida por {c['uuid'][:8]} (relación 04): se excluye; confirma "
                                      "que esté cancelada")
    meses = defaultdict(_nuevo_mes)
    ppd_emitidas, ppd_recibidas = {}, {}
    for c in cfdis:
        if c["uuid"] not in excluir and c["tipo"] == "I" and c["metodo"] == "PPD":
            if c["emisor"]["rfc"] == rfc:
                ppd_emitidas[c["uuid"]] = c
            elif c["receptor"]["rfc"] == rfc:
                ppd_recibidas[c["uuid"]] = c
    pagados, ultimo_saldo = set(), {}
    ret_por_cliente = defaultdict(float)
    retenciones = []
    for c in cfdis:
        if c["uuid"] in excluir:
            if c["uuid"] in manual:
                avisos.append(f"excluido por cancelado: {c['uuid']}")
            continue
        tc = c["tipo_cambio"]
        neto = (c["subtotal"] - c["descuento"]) * tc
        if c["tipo"] == "R":
            if c["receptor"]["rfc"] == rfc:
                retenciones.append(c)
            else:
                avisos.append(f"CFDI de retenciones {c['uuid'][:8]} no es para el RFC indicado")
            continue
        if c["emisor"]["rfc"] == rfc:
            if c["emisor"]["regimen"] and c["emisor"]["regimen"] != "626" and c["tipo"] in ("I", "E"):
                avisos.append(f"{c['uuid'][:8]}: emitido con régimen {_s(c['emisor']['regimen'])}, no 626")
            if c["tipo"] == "I" and c["metodo"] == "PUE":
                mes = _mes_de_ingreso(c, avisos)
                m = meses[mes]
                m["cobrado"] += neto
                m["iva_trasladado"] += c["traslados"]["002"] * tc
                m["ret_isr"] += c["retenciones"]["001"] * tc
                m["ret_iva"] += c["retenciones"]["002"] * tc
                ret_por_cliente[(mes, c["receptor"]["rfc"])] += c["retenciones"]["001"] * tc
                etiqueta = "global" if c["receptor"]["rfc"] == RFC_PUBLICO else "PUE"
                m["detalle"].append((c["fecha"], etiqueta, c["uuid"], neto))
            elif c["tipo"] == "P":
                for p in c["pagos"]:
                    mes = p["fecha"][:7]
                    m = meses[mes]
                    m["cobrado"] += p["base"]
                    m["iva_trasladado"] += p["iva"]
                    m["ret_isr"] += p["ret_isr"]
                    m["ret_iva"] += p["ret_iva"]
                    ret_por_cliente[(mes, c["receptor"]["rfc"])] += p["ret_isr"]
                    m["detalle"].append((p["fecha"], "pago", c["uuid"], p["base"]))
                    for d in p["docs"]:
                        pagados.add(d["uuid"])
                        previo = ultimo_saldo.get(d["uuid"])
                        if previo is None or p["fecha"] >= previo[0]:
                            ultimo_saldo[d["uuid"]] = (p["fecha"], d["saldo"], d["moneda"])
                    if p["pagos10"]:
                        avisos.append(f"pago {c['uuid'][:8]} en Pagos 1.0: se tomó el monto completo como base y NO se "
                                      "calculó el IVA trasladado; sepáralos a mano con la factura PPD")
                    elif p["sin_desglose"]:
                        avisos.append(f"pago {c['uuid'][:8]} sin desglose de impuestos: se tomó el monto completo como base")
                    tope = limite_complemento(p["fecha"])
                    if date.fromisoformat(c["fecha"]) > tope:
                        avisos.append(f"complemento {c['uuid'][:8]} emitido el {c['fecha']}, después del límite "
                                      f"{tope} para el pago del {p['fecha']}")
            elif c["tipo"] == "E":
                if c["metodo"] not in ("PUE", ""):
                    avisos.append(f"nota de crédito {c['uuid'][:8]} en {c['metodo']}: el SAT solo precarga las de egreso "
                                  "PUE; revisa en qué mes restarla")
                m = meses[c["fecha"][:7]]
                m["descuentos"] += neto
                m["iva_trasladado"] -= c["traslados"]["002"] * tc
                m["ret_isr"] -= c["retenciones"]["001"] * tc
                m["ret_iva"] -= c["retenciones"]["002"] * tc
                m["detalle"].append((c["fecha"], "egreso", c["uuid"], -neto))
        elif c["receptor"]["rfc"] == rfc:
            uso = c["receptor"]["uso"]
            if c["tipo"] == "I" and c["metodo"] == "PUE":
                if es_uso_de_gasto(uso):
                    m = meses[c["fecha"][:7]]
                    m["iva_acreditable"] += c["traslados"]["002"] * tc
                    m["gastos"].append((c["fecha"], _quien(c["emisor"]), uso, c["traslados"]["002"] * tc))
                else:
                    avisos.append(f"recibida {c['uuid'][:8]} con uso {_s(uso)}: no cuenta para IVA acreditable de la actividad")
            elif c["tipo"] == "P":
                for p in c["pagos"]:
                    m = meses[p["fecha"][:7]]
                    for d in p["docs"]:
                        f = ppd_recibidas.get(d["uuid"])
                        if f is None:
                            avisos.append(f"pago {c['uuid'][:8]} de la factura {d['uuid'][:8]}, que no está en los XML: "
                                          f"IVA {d['iva']:,.2f} no acreditado; agrega la factura para saber su uso")
                        elif es_uso_de_gasto(f["receptor"]["uso"]):
                            m["iva_acreditable"] += d["iva"]
                            m["gastos"].append((p["fecha"], _quien(f["emisor"]), "pago", d["iva"]))
                        else:
                            avisos.append(f"pago de la factura {d['uuid'][:8]} con uso {_s(f['receptor']['uso'])}: no "
                                          "cuenta para IVA acreditable de la actividad")
            elif c["tipo"] == "E" and es_uso_de_gasto(uso):
                meses[c["fecha"][:7]]["iva_acreditable"] -= c["traslados"]["002"] * tc
        else:
            avisos.append(f"{_s(pathlib.Path(c['archivo']).name)}: ni emisor ni receptor es el RFC indicado")
    for r in retenciones:
        ejercicio, mes_ini, mes_fin = r["periodo"]
        mes = f"{ejercicio}-{mes_fin:02d}"
        if mes_ini != mes_fin:
            avisos.append(f"CFDI de retenciones {r['uuid'][:8]} ampara los meses {mes_ini} a {mes_fin}: se asignó a {mes}")
        if ret_por_cliente.get((mes, r["emisor"]["rfc"]), 0) > 0:
            avisos.append(f"CFDI de retenciones {r['uuid'][:8]} de {_quien(r['emisor'])} ({mes}): la retención ya está "
                          "expresada en tus facturas a ese cliente; no se sumó otra vez")
            continue
        m = meses[mes]
        m["ret_isr"] += r["retenciones"]["001"]
        m["ret_iva"] += r["retenciones"]["002"]
        m["detalle"].append((r["fecha"], "retención", r["uuid"], r["retenciones"]["001"]))
    pendientes = []
    for u, c in ppd_emitidas.items():
        if u not in pagados:
            pendientes.append({"uuid": u, "fecha": c["fecha"], "total": c["total"], "saldo": c["total"],
                               "moneda": c["moneda"], "motivo": "sin complemento"})
        elif ultimo_saldo[u][1] > 0.005:
            pendientes.append({"uuid": u, "fecha": c["fecha"], "total": c["total"], "saldo": ultimo_saldo[u][1],
                               "moneda": ultimo_saldo[u][2], "motivo": "saldo insoluto"})
    salida = OrderedDict()
    for mes in sorted(meses):
        m = meses[mes]
        anio, mm = int(mes[:4]), int(mes[5:])
        ingresos = m["cobrado"] - m["descuentos"]
        try:
            tabla = fiscal.tabla_resico(anio)
        except KeyError:
            tasa = isr = None
            avisos.append(f"{mes}: falta la tabla RESICO {anio} en parametros_mx.json; no se calculó el ISR")
        else:
            if ingresos > tabla["filas"][-1][0]:
                avisos.append(f"{mes}: ingresos de {ingresos:,.2f} rebasan el tope mensual de la tabla "
                              f"({tabla['filas'][-1][0]:,.2f}); revisa la salida del régimen (regla 3.13.5)")
            tasa = fiscal.tasa_resico(ingresos, anio) if ingresos > 0 else 0.0
            isr = ingresos * tasa
        salida[mes] = {**m, "ingresos": ingresos, "tasa": tasa, "isr": isr,
                       "isr_cargo": None if isr is None else isr - m["ret_isr"],
                       "iva_cargo": m["iva_trasladado"] - m["iva_acreditable"] - m["ret_iva"],
                       "vence": fiscal.vencimiento_mensual(anio, mm)}
    return salida, pendientes, avisos


def _n(x, fmt="{:,.2f}"):
    return "n/d" if x is None else fmt.format(x)


def _cmd_resico(a):
    cfdis, avisos = leer_varios(a.xml)
    meses, pendientes, avisos2 = resico(cfdis, a.rfc, a.excluir or [])
    hoy = date.fromisoformat(a.hoy)
    todos = OrderedDict(meses)
    if a.mes:
        meses = OrderedDict((k, v) for k, v in meses.items() if k == a.mes)
        if not meses:
            print(f"Sin CFDI que cuenten para {a.mes}: si no tuviste ingresos, la declaración se presenta en ceros.")
    if a.anio:
        ultimo = min(12, hoy.month - 1) if hoy.year == a.anio else 12
        for mm in range(1, ultimo + 1):
            meses.setdefault(f"{a.anio}-{mm:02d}", None)
        meses = OrderedDict(sorted((k, v) for k, v in meses.items() if k.startswith(str(a.anio))))
    print("| Mes | Cobrado sin IVA | Notas de crédito | Ingresos | Tasa | ISR | ISR retenido | ISR a cargo (a favor) "
          "| IVA trasladado | IVA acreditable* | IVA retenido | IVA a cargo (a favor) | Vence | Estado |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for mes, m in meses.items():
        if m is None:
            vence = fiscal.vencimiento_mensual(int(mes[:4]), int(mes[5:]))
            print(f"| {mes} | sin CFDI |  |  |  |  |  |  |  |  |  |  | {vence} | presentar en ceros |")
            continue
        estado = "vencido" if m["vence"] < hoy else "en tiempo"
        print(f"| {mes} | {m['cobrado']:,.2f} | {m['descuentos']:,.2f} | {m['ingresos']:,.2f} | "
              f"{_n(m['tasa'], '{:.2%}')} | {_n(m['isr'])} | {m['ret_isr']:,.2f} | {_n(m['isr_cargo'])} | "
              f"{m['iva_trasladado']:,.2f} | {m['iva_acreditable']:,.2f} | {m['ret_iva']:,.2f} | "
              f"{m['iva_cargo']:,.2f} | {m['vence']} | {estado} |")
    print()
    print("Negativo = saldo a favor. *IVA acreditable: candidatos de facturas recibidas con uso G o I; confirma que "
          "cada gasto sea estrictamente indispensable para tu actividad (regla 3.13.18).")
    for mes, m in meses.items():
        if not m:
            continue
        print(f"\n### Detalle {mes}")
        for fecha, etiqueta, uuid, monto in sorted(m["detalle"]):
            print(f"- {fecha} {etiqueta:9} {uuid[:8]}… {monto:,.2f}")
        for fecha, emisor, uso, iva in sorted(m["gastos"]):
            print(f"- {fecha} gasto     {_s(emisor)} ({_s(uso)}) IVA {iva:,.2f}")
    if pendientes:
        print("\n### Facturas PPD sin cobrar por completo")
        for p in pendientes:
            print(f"- {p['fecha']} {p['uuid'][:8]}… total {p['total']:,.2f}; {p['motivo']} {p['saldo']:,.2f} "
                  f"{_s(p['moneda'])}. Si ya la cobraste, búscala en el portal antes de emitir otro complemento "
                  "(vence el día 5 del mes siguiente al cobro); sin complemento, el SAT no la precarga como cobrada.")
    print()
    por_anio = defaultdict(float)
    for mes, m in todos.items():
        por_anio[mes[:4]] += m["ingresos"]
    for anio, total in sorted(por_anio.items()):
        try:
            tope = fiscal.tabla_resico(int(anio))["tope_anual"]
        except KeyError:
            tope = None
        alerta = f"  ¡EXCEDE el tope RESICO de ${tope:,.0f}! (regla 3.13.5)" if tope and total > tope else ""
        print(f"- Ingresos {anio} en estos XML: {total:,.2f}{alerta}. Con sueldo o intereses, el tope se mide en conjunto.")
    for x in avisos + avisos2:
        print(f"- {_s(x)}")
    print("- Pasa los XML de todo el ejercicio: un complemento emitido del 1 al 5 del mes siguiente cuenta en el mes del "
          "pago. Los XML no dicen si un CFDI fue cancelado: confírmalo en el portal y pásalo con --excluir UUID.")


# ---------- nómina ----------

def nomina(cfdis):
    """(filas por (año de pago, RFC del patrón, nombre), totales por año, alertas). Ignora lo que no es nómina."""
    filas = defaultdict(lambda: defaultdict(float))
    alertas = []
    for c in cfdis:
        n = c["nomina"]
        if c["tipo"] != "N" or n is None:
            continue
        anio = (n["fecha_pago"] or c["fecha"])[:4]
        f = filas[(anio, c["emisor"]["rfc"], c["emisor"]["nombre"])]
        f["recibos"] += 1
        f["gravado_acumulable"] += n["gravado"] - n["separacion_gravada"]
        f["separacion"] += n["separacion_gravada"]
        for k in ("gravado", "exento", "isr", "subsidio", "aguinaldo_exento", "ptu_exento", "prima_vac_exento"):
            f[k] += n[k]
        f["extraordinaria"] += n["tipo"] == "E"
        if n["separacion_gravada"] or n["separacion"] or n["jubilacion"]:
            alertas.append(f"{anio} {_quien(c['emisor'])}: indemnización, separación o jubilación en una exhibición en "
                           f"{c['uuid'][:8]}; se grava por el art. 95 (último sueldo mensual ordinario), no se sumó al "
                           "gravado acumulable, obliga a declarar y no entra al relevo de la anual")
    por_anio = defaultdict(lambda: defaultdict(float))
    for (anio, _, _), f in filas.items():
        t = por_anio[anio]
        t["patrones"] += 1
        for k in ("gravado", "gravado_acumulable", "separacion", "exento", "isr", "subsidio", "aguinaldo_exento",
                  "ptu_exento", "prima_vac_exento"):
            t[k] += f[k]
    uma = fiscal.PARAMS["uma_diaria"]["valores"]
    for anio, t in sorted(por_anio.items()):
        t["ingresos_totales"] = t["gravado"] + t["exento"]
        t["obligado_400k"] = t["ingresos_totales"] > 400_000
        t["dos_patrones"] = t["patrones"] > 1
        u = uma.get(anio)
        if u is None:
            alertas.append(f"{anio}: falta la UMA {anio} en parametros_mx.json: no se revisaron los topes de aguinaldo, "
                           "prima vacacional y PTU")
        else:
            for clave, veces, nombre in (("aguinaldo_exento", 30, "aguinaldo"), ("prima_vac_exento", 15, "prima vacacional"),
                                         ("ptu_exento", 15, "PTU")):
                tope = veces * u
                if t[clave] > tope + 0.01:
                    alertas.append(f"{anio}: {nombre} exento {t[clave]:,.2f} rebasa el tope anual de {veces} UMA "
                                   f"({tope:,.2f}); el exceso de {t[clave] - tope:,.2f} se gravaría (criterio "
                                   "conservador: confírmalo contra la precarga)")
        if t["dos_patrones"] and t["subsidio"] > 0:
            alertas.append(f"{anio}: hubo subsidio para el empleo con más de un patrón ({t['subsidio']:,.2f}); el SAT lo "
                           f"disminuye del ISR retenido. Estima con --retenido {t['isr'] - t['subsidio']:.2f}")
    return filas, por_anio, alertas


def _cmd_nomina(a):
    cfdis, avisos = leer_varios(a.xml)
    filas, por_anio, alertas = nomina(cfdis)
    print("| Año | Patrón | Recibos | Extraord. | Gravado acumulable | Separación (art. 95) | Exento | ISR retenido | "
          "Subsidio entregado |")
    print("|---|---|---|---|---|---|---|---|---|")
    for (anio, rfc, nombre), f in sorted(filas.items()):
        print(f"| {anio} | {_s(nombre) or mascara_rfc(rfc)} | {int(f['recibos'])} | {int(f['extraordinaria'])} | "
              f"{f['gravado_acumulable']:,.2f} | {f['separacion']:,.2f} | {f['exento']:,.2f} | {f['isr']:,.2f} | "
              f"{f['subsidio']:,.2f} |")
    print()
    for anio, t in sorted(por_anio.items()):
        print(f"- {anio}: {int(t['patrones'])} patrón(es); ingresos totales {t['ingresos_totales']:,.2f} (gravado más "
              f"exento); gravado acumulable {t['gravado_acumulable']:,.2f}; ISR retenido {t['isr']:,.2f}.")
        print(f"  Siguiente paso: fiscal_mx.py anual --ejercicio {anio} --gravado {t['gravado_acumulable']:.2f} "
              f"--retenido {t['isr']:.2f} (resta antes las deducciones personales válidas).")
        if t["dos_patrones"]:
            print("  - Dos o más patrones: obligado a declarar (LISR art. 98, fr. III, c) si fueron simultáneos o dejó "
                  "uno antes del 31/12.")
        if t["obligado_400k"]:
            print("  - Ingresos por sueldos de más de $400,000: obligado a declarar (art. 98, fr. III, e).")
        elif t["ingresos_totales"] > 380_000:
            print("  - Cerca de $400,000: revisa con el recibo de diciembre y el Visor si se rebasa.")
    for x in alertas + avisos:
        print(f"- {_s(x)}")
    print("- Los XML no dicen si un recibo fue cancelado: cuadra contra el Visor de nómina del SAT.")


# ---------- deducciones ----------

ETIQUETAS_D = {"D01": "Honorarios médicos, dentales y hospitalarios", "D02": "Gastos médicos por incapacidad",
               "D03": "Gastos funerales", "D04": "Donativos", "D05": "Intereses reales hipotecarios",
               "D06": "Aportaciones voluntarias al SAR", "D07": "Primas de seguros de gastos médicos",
               "D08": "Transportación escolar obligatoria", "D09": "Depósitos en cuentas de ahorro / planes de pensiones",
               "D10": "Colegiaturas"}
FUERA_DEL_TOPE_GLOBAL = {"D02", "D06", "D09", "D10"}


def _leer_69b(ruta):
    """RFC -> situación desde el CSV público del SAT (Listado_Completo_69-B.csv). Tolera encabezados previos."""
    situacion = {}
    with open(ruta, newline="", encoding="latin-1") as f:
        for fila in csv.reader(f):
            if len(fila) >= 4 and re.fullmatch(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}", fila[1].strip().upper()):
                situacion[fila[1].strip().upper()] = fila[3].strip()
    return situacion


def deducciones(cfdis, rfc, ejercicio, lista_69b=None):
    rfc = rfc.upper()
    revisadas, otras = [], 0
    for c in cfdis:
        r = c["receptor"]
        if c["tipo"] != "I" or not r["uso"].startswith("D"):
            if r["rfc"] == rfc and c["tipo"] == "I":
                otras += 1
            continue
        problemas = []
        if r["rfc"] != rfc:
            problemas.append("no está a tu RFC")
        if not c["version"].startswith("3") and r["regimen"] not in REG_DEDUCCIONES:
            problemas.append(f"régimen {_s(r['regimen'])} no admite {_s(r['uso'])}: pide reexpedirla con 605 "
                             "(u otro régimen de deducciones que tengas)")
        if c["forma"] == "01":
            problemas.append("pagada en efectivo: el SAT exige transferencia, tarjeta o cheque nominativo")
        elif c["metodo"] == "PPD":
            problemas.append("PPD: la deducción vale con el complemento de pago; revisa forma y fecha del pago")
        if c["fecha"][:4] != str(ejercicio):
            problemas.append(f"fecha {c['fecha']} fuera del ejercicio {ejercicio}")
        if r["uso"] == "D10" and not c["colegiaturas"]:
            problemas.append("colegiatura sin complemento de instituciones educativas (CURP del alumno y RVOE)")
        if lista_69b and c["emisor"]["rfc"] in lista_69b:
            problemas.append(f"emisor en lista 69-B ({_s(lista_69b[c['emisor']['rfc']])})")
        revisadas.append((c, problemas))
    return revisadas, otras


def resumen_deducciones(revisadas, ejercicio, ingresos=None):
    """Totales aplicables: colegiaturas topadas por alumno y nivel; tope global (5 UMA anuales o 15% de ingresos)."""
    por_uso, colegiaturas, avisos = defaultdict(float), defaultdict(float), []
    topes = {normalizar_nombre(k): v for k, v in fiscal.PARAMS["colegiaturas_tope_anual"]["por_alumno"].items()}
    for c, problemas in revisadas:
        if problemas:
            continue
        monto = c["total"] * c["tipo_cambio"]
        uso = c["receptor"]["uso"]
        por_uso[uso] += monto
        if uso == "D10":
            alumno = c["colegiaturas"][0]
            colegiaturas[(alumno["curp"], normalizar_nombre(alumno["nivel"]))] += monto
    aplicable_col = 0.0
    for (curp, nivel), total in colegiaturas.items():
        tope = topes.get(nivel)
        if tope is None:
            avisos.append(f"colegiatura con nivel '{_s(nivel)}' sin tope conocido: no se topó")
            aplicable_col += total
        else:
            aplicable_col += min(total, tope)
            if total > tope:
                avisos.append(f"colegiaturas de un alumno de {nivel.lower()}: {total:,.2f}, tope anual {tope:,.2f}")
    dentro = sum(v for k, v in por_uso.items() if k not in FUERA_DEL_TOPE_GLOBAL)
    tope_global = aplicable_global = None
    uma = fiscal.PARAMS["uma_diaria"]["valores"].get(str(ejercicio))
    if uma is None:
        avisos.append(f"!! falta la UMA {ejercicio} en parametros_mx.json: no se aplicó el tope global")
    elif ingresos:
        uma_anual = round(round(uma * 30.4, 2) * 12, 2)  # INEGI: mensual = diaria x 30.4; anual = mensual x 12
        tope_global = min(5 * uma_anual, 0.15 * ingresos)
        aplicable_global = min(dentro, tope_global)
    return {"por_uso": dict(por_uso), "colegiaturas": aplicable_col, "dentro_del_tope": dentro,
            "tope_global": tope_global, "aplicable_global": aplicable_global, "avisos": avisos}


def _cmd_deducciones(a):
    cfdis, avisos = leer_varios(a.xml)
    lista = _leer_69b(a.lista_69b) if a.lista_69b else None
    revisadas, otras = deducciones(cfdis, a.rfc, a.ejercicio, lista)
    print("| Archivo | Fecha | Emisor | Uso | Régimen | Forma | Total | Resultado |")
    print("|---|---|---|---|---|---|---|---|")
    for c, problemas in revisadas:
        print(f"| {_s(pathlib.Path(c['archivo']).name)} | {c['fecha']} | {_quien(c['emisor'])} | {_s(c['receptor']['uso'])} | "
              f"{_s(c['receptor']['regimen'])} | {_s(c['forma'])} | {c['total']:,.2f} | "
              f"{'OK' if not problemas else '; '.join(problemas)} |")
    print()
    r = resumen_deducciones(revisadas, a.ejercicio, a.ingresos)
    for uso in sorted(r["por_uso"]):
        print(f"- {uso} {ETIQUETAS_D.get(uso, '')}: {r['por_uso'][uso]:,.2f}")
    if r["colegiaturas"]:
        print(f"- Colegiaturas aplicables (tope por alumno y nivel, fuera del tope global): {r['colegiaturas']:,.2f}")
    if r["tope_global"] is not None:
        print(f"- Sujetas al tope global: {r['dentro_del_tope']:,.2f}; tope = menor de 5 UMA anuales y 15% de ingresos "
              f"= {r['tope_global']:,.2f}; aplicable: {r['aplicable_global']:,.2f}")
    elif not a.ingresos:
        print("- Pasa --ingresos <total del año, incluidos exentos> para aplicar el tope global (5 UMA o 15%).")
    print("- Topes propios que la herramienta no ve: lentes ópticos $2,500, funerales 1 UMA anual, donativos 7%, "
          "aportaciones voluntarias de retiro (10% del ingreso, máximo 5 UMA). Dependientes: ingresos menores a 1 UMA anual.")
    if otras:
        print(f"- {otras} factura(s) a tu RFC con uso distinto de D01-D10: no cuentan como deducción personal.")
    for x in r["avisos"] + avisos:
        print(f"- {_s(x)}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ver", help="resumen de uno o varios XML")
    s.add_argument("xml", nargs="+")
    s.add_argument("--sin-mascara", action="store_true")
    s.set_defaults(f=_cmd_ver)
    s = sub.add_parser("verificar", help="receptor de cada XML contra tu configuración (sale con 1 o 2 si no cuadra)")
    s.add_argument("xml", nargs="+")
    s.add_argument("--config", required=True, help="JSON con bloque receptor (ver ejemplos/autofactura.ejemplo.json)")
    s.add_argument("--perfil", help="perfil de la configuración (p. ej. actividad, medicos)")
    s.set_defaults(f=_cmd_verificar)
    s = sub.add_parser("resico", help="ISR e IVA mensual de RESICO PF desde XML emitidos y recibidos")
    s.add_argument("xml", nargs="+", help="todos los XML del ejercicio (emitidos, recibidos, pagos y retenciones)")
    s.add_argument("--rfc", required=True, help="tu RFC (para separar emitidos de recibidos)")
    s.add_argument("--mes", help="AAAA-MM para ver solo un mes")
    s.add_argument("--anio", type=int, help="muestra todos los meses del año, también los que no tienen CFDI")
    s.add_argument("--excluir", nargs="*", help="UUID cancelados")
    s.add_argument("--hoy", default=date.today().isoformat())
    s.set_defaults(f=_cmd_resico)
    s = sub.add_parser("nomina", help="totales de recibos de nómina por año y patrón")
    s.add_argument("xml", nargs="+")
    s.set_defaults(f=_cmd_nomina)
    s = sub.add_parser("deducciones", help="revisa facturas de deducciones personales")
    s.add_argument("xml", nargs="+")
    s.add_argument("--rfc", required=True)
    s.add_argument("--ejercicio", type=int, required=True)
    s.add_argument("--ingresos", type=float, help="ingresos totales del año, incluidos exentos (tope del 15%%)")
    s.add_argument("--lista-69b", help="CSV público del SAT con el listado 69-B")
    s.set_defaults(f=_cmd_deducciones)
    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main(sys.argv[1:])
