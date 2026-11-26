"""Documentos fiscales personales: clasificar, ordenar sin borrar, extraer depósitos y leer el Visor del SAT.

Subcomandos (`python3 -I herramientas/documentos.py <subcomando> --help`):
  planear     Propone nombres y carpetas (convención institucion/AAAA-MM-DD_institucion-producto_tipo).
  ordenar     Ejecuta un plan: mueve dentro del origen, aparta duplicados y metadatos, copia canónicos, manifiesto.
  depositos   Extrae depósitos de un pagador (p. ej. empresa extranjera) de estados Banamex y DólarApp a CSV.
  visor       Lee exportaciones "Anual.<RFC>.<año>.pdf" del Visor de nómina a CSV.
  csf         Resume una Constancia de Situación Fiscal (RFC enmascarado).
Requiere pdftotext (poppler). Todo es local; los archivos de entrada se tratan como datos no confiables.
"""
import argparse
import csv
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET

MESES_ES = {m: i for i, m in enumerate("enero febrero marzo abril mayo junio julio agosto septiembre octubre "
                                         "noviembre diciembre".split(), 1)}
MESES_ABR_ES = {m: i for i, m in enumerate("ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC".split(), 1)}
MESES_ABR_EN = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def _mes_en(nombre):
    """'May', 'Apr' o 'April' -> número de mes (DólarApp usa abreviatura o nombre completo)."""
    return MESES_ABR_EN[nombre[:3].capitalize()]


_MES_EN_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"


def _fechas_dolarapp(t):
    """(inicio, fin) del periodo como AAAA-MM-DD. El bloque puede partirse en renglones y mezclarse con la
    columna de saldos ("1 September" / "2026" / "30 September" / "2026"), así que se lee como secuencia:
    cada "día mes" toma el primer año de 4 dígitos que aparece después."""
    i = t.find("Fecha de inicio")
    if i < 0:
        return None
    j = t.find("Días)", i)
    bloque = t[i: j if j > 0 else i + 600]
    tokens = re.findall(rf"\b(\d{{1,2}}) ({_MES_EN_RE})\b|\b(20\d{{2}})\b", bloque)
    fechas, pendiente = [], None
    for dia, mes, anio in tokens:
        if dia:
            pendiente = (int(dia), _mes_en(mes))
        elif anio and pendiente:
            fechas.append(f"{anio}-{pendiente[1]:02d}-{pendiente[0]:02d}")
            pendiente = None
    return (fechas[0], fechas[1]) if len(fechas) >= 2 else None
CARPETAS_ESPECIALES = ("_duplicados", "_metadatos_macos", "_por_clasificar")


# ---------- utilidades ----------

def texto_pdf(ruta):
    r = subprocess.run(["pdftotext", "-layout", str(ruta), "-"], capture_output=True, timeout=120)
    return r.stdout.decode("utf-8", "replace")


