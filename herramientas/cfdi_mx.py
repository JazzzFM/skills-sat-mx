"""Lectura local de CFDI (XML 4.0 y 3.3) para personas físicas, sin dependencias externas.

Subcomandos (`python3 -I herramientas/cfdi_mx.py <subcomando> --help`):
  ver          Resume uno o varios XML: tipo, fecha, emisor, receptor, totales e impuestos.
  verificar    Compara el receptor de cada XML contra tu configuración (después de una autofactura).
  resico       Ingresos cobrados, ISR e IVA por mes para RESICO PF, desde tus XML emitidos y recibidos.
  nomina       Suma recibos de nómina por año y patrón: gravado, exento, ISR retenido, subsidio.
  deducciones  Revisa si tus facturas de gastos personales cumplen los requisitos de la anual.

Los XML se tratan como datos no confiables: solo se leen atributos. El RFC de persona física se enmascara en
la salida salvo con --sin-mascara. Nada sale de tu equipo.
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
from datetime import date, timedelta

_AQUI = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("fiscal_mx", _AQUI / "fiscal_mx.py")
fiscal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fiscal)

NS_CFDI = ("http://www.sat.gob.mx/cfd/4", "http://www.sat.gob.mx/cfd/3")
NS_TFD = "http://www.sat.gob.mx/TimbreFiscalDigital"
NS_PAGOS20 = "http://www.sat.gob.mx/Pagos20"
NS_PAGOS10 = "http://www.sat.gob.mx/Pagos"
NS_NOMINA = "http://www.sat.gob.mx/nomina12"
NS_IEDU = "http://www.sat.gob.mx/iedu"
RFC_PUBLICO = "XAXX010101000"

# Catálogo c_UsoCFDI del SAT (versión del 15/10/2026): regímenes de receptor admitidos por cada uso.
REG_DEDUCCIONES = {"605", "606", "607", "608", "611", "612", "614", "615", "625"}
REG_GASTOS = {"601", "603", "606", "612", "620", "621", "622", "623", "624", "625", "626"}


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


# ---------- utilidades ----------

def _f(valor, defecto=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


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


def _hijo(el, nombre, ns):
    return None if el is None else el.find(f"{{{ns}}}{nombre}")


def _hijos(el, nombre, ns):
    return [] if el is None else el.findall(f"{{{ns}}}{nombre}")


# ---------- lectura ----------

def leer(ruta):
    """Devuelve un dict con los datos fiscales de un CFDI. Lanza ValueError si no es un CFDI."""
    datos = pathlib.Path(ruta).read_bytes().lstrip(b"\xef\xbb\xbf \t\r\n")
    raiz = ET.fromstring(datos)
    ns = raiz.tag[1:].split("}")[0] if raiz.tag.startswith("{") else ""
    if ns not in NS_CFDI or not raiz.tag.endswith("Comprobante"):
        raise ValueError(f"{ruta}: no es un CFDI 3.3/4.0")
    a = raiz.attrib
    tc = _f(a.get("TipoCambio"), 1.0) or 1.0
    emisor, receptor = _hijo(raiz, "Emisor", ns), _hijo(raiz, "Receptor", ns)
    tfd = raiz.find(f".//{{{NS_TFD}}}TimbreFiscalDigital")
    c = {
        "archivo": str(ruta),
        "version": a.get("Version", ""),
        "tipo": a.get("TipoDeComprobante", ""),
        "fecha": a.get("Fecha", "")[:10],
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
        "traslados": defaultdict(float),
        "retenciones": defaultdict(float),
        "pagos": [],
        "nomina": None,
        "colegiatura": raiz.find(f".//{{{NS_IEDU}}}instEducativas") is not None,
    }
    imp = _hijo(raiz, "Impuestos", ns)  # solo el nodo del comprobante, no el de cada concepto
    for t in _hijos(_hijo(imp, "Traslados", ns), "Traslado", ns):
        c["traslados"][t.get("Impuesto", "")] += _f(t.get("Importe"))
    for r in _hijos(_hijo(imp, "Retenciones", ns), "Retencion", ns):
        c["retenciones"][r.get("Impuesto", "")] += _f(r.get("Importe"))
    c["pagos"] = _leer_pagos(raiz)
    c["nomina"] = _leer_nomina(raiz)
    return c


def _leer_pagos(raiz):
    pagos = []
    for p in raiz.iter(f"{{{NS_PAGOS20}}}Pago"):
        tc = _f(p.get("TipoCambioP"), 1.0) or 1.0
        base_iva = iva = ret_isr = ret_iva = 0.0
        hay_iva = False
        imp = _hijo(p, "ImpuestosP", NS_PAGOS20)
        for t in _hijos(_hijo(imp, "TrasladosP", NS_PAGOS20), "TrasladoP", NS_PAGOS20):
            if t.get("ImpuestoP") == "002":
                hay_iva = True
                base_iva += _f(t.get("BaseP"))
                iva += _f(t.get("ImporteP"))
        for r in _hijos(_hijo(imp, "RetencionesP", NS_PAGOS20), "RetencionP", NS_PAGOS20):
            if r.get("ImpuestoP") == "001":
                ret_isr += _f(r.get("ImporteP"))
            elif r.get("ImpuestoP") == "002":
                ret_iva += _f(r.get("ImporteP"))
        monto = _f(p.get("Monto"))
        pagos.append({"fecha": p.get("FechaPago", "")[:10], "moneda": p.get("MonedaP", "MXN"), "tc": tc,
                      "monto": monto * tc, "base": (base_iva if hay_iva else monto) * tc, "iva": iva * tc,
                      "ret_isr": ret_isr * tc, "ret_iva": ret_iva * tc, "sin_desglose": not hay_iva,
                      "docs": [d.get("IdDocumento", "").upper() for d in _hijos(p, "DoctoRelacionado", NS_PAGOS20)]})
    for p in raiz.iter(f"{{{NS_PAGOS10}}}Pago"):  # Pagos 1.0 (2022 y antes): sin desglose de impuestos
        tc = _f(p.get("TipoCambioP"), 1.0) or 1.0
        monto = _f(p.get("Monto")) * tc
        pagos.append({"fecha": p.get("FechaPago", "")[:10], "moneda": p.get("MonedaP", "MXN"), "tc": tc,
                      "monto": monto, "base": monto, "iva": 0.0, "ret_isr": 0.0, "ret_iva": 0.0,
                      "sin_desglose": True,
                      "docs": [d.get("IdDocumento", "").upper() for d in _hijos(p, "DoctoRelacionado", NS_PAGOS10)]})
    return pagos


def _leer_nomina(raiz):
    n = raiz.find(f".//{{{NS_NOMINA}}}Nomina")
    if n is None:
        return None
    per = _hijo(n, "Percepciones", NS_NOMINA)
    exentos = defaultdict(float)
    for p in _hijos(per, "Percepcion", NS_NOMINA):
        exentos[p.get("TipoPercepcion", "")] += _f(p.get("ImporteExento"))
    isr = sum(_f(d.get("Importe")) for d in _hijos(_hijo(n, "Deducciones", NS_NOMINA), "Deduccion", NS_NOMINA)
              if d.get("TipoDeduccion") == "002")
    subsidio = 0.0
    for o in _hijos(_hijo(n, "OtrosPagos", NS_NOMINA), "OtroPago", NS_NOMINA):
        if o.get("TipoOtroPago") == "002":
            subsidio += _f(o.get("Importe"))
    return {"tipo": n.get("TipoNomina", ""), "fecha_pago": n.get("FechaPago", "")[:10],
            "gravado": _f(per.get("TotalGravado")) if per is not None else 0.0,
            "exento": _f(per.get("TotalExento")) if per is not None else 0.0,
            "isr": isr, "subsidio": subsidio,
            "aguinaldo_exento": exentos["002"], "ptu_exento": exentos["003"], "prima_vac_exento": exentos["021"],
            "separacion": _f(per.get("TotalSeparacionIndemnizacion")) if per is not None else 0.0,
            "jubilacion": _f(per.get("TotalJubilacionPensionRetiro")) if per is not None else 0.0}


def leer_varios(rutas):
    """Lee varios XML, descarta los que no son CFDI y deduplica por UUID (descargas repetidas)."""
    vistos, salida, avisos = set(), [], []
    for r in rutas:
        try:
            c = leer(r)
        except (ValueError, ET.ParseError, OSError) as e:
            avisos.append(f"ignorado {r}: {e}")
            continue
        clave = c["uuid"] or c["archivo"]
        if clave in vistos:
            avisos.append(f"duplicado {r} (UUID {c['uuid']})")
            continue
        vistos.add(clave)
        salida.append(c)
    return salida, avisos


# ---------- ver ----------

def _cmd_ver(a):
    cfdis, avisos = leer_varios(a.xml)
    m = (lambda x: x) if a.sin_mascara else mascara_rfc
    print("| Archivo | Tipo | Fecha | UUID | Emisor | Receptor | Régimen/Uso | Método/Forma | SubTotal | IVA | Ret ISR | Total |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in cfdis:
        print(f"| {pathlib.Path(c['archivo']).name} | {c['tipo']} | {c['fecha']} | {c['uuid'][:8]}… | "
              f"{m(c['emisor']['rfc'])} {c['emisor']['nombre']} | {m(c['receptor']['rfc'])} {c['receptor']['nombre']} | "
              f"{c['receptor']['regimen']}/{c['receptor']['uso']} | {c['metodo']}/{c['forma']} | {c['subtotal']:,.2f} | "
              f"{c['traslados']['002']:,.2f} | {c['retenciones']['001']:,.2f} | {c['total']:,.2f} {c['moneda']} |")
    for x in avisos:
        print(f"- {x}")


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
    """Lista de problemas del receptor de un CFDI frente a los datos esperados (vacía si todo cuadra)."""
    r, problemas = c["receptor"], []
    if c["tipo"] != "I":
        problemas.append(f"tipo {c['tipo']} (se esperaba I, ingreso)")
    if r["rfc"] != esperado.get("rfc", "").upper():
        problemas.append("RFC del receptor distinto")
    if esperado.get("nombre"):
        if normalizar_nombre(r["nombre"]) != normalizar_nombre(esperado["nombre"]):
            problemas.append(f"nombre del receptor '{r['nombre']}'")
        elif r["nombre"] != esperado["nombre"]:
            problemas.append(f"nombre difiere solo en acentos o espacios: '{r['nombre']}'")
    if esperado.get("cp") and r["cp"] != esperado["cp"]:
        problemas.append(f"código postal {r['cp']}")
    if esperado.get("regimen") and r["regimen"] != esperado["regimen"]:
        problemas.append(f"régimen {r['regimen']} (se esperaba {esperado['regimen']})")
    if esperado.get("uso") and r["uso"] != esperado["uso"]:
        problemas.append(f"uso {r['uso']} (se esperaba {esperado['uso']})")
    admitidos = regimenes_admitidos(r["uso"])
    if admitidos is not None and r["regimen"] not in admitidos:
        problemas.append(f"el catálogo no admite uso {r['uso']} con régimen {r['regimen']}")
    return problemas


def _cmd_verificar(a):
    esperado = cargar_receptor(a.config, a.perfil)
    cfdis, avisos = leer_varios(a.xml)
    malos = 0
    for c in cfdis:
        problemas = verificar(c, esperado)
        estado = "OK" if not problemas else "REVISAR: " + "; ".join(problemas)
        malos += bool(problemas)
        print(f"== {pathlib.Path(c['archivo']).name}: {estado}")
        print(f"   UUID {c['uuid']} | {c['fecha']} | emisor {c['emisor']['rfc']} {c['emisor']['nombre']} | "
              f"total {c['total']:,.2f} {c['moneda']} | {c['metodo']} forma {c['forma']} | "
              f"receptor {mascara_rfc(c['receptor']['rfc'])} {c['receptor']['regimen']}/{c['receptor']['uso']}")
    for x in avisos:
        print(f"- {x}")
    if malos:
        print(f"!! {malos} CFDI con receptor incorrecto: no los archives; pide al comercio cancelar y reexpedir.",
              file=sys.stderr)
        sys.exit(1)


# ---------- resico ----------

def tasa_resico(ingreso):
    for limite, tasa in fiscal.PARAMS["resico_pf_mensual"]["filas"]:
        if ingreso <= limite:
            return tasa
    raise ValueError("Ingreso mensual por encima del tope RESICO de $3,500,000")


def limite_complemento(fecha_pago):
    """Quinto día natural del mes siguiente al pago (RMF 2026 regla 2.7.1.32)."""
    d = date.fromisoformat(fecha_pago)
    a, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(a, m, 5)


def resico(cfdis, rfc, excluir=()):
    """Agrupa por mes lo que el SAT precarga en la declaración RESICO PF y lo que falta para cuadrarla.

    Ingresos cobrados = facturas de ingreso PUE del mes + pagos (complemento 2.0) con FechaPago en el mes, sin
    IVA; se restan las notas de crédito (egreso) PUE del mes. Las PPD sin complemento no cuentan como cobradas.
    IVA acreditable: candidatos de facturas recibidas con uso de gasto (G/I); se debe revisar que el gasto
    sea deducible (RMF 2026 regla 3.13.18).
    """
    rfc = rfc.upper()
    excluir = {u.upper() for u in excluir}
    meses = defaultdict(lambda: {"cobrado": 0.0, "descuentos": 0.0, "iva_trasladado": 0.0, "ret_isr": 0.0,
                                 "ret_iva": 0.0, "iva_acreditable": 0.0, "detalle": [], "gastos": []})
    ppd, pagados, avisos = {}, set(), []
    for c in cfdis:
        if c["uuid"] in excluir:
            avisos.append(f"excluido por cancelado: {c['uuid']}")
            continue
        tc = c["tipo_cambio"]
        neto = (c["subtotal"] - c["descuento"]) * tc
        if c["emisor"]["rfc"] == rfc:
            if c["emisor"]["regimen"] and c["emisor"]["regimen"] != "626" and c["tipo"] in ("I", "E"):
                avisos.append(f"{c['uuid'][:8]}: emitido con régimen {c['emisor']['regimen']}, no 626")
            if c["tipo"] == "I" and c["metodo"] == "PUE":
                m = meses[c["fecha"][:7]]
                m["cobrado"] += neto
                m["iva_trasladado"] += c["traslados"]["002"] * tc
                m["ret_isr"] += c["retenciones"]["001"] * tc
                m["ret_iva"] += c["retenciones"]["002"] * tc
                etiqueta = "global" if c["receptor"]["rfc"] == RFC_PUBLICO else "PUE"
                m["detalle"].append((c["fecha"], etiqueta, c["uuid"], neto))
            elif c["tipo"] == "I" and c["metodo"] == "PPD":
                ppd[c["uuid"]] = c
            elif c["tipo"] == "P":
                for p in c["pagos"]:
                    m = meses[p["fecha"][:7]]
                    m["cobrado"] += p["base"]
                    m["iva_trasladado"] += p["iva"]
                    m["ret_isr"] += p["ret_isr"]
                    m["ret_iva"] += p["ret_iva"]
                    m["detalle"].append((p["fecha"], "pago", c["uuid"], p["base"]))
                    pagados.update(p["docs"])
                    if p["sin_desglose"]:
                        avisos.append(f"pago {c['uuid'][:8]} sin desglose de IVA: se tomó el monto completo como base")
                    tope = limite_complemento(p["fecha"])
                    if c["fecha"] and date.fromisoformat(c["fecha"]) > tope:
                        avisos.append(f"complemento {c['uuid'][:8]} emitido el {c['fecha']}, después del límite "
                                      f"{tope} para el pago del {p['fecha']}")
            elif c["tipo"] == "E":
                if c["metodo"] != "PUE":
                    avisos.append(f"nota de crédito {c['uuid'][:8]} en {c['metodo'] or 'sin método'}: el SAT solo "
                                  "precarga las de egreso PUE; revisa en qué mes restarla")
                m = meses[c["fecha"][:7]]
                m["descuentos"] += neto
                m["iva_trasladado"] -= c["traslados"]["002"] * tc
                m["detalle"].append((c["fecha"], "egreso", c["uuid"], -neto))
        elif c["receptor"]["rfc"] == rfc:
            uso = c["receptor"]["uso"]
            es_gasto = uso.startswith("G") or uso.startswith("I")
            if c["tipo"] == "I" and c["metodo"] == "PUE" and es_gasto:
                m = meses[c["fecha"][:7]]
                m["iva_acreditable"] += c["traslados"]["002"] * tc
                m["gastos"].append((c["fecha"], c["emisor"]["nombre"] or c["emisor"]["rfc"], uso,
                                    c["traslados"]["002"] * tc))
            elif c["tipo"] == "P":
                for p in c["pagos"]:
                    m = meses[p["fecha"][:7]]
                    m["iva_acreditable"] += p["iva"]
                    m["gastos"].append((p["fecha"], c["emisor"]["nombre"] or c["emisor"]["rfc"], "pago", p["iva"]))
            elif c["tipo"] == "E" and es_gasto:
                m = meses[c["fecha"][:7]]
                m["iva_acreditable"] -= c["traslados"]["002"] * tc
            elif c["tipo"] == "I" and not es_gasto:
                avisos.append(f"recibida {c['uuid'][:8]} con uso {uso}: no cuenta para IVA acreditable de la actividad")
        else:
            avisos.append(f"{pathlib.Path(c['archivo']).name}: ni emisor ni receptor es el RFC indicado")
    sin_complemento = [c for u, c in ppd.items() if u not in pagados]
    salida = OrderedDict()
    for mes in sorted(meses):
        m = meses[mes]
        ingresos = m["cobrado"] - m["descuentos"]
        tasa = tasa_resico(ingresos) if ingresos > 0 else 0.0
        isr = ingresos * tasa if ingresos > 0 else 0.0
        anio, mm = int(mes[:4]), int(mes[5:])
        salida[mes] = {**m, "ingresos": ingresos, "tasa": tasa, "isr": isr, "isr_cargo": isr - m["ret_isr"],
                       "iva_cargo": m["iva_trasladado"] - m["iva_acreditable"] - m["ret_iva"],
                       "vence": fiscal.vencimiento_mensual(anio, mm)}
    return salida, sin_complemento, avisos


def _cmd_resico(a):
    cfdis, avisos = leer_varios(a.xml)
    meses, sin_comp, avisos2 = resico(cfdis, a.rfc, a.excluir or [])
    hoy = date.fromisoformat(a.hoy)
    if a.mes:
        meses = OrderedDict((k, v) for k, v in meses.items() if k == a.mes)
    print("| Mes | Cobrado sin IVA | Notas de crédito | Ingresos | Tasa | ISR | ISR retenido PM | ISR a cargo (a favor) "
          "| IVA trasladado | IVA acreditable* | IVA retenido | IVA a cargo (a favor) | Vence | Estado |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    por_anio = defaultdict(float)
    for mes, m in meses.items():
        estado = "vencido" if m["vence"] < hoy else "en tiempo"
        print(f"| {mes} | {m['cobrado']:,.2f} | {m['descuentos']:,.2f} | {m['ingresos']:,.2f} | {m['tasa']:.2%} | "
              f"{m['isr']:,.2f} | {m['ret_isr']:,.2f} | {m['isr_cargo']:,.2f} | {m['iva_trasladado']:,.2f} | "
              f"{m['iva_acreditable']:,.2f} | {m['ret_iva']:,.2f} | {m['iva_cargo']:,.2f} | {m['vence']} | {estado} |")
        por_anio[mes[:4]] += m["ingresos"]
    print()
    print("Negativo = saldo a favor. *IVA acreditable: candidatos de facturas recibidas con uso G o I; confirma que "
          "cada gasto sea estrictamente indispensable para tu actividad (regla 3.13.18).")
    for mes, m in meses.items():
        print(f"\n### Detalle {mes}")
        for fecha, etiqueta, uuid, monto in sorted(m["detalle"]):
            print(f"- {fecha} {etiqueta:7} {uuid[:8]}… {monto:,.2f}")
        for fecha, emisor, uso, iva in sorted(m["gastos"]):
            print(f"- {fecha} gasto   {emisor} ({uso}) IVA {iva:,.2f}")
    if sin_comp:
        print("\n### Facturas PPD sin complemento de pago")
        for c in sin_comp:
            print(f"- {c['fecha']} {c['uuid'][:8]}… total {c['total']:,.2f}: si ya la cobraste, emite el complemento "
                  "(vence el día 5 del mes siguiente al cobro). Mientras no exista, el SAT no la precarga como cobrada.")
    print()
    for anio, total in por_anio.items():
        alerta = "  ¡EXCEDE el tope RESICO de $3,500,000!" if total > 3_500_000 else ""
        print(f"- Ingresos {anio} en estos XML: {total:,.2f}{alerta}")
    for x in avisos + avisos2:
        print(f"- {x}")
    print("- Los XML no dicen si un CFDI fue cancelado: confírmalo en el portal y pásalo con --excluir UUID.")


# ---------- nómina ----------

def nomina(cfdis):
    """Totales por (año de pago, RFC del patrón). Ignora CFDI que no son de nómina."""
    filas = defaultdict(lambda: defaultdict(float))
    alertas = []
    for c in cfdis:
        n = c["nomina"]
        if c["tipo"] != "N" or n is None:
            continue
        anio = (n["fecha_pago"] or c["fecha"])[:4]
        f = filas[(anio, c["emisor"]["rfc"], c["emisor"]["nombre"])]
        f["recibos"] += 1
        for k in ("gravado", "exento", "isr", "subsidio", "aguinaldo_exento", "ptu_exento", "prima_vac_exento"):
            f[k] += n[k]
        f["extraordinaria"] += n["tipo"] == "E"
        if n["separacion"] or n["jubilacion"]:
            alertas.append(f"{anio} {c['emisor']['nombre']}: indemnización o jubilación en {c['uuid'][:8]}; "
                           "obliga a declarar y no entra al relevo de la anual")
    return filas, alertas


def _cmd_nomina(a):
    cfdis, avisos = leer_varios(a.xml)
    filas, alertas = nomina(cfdis)
    print("| Año | Patrón | Recibos | Extraord. | Gravado | Exento | ISR retenido | Subsidio entregado |")
    print("|---|---|---|---|---|---|---|---|")
    por_anio = defaultdict(lambda: defaultdict(float))
    for (anio, rfc, nombre), f in sorted(filas.items()):
        print(f"| {anio} | {nombre or rfc} | {int(f['recibos'])} | {int(f['extraordinaria'])} | {f['gravado']:,.2f} | "
              f"{f['exento']:,.2f} | {f['isr']:,.2f} | {f['subsidio']:,.2f} |")
        t = por_anio[anio]
        t["patrones"] += 1
        for k in ("gravado", "isr", "aguinaldo_exento", "ptu_exento", "prima_vac_exento"):
            t[k] += f[k]
    print()
    uma = fiscal.PARAMS["uma_diaria"]["valores"]
    for anio, t in sorted(por_anio.items()):
        linea = (f"- {anio}: {int(t['patrones'])} patrón(es); gravado {t['gravado']:,.2f}; ISR retenido {t['isr']:,.2f}. "
                 f"Siguiente paso: fiscal_mx.py anual --ejercicio {anio} --gravado {t['gravado']:.2f} "
                 f"--retenido {t['isr']:.2f}")
        print(linea)
        u = uma.get(anio)
        if u:
            for clave, veces, nombre in (("aguinaldo_exento", 30, "aguinaldo"), ("prima_vac_exento", 15, "prima vacacional"),
                                         ("ptu_exento", 15, "PTU")):
                tope = veces * u
                if t[clave] > tope + 0.01:
                    print(f"  - {nombre} exento {t[clave]:,.2f} rebasa el tope anual de {veces} UMA ({tope:,.2f}): "
                          f"el exceso de {t[clave] - tope:,.2f} grava en la anual")
        if t["patrones"] > 1:
            print("  - Dos o más patrones: obligado a declarar (LISR art. 98, fr. III, c) si fueron simultáneos "
                  "o dejó uno antes del 31/12; revisa también subsidio duplicado.")
        if t["gravado"] > 400_000:
            print("  - Salarios de más de $400,000: obligado a declarar (art. 98, fr. III, e).")
    for x in alertas + avisos:
        print(f"- {x}")
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
        if r["regimen"] not in REG_DEDUCCIONES:
            problemas.append(f"régimen {r['regimen']} no admite {r['uso']}: pide reexpedirla con 605 "
                             "(u otro régimen de deducciones que tengas)")
        if c["forma"] == "01":
            problemas.append("pagada en efectivo: el SAT exige transferencia, tarjeta o cheque nominativo")
        elif c["metodo"] == "PPD":
            problemas.append("PPD: la deducción vale con el complemento de pago; revisa forma y fecha del pago")
        if c["fecha"][:4] != str(ejercicio):
            problemas.append(f"fecha {c['fecha']} fuera del ejercicio {ejercicio}")
        if r["uso"] == "D10" and not c["colegiatura"]:
            problemas.append("colegiatura sin complemento de instituciones educativas (CURP del alumno y RVOE)")
        if lista_69b and c["emisor"]["rfc"] in lista_69b:
            problemas.append(f"emisor en lista 69-B ({lista_69b[c['emisor']['rfc']]})")
        revisadas.append((c, problemas))
    return revisadas, otras


def _cmd_deducciones(a):
    cfdis, avisos = leer_varios(a.xml)
    lista = _leer_69b(a.lista_69b) if a.lista_69b else None
    revisadas, otras = deducciones(cfdis, a.rfc, a.ejercicio, lista)
    print("| Archivo | Fecha | Emisor | Uso | Régimen | Forma | Total | Resultado |")
    print("|---|---|---|---|---|---|---|---|")
    suma = defaultdict(float)
    for c, problemas in revisadas:
        if not problemas:
            suma[c["receptor"]["uso"]] += c["total"] * c["tipo_cambio"]
        print(f"| {pathlib.Path(c['archivo']).name} | {c['fecha']} | {c['emisor']['nombre'] or c['emisor']['rfc']} | "
              f"{c['receptor']['uso']} | {c['receptor']['regimen']} | {c['forma']} | {c['total']:,.2f} | "
              f"{'OK' if not problemas else '; '.join(problemas)} |")
    print()
    for uso in sorted(suma):
        print(f"- {uso} {ETIQUETAS_D.get(uso, '')}: {suma[uso]:,.2f}")
    dentro = sum(v for k, v in suma.items() if k not in FUERA_DEL_TOPE_GLOBAL)
    uma = fiscal.PARAMS["uma_diaria"]["valores"].get(str(a.ejercicio))
    if a.ingresos and uma:
        uma_anual = round(round(uma * 30.4, 2) * 12, 2)  # INEGI: mensual = diaria x 30.4; anual = mensual x 12
        tope = min(5 * uma_anual, 0.15 * a.ingresos)
        print(f"- Sujetas al tope global: {dentro:,.2f}; tope = menor de 5 UMA anuales ({5 * uma_anual:,.2f}) y 15% de "
              f"ingresos ({0.15 * a.ingresos:,.2f}) = {tope:,.2f}; aplicable: {min(dentro, tope):,.2f}")
    elif not a.ingresos:
        print("- Pasa --ingresos <total del año, incluidos exentos> para aplicar el tope global (5 UMA o 15%).")
    print("- Topes propios que la herramienta no ve: lentes ópticos $2,500, funerales 1 UMA anual, colegiaturas por "
          "nivel, donativos 7%. Gastos de dependientes: ingresos menores a 1 UMA anual.")
    if otras:
        print(f"- {otras} factura(s) a tu RFC con uso distinto de D01-D10: no cuentan como deducción personal.")
    for x in avisos:
        print(f"- {x}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ver", help="resumen de uno o varios XML")
    s.add_argument("xml", nargs="+")
    s.add_argument("--sin-mascara", action="store_true")
    s.set_defaults(f=_cmd_ver)
    s = sub.add_parser("verificar", help="receptor de cada XML contra tu configuración")
    s.add_argument("xml", nargs="+")
    s.add_argument("--config", required=True, help="JSON con bloque receptor (ver ejemplos/autofactura.ejemplo.json)")
    s.add_argument("--perfil", help="perfil de la configuración (p. ej. actividad, medicos)")
    s.set_defaults(f=_cmd_verificar)
    s = sub.add_parser("resico", help="ISR e IVA mensual de RESICO PF desde XML emitidos y recibidos")
    s.add_argument("xml", nargs="+")
    s.add_argument("--rfc", required=True, help="tu RFC (para separar emitidos de recibidos)")
    s.add_argument("--mes", help="AAAA-MM para ver solo un mes")
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