def md5(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def huella_texto(texto):
    """Hash del contenido sin espacios ni horas: iguala el mismo estado descargado varias veces."""
    t = re.sub(r"\d{1,2}:\d{2}(:\d{2})?", "", re.sub(r"\s+", " ", texto))
    return hashlib.md5(t.encode()).hexdigest()


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def mascara(t):
    """Enmascara RFC de persona física, CURP, CLABE/cuentas/tarjetas y correos."""
    t = re.sub(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b", "[CURP]", t)
    t = re.sub(r"\b([A-ZÑ&]{4})\d{6}([A-Z0-9]{3})(?=\d*\b)", r"\1******\2", t)  # \d*: folios RFC+consecutivo
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[correo]", t)
    return re.sub(r"\b\d[\d -]{8,}\d\b", lambda m: "####" + re.sub(r"\D", "", m.group())[-4:], t)


def _monto(s):
    return float(s.replace("$", "").replace(",", ""))


# ---------- clasificación ----------

def clasificar(ruta):
    """Devuelve {'tipo', 'destino' (ruta relativa propuesta o None), ...} sin modificar nada."""
    ruta = pathlib.Path(ruta)
    if ruta.name.startswith("._"):
        return {"tipo": "metadatos_macos", "destino": None}
    ext = ruta.suffix.lower()
    if ext == ".xml":
        try:
            raiz = ET.parse(ruta).getroot()
        except ET.ParseError:
            return {"tipo": "xml", "destino": None}
        if raiz.tag.endswith("Comprobante"):
            emisor = next((e for e in raiz if e.tag.endswith("Emisor")), None)
            nombre = emisor.get("Nombre", "emisor") if emisor is not None else "emisor"
            inst = "banamex" if "BANCO NACIONAL DE MEXICO" in nombre.upper() else slug(nombre)
            fecha = (raiz.get("Fecha") or "")[:10]
            return {"tipo": "cfdi", "destino": f"{inst}/{fecha}_{inst}_cfdi.xml"}
        return {"tipo": "xml", "destino": None}
    if ext != ".pdf":
        return {"tipo": "otro", "destino": None}
    t = texto_pdf(ruta)
    m = re.search(r"Per[ií]odo del \d+ de \w+(?: del \d{4})? al (\d+) de (\w+) del (\d{4})", t)
    if m and "MiCuenta" in t:
        fecha = f"{m.group(3)}-{MESES_ES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
        return {"tipo": "banamex", "destino": f"banamex/{fecha}_banamex-micuenta_estado-cuenta.pdf"}
    periodo = _fechas_dolarapp(t)
    if periodo and ("DÓLARAPP" in t.upper() or "DOLARAPP" in t.upper()):
        return {"tipo": "dolarapp", "destino": f"dolarapp/{periodo[1]}_dolarapp-usd_estado-cuenta.pdf"}
    m = re.search(r"Acumulado anual total - Ejercicio: (\d{4})", t)
    if m:
        return {"tipo": "visor_anual", "ejercicio": int(m.group(1)), "destino": f"sat/visor/{m.group(1)}_visor-anual.pdf"}
    if "CONSTANCIA DE SITUACIÓN FISCAL" in t.upper():
        return {"tipo": "csf", "destino": None}
    return {"tipo": "pdf", "destino": None}


def planear(origen, referencia=None, mapa=None):
    """Plan para todos los archivos del origen: nada se omite ni se borra.

    Prioridad: mapa manual > igual a un archivo ya ordenado en `referencia` (misma ruta) > clasificación >
    duplicado de texto de uno ya planeado > _por_clasificar. Metadatos de macOS a _metadatos_macos.
    """
    origen = pathlib.Path(origen)
    mapa = mapa or {}
    ref = {}
    if referencia:
        referencia = pathlib.Path(referencia)
        ref = {md5(p): str(p.relative_to(referencia)) for p in referencia.rglob("*") if p.is_file()}
    plan, usados, huellas = [], set(), {}
    archivos = sorted(p for p in origen.rglob("*") if p.is_file() and p.name != "MANIFIESTO.csv"
                      and p.relative_to(origen).parts[0] not in CARPETAS_ESPECIALES)
    for p in archivos:
        rel = str(p.relative_to(origen))
        h = md5(p)
        c = clasificar(p)
        huella = huella_texto(texto_pdf(p)) if p.suffix.lower() == ".pdf" and c["tipo"] != "metadatos_macos" else h
        if rel in mapa:
            nuevo, motivo = mapa[rel], "mapa manual"
        elif c["tipo"] == "metadatos_macos":
            nuevo, motivo = "_metadatos_macos/" + rel.replace("/", "__"), "metadatos de macOS"
        elif huella in huellas:
            nuevo, motivo = "_duplicados/" + rel.replace("/", "__"), f"duplicado de {huellas[huella]}"
        elif h in ref:
            nuevo, motivo = ref[h], "igual al ya ordenado en la carpeta de referencia"
        elif c["destino"]:
            nuevo, motivo = c["destino"], f"clasificado como {c['tipo']}"
        else:
            nuevo, motivo = "_por_clasificar/" + rel.replace("/", "__"), f"sin regla ({c['tipo']}); decidir con el usuario"
        if nuevo in usados:
            nuevo, motivo = "_duplicados/" + rel.replace("/", "__"), f"mismo destino que otro archivo ({nuevo})"
        usados.add(nuevo)
        if not nuevo.startswith(CARPETAS_ESPECIALES):
            huellas.setdefault(huella, rel)
        plan.append({"original": rel, "nuevo": nuevo, "md5": h, "motivo": motivo})
    return plan


def ejecutar(plan, origen, copia=None):
    """Mueve dentro de `origen` según el plan, copia canónicos a `copia` y escribe MANIFIESTO.csv en ambos.

    No sobrescribe: si un destino existe, se detiene antes de mover nada.
    """
    origen = pathlib.Path(origen)
    for p in plan:
        if (origen / p["nuevo"]).exists() and p["nuevo"] != p["original"]:
            raise FileExistsError(origen / p["nuevo"])
        if copia and not p["nuevo"].startswith(CARPETAS_ESPECIALES) and (pathlib.Path(copia) / p["nuevo"]).exists():
            raise FileExistsError(pathlib.Path(copia) / p["nuevo"])
    filas = []
    for p in plan:
        src, dst = origen / p["original"], origen / p["nuevo"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.rename(src, dst)
        copia_rel = ""
        if copia and not p["nuevo"].startswith(CARPETAS_ESPECIALES):
            destino_copia = pathlib.Path(copia) / p["nuevo"]
            destino_copia.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, destino_copia)
            if md5(destino_copia) != p["md5"]:
                raise IOError(f"La copia de {p['nuevo']} no coincide")
            copia_rel = p["nuevo"]
        filas.append({**p, "copia": copia_rel})
    for carpeta in sorted({(origen / p["original"]).parent for p in plan}, key=lambda x: len(str(x)), reverse=True):
        if carpeta != origen:
            try:
                carpeta.rmdir()
            except OSError:
                pass
    for destino in [origen] + ([pathlib.Path(copia)] if copia else []):
        with open(destino / "MANIFIESTO.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["original", "nuevo", "md5", "motivo", "copia"])
            w.writeheader()
            w.writerows(filas)
    return filas


# ---------- depósitos ----------

def _depositos_banamex(t, pagador):
    m = re.search(r"Per[ií]odo del \d+ de (\w+)(?: del (\d{4}))? al \d+ de (\w+) del (\d{4})", t)
    if not m:
        return []
    mes_ini, anio_fin = MESES_ES[m.group(1).lower()], int(m.group(4))
    anio_ini = int(m.group(2)) if m.group(2) else anio_fin
    lineas = [" ".join(l.split()) for l in t.splitlines() if l.strip()]
    salida = []
    for i, l in enumerate(lineas):
        mm = re.match(r"(\d{2}) ([A-Z]{3}) PAGO RECIBIDO DE (.+)", l)
        if not mm or pagador.upper() not in mm.group(3).upper():
            continue
        mes = MESES_ABR_ES[mm.group(2)]
        anio = anio_ini if mes >= mes_ini else anio_fin
        bloque = " ".join(lineas[i + 1:i + 8])
        usd = re.search(r"\$([\d,]+\.\d{2})/TC \$([\d.]+)", bloque)
        mxn = re.search(r"HORA \d{2}:\d{2} SUC \S+ ([\d,]+\.\d{2})", bloque)
        salida.append({"fecha": f"{anio}-{mes:02d}-{int(mm.group(1)):02d}", "usd": _monto(usd.group(1)) if usd else None,
                       "tc_banco": float(usd.group(2)) if usd else None, "mxn_banco": _monto(mxn.group(1)) if mxn else None,
                       "cuenta": "banamex", "comision_usd": None})
    return salida


def _depositos_dolarapp(t, pagador):
    periodo = _fechas_dolarapp(t)
    if not periodo:
        return []
    anio = int(periodo[0][:4])
    salida = []
    lineas = [" ".join(l.split()) for l in t.splitlines() if l.strip()]
    for i, l in enumerate(lineas):
        mm = re.match(r"([A-Za-z]{3}) (\d{2}) Compra USDc \+ ([\d,]+(?:\.\d+)?) USD \+ [\d,.]+ (.+)", l)
        if not mm or pagador.upper() not in mm.group(4).upper():
            continue
        com = re.search(r"Comisi[oó]n -([\d.]+)", " ".join(lineas[i + 1:i + 3]))
        salida.append({"fecha": f"{anio}-{_mes_en(mm.group(1)):02d}-{int(mm.group(2)):02d}",
                       "usd": _monto(mm.group(3)), "tc_banco": None, "mxn_banco": None, "cuenta": "dolarapp",
                       "comision_usd": float(com.group(1)) if com else None})
    return salida


def depositos(pdfs, pagador):
    """Depósitos del pagador en estados Banamex y DólarApp, sin duplicar estados repetidos."""
    vistos, salida = set(), []
    for ruta in pdfs:
        t = texto_pdf(ruta)
        h = huella_texto(t)
        if h in vistos:
            continue
        vistos.add(h)
        for d in _depositos_banamex(t, pagador) + _depositos_dolarapp(t, pagador):
            salida.append({**d, "fuente": pathlib.Path(ruta).name})
    return sorted(salida, key=lambda d: d["fecha"])


# ---------- SAT ----------

def visor(pdfs):
    """Lee exportaciones del Visor de nómina; ignora descargas repetidas del mismo documento."""
    filas, vistos = [], set()
    for ruta in pdfs:
        t = texto_pdf(ruta)
        huella = huella_texto(re.sub(r"\|[^\n]*\|", "", t))  # la cadena original cambia con la fecha de consulta
        if huella in vistos:
            continue
        vistos.add(huella)
        lineas = [" ".join(l.split()) for l in t.splitlines() if l.strip()]
        texto = "\n".join(lineas)
        ej = re.search(r"Ejercicio: (\d{4})", texto)
        per = re.search(r"Periodo que ampara la información \d{4} (\w+) (\w+)", texto)
        total = re.search(r"Total de ingresos por sueldos y salarios (\$[\d,]+\.\d{2})", texto)
        isr = re.search(r"ISR retenido (\$[\d,]+\.\d{2})", texto)
        exento = None
        for i, l in enumerate(lineas):
            if l.startswith("Total de ingresos exento por sueldos"):
                for sig in lineas[i:i + 3]:
                    mm = re.search(r"(\$[\d,]+\.\d{2})", sig)
                    if mm:
                        exento = _monto(mm.group(1))
                        break
                break
        patrones = []
        en_retenedores = False
        for l in lineas:
            if l.startswith("Datos del retenedor"):
                en_retenedores = True
                continue
            mm = re.match(r"RFC ([A-Z&Ñ]{3}\d{6}[A-Z0-9]{3}) (.+)", l)
            if en_retenedores and mm and "CURP" not in l:
                patrones.append(mm.group(2).strip())
        filas.append({"ejercicio": int(ej.group(1)) if ej else None,
                      "periodo": f"{per.group(1)}-{per.group(2)}" if per else "",
                      "total": _monto(total.group(1)) if total else None, "exento": exento,
                      "isr_retenido": _monto(isr.group(1)) if isr else None, "patrones": patrones,
                      "fuente": pathlib.Path(ruta).name})
    return sorted(filas, key=lambda f: f["ejercicio"] or 0)


def csf(ruta):
    t = texto_pdf(ruta)
    lineas = [" ".join(l.split()) for l in t.splitlines() if l.strip()]
    rfc = re.search(r"RFC:\s*([A-ZÑ&]{4}\d{6}[A-Z0-9]{3})", "\n".join(lineas))
    estatus = re.search(r"Estatus en el padrón:\s*(\w+)", "\n".join(lineas))
    regimenes = []
    for l in lineas:
        mm = re.match(r"(Régimen .+?)\s+\d{2}/\d{2}/\d{4}", l)
        if mm:
            regimenes.append(mm.group(1))
    return {"rfc": mascara(rfc.group(1)) if rfc else None, "estatus": estatus.group(1) if estatus else None,
            "regimenes": regimenes}


# ---------- CLI ----------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre in ("planear", "ordenar"):
        s = sub.add_parser(nombre)
        s.add_argument("--origen", required=True)
        s.add_argument("--referencia", help="carpeta ya ordenada cuyos nombres se reutilizan si el archivo es idéntico")
        s.add_argument("--mapa", help="CSV original,nuevo para decisiones manuales")
        if nombre == "ordenar":
            s.add_argument("--copia", help="carpeta donde copiar los canónicos (p. ej. personal/estados-cuenta)")
    s = sub.add_parser("depositos")
    s.add_argument("--pagador", required=True)
    s.add_argument("--salida", required=True)
    s.add_argument("pdfs", nargs="+")
    s = sub.add_parser("visor")
    s.add_argument("--salida", required=True)
    s.add_argument("pdfs", nargs="+")
    s = sub.add_parser("csf")
    s.add_argument("pdf")
    a = p.parse_args(argv)

    if a.cmd in ("planear", "ordenar"):
        mapa = {}
        if a.mapa:
            mapa = {r["original"]: r["nuevo"] for r in csv.DictReader(open(a.mapa, encoding="utf-8"))}
        plan = planear(a.origen, a.referencia, mapa)
        for x in plan:
            if not x["original"].split("/")[-1].startswith("._"):
                print(f"{x['original']}  ->  {x['nuevo']}  ({x['motivo']})")
        print(f"\n{len(plan)} archivos; {sum(1 for x in plan if x['nuevo'].startswith('_por_clasificar'))} por clasificar")
        if a.cmd == "ordenar":
            filas = ejecutar(plan, a.origen, a.copia)
            print(f"Movidos {len(filas)}; copiados {sum(1 for f in filas if f['copia'])}; MANIFIESTO.csv escrito")
        else:
            print("Simulación: nada se movió. Usa 'ordenar' para ejecutar.")
    elif a.cmd == "depositos":
        deps = depositos(a.pdfs, a.pagador)
        with open(a.salida, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["fecha", "usd", "mxn", "cuenta", "tc_banco", "mxn_banco", "comision_usd", "fuente", "nota"])
            w.writeheader()
            for d in deps:
                w.writerow({**d, "mxn": "", "nota": ""})
        for d in deps:
            print(f"{d['fecha']} {d['usd']:,.2f} USD ({d['cuenta']}; {d['fuente']})")
        print(f"{len(deps)} depósitos -> {a.salida}")
    elif a.cmd == "visor":
        filas = visor(a.pdfs)
        with open(a.salida, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ejercicio", "periodo", "total", "exento", "isr_retenido", "patrones", "fuente"])
            w.writeheader()
            for r in filas:
                w.writerow({**r, "patrones": " | ".join(r["patrones"]), "fuente": mascara(r["fuente"])})
        for r in filas:
            print(f"{r['ejercicio']} {r['periodo']}: total {r['total']:,.2f}; exento {r['exento']:,.2f}; "
                  f"ISR {r['isr_retenido']:,.2f}; {len(r['patrones'])} patrón(es)")
    elif a.cmd == "csf":
        print(csf(a.pdf))


if __name__ == "__main__":
    main(sys.argv[1:])
