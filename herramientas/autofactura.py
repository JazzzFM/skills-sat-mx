"""Archivo de tickets y CFDI de autofactura: una carpeta por día de consumo y una tabla por mes.

Subcomandos (`python3 -I herramientas/autofactura.py <subcomando> --help`):
  registrar  Mueve un ticket a <carpeta>/<AAAA-MM>/<AAAA-MM-DD>/<comercio>_<total>_ticket.<ext> y agrega su fila
             "Pendiente" al README del mes.
  archivar   Mueve el XML (y PDF) timbrado junto a su ticket como <comercio>_<total>_<serie><folio>.{xml,pdf} y
             marca la fila como "Facturado" con UUID y forma de pago.
  vigencias  Cruza los pendientes del mes contra la ventana de autofactura de cada comercio.

Todo sale de tu configuración (ejemplos/autofactura.ejemplo.json copiado a personal/autofactura.json):
carpeta de facturas, receptor, perfiles y ventanas por comercio. Nunca sobrescribe ni borra archivos.
"""
import argparse
import calendar
import importlib.util
import json
import pathlib
import re
import shutil
import sys
from datetime import date, timedelta

_AQUI = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("cfdi_mx", _AQUI / "cfdi_mx.py")
cfdi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cfdi)

ENCABEZADO = "| Fecha | Comercio | Total | Estado | UUID | Forma de pago | Perfil | Notas |"
SEPARADOR = "|---|---|---|---|---|---|---|---|"
TOLERANCIA = 0.0201  # los portales redondean IVA/IEPS y el CFDI puede diferir uno o dos centavos del ticket


def cargar_config(ruta):
    cfg = json.loads(pathlib.Path(ruta).read_text(encoding="utf-8"))
    cfg["_carpeta"] = (pathlib.Path(ruta).resolve().parent / cfg.get("carpeta", "facturas")).resolve() \
        if not pathlib.Path(cfg.get("carpeta", "facturas")).expanduser().is_absolute() \
        else pathlib.Path(cfg["carpeta"]).expanduser()
    return cfg


def slug(s):
    s = cfdi.normalizar_nombre(s).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _monto(x):
    return f"{float(x):.2f}"


def readme_del_mes(carpeta, mes):
    ruta = carpeta / mes / "README.md"
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(f"# Facturas {mes}\n\nUna carpeta por día de consumo. Un ticket sin XML al lado es un "
                        f"pendiente.\n\n{ENCABEZADO}\n{SEPARADOR}\n", encoding="utf-8")
    return ruta


def _filas(texto):
    """(índice de línea, celdas) de cada fila de datos de la tabla."""
    salida = []
    for i, linea in enumerate(texto.splitlines()):
        if re.match(r"^\|\s*20\d{2}-\d{2}-\d{2}\s*\|", linea):
            salida.append((i, [c.strip() for c in linea.strip().strip("|").split("|")]))
    return salida


def _destino_libre(ruta):
    if not ruta.exists():
        return ruta
    n = 2
    while True:
        cand = ruta.with_name(f"{ruta.stem}-{n}{ruta.suffix}")
        if not cand.exists():
            return cand
        n += 1


def registrar(cfg, archivo, fecha, comercio, total, perfil="", notas=""):
    date.fromisoformat(fecha)
    comercio = slug(comercio)
    dia = cfg["_carpeta"] / fecha[:7] / fecha
    dia.mkdir(parents=True, exist_ok=True)
    origen = pathlib.Path(archivo)
    destino = _destino_libre(dia / f"{comercio}_{_monto(total)}_ticket{origen.suffix.lower()}")
    shutil.move(str(origen), destino)
    readme = readme_del_mes(cfg["_carpeta"], fecha[:7])
    with readme.open("a", encoding="utf-8") as f:
        f.write(f"| {fecha} | {comercio} | ${_monto(total)} | Pendiente | | | {perfil} | {notas} |\n")
    return destino


def _tickets_sin_cfdi(carpeta, comercio, total):
    """Carpetas de día con un ticket de ese comercio y total (± tolerancia) que todavía no tiene su CFDI."""
    candidatos = []
    for dia in sorted(carpeta.glob("20??-??/20??-??-??")):
        tickets = [t for t in dia.glob(f"{comercio}_*_ticket*.*") if _cerca(t.name, comercio, total)]
        xmls = [x for x in dia.glob(f"{comercio}_*.xml") if _cerca(x.name, comercio, total)]
        if len(tickets) > len(xmls):
            candidatos.append(dia)
    return candidatos


def _cerca(nombre, comercio, total):
    m = re.match(rf"^{re.escape(comercio)}_(\d+\.\d{{2}})_", nombre)
    return bool(m) and abs(float(m.group(1)) - total) < TOLERANCIA


def archivar(cfg, xml, pdf, comercio):
    c = cfdi.leer(xml)
    comercio = slug(comercio)
    total = c["total"]
    candidatos = _tickets_sin_cfdi(cfg["_carpeta"], comercio, total)
    aviso = ""
    if len(candidatos) > 1:
        raise RuntimeError(f"ambiguo: {len(candidatos)} tickets de {comercio} por {total:.2f} sin CFDI: "
                           + ", ".join(d.name for d in candidatos) + ". Muévelo a mano.")
    if candidatos:
        dia = candidatos[0]
    else:
        dia = cfg["_carpeta"] / c["fecha"][:7] / c["fecha"]
        aviso = f"sin ticket de {comercio} por {total:.2f}: se archiva por la fecha del XML ({c['fecha']}); verifica"
    dia.mkdir(parents=True, exist_ok=True)
    base = f"{comercio}_{total:.2f}_{c['serie']}{c['folio']}".rstrip("_")
    destino_xml = _destino_libre(dia / f"{base}.xml")
    shutil.move(str(xml), destino_xml)
    destino_pdf = None
    if pdf:
        destino_pdf = _destino_libre(destino_xml.with_suffix(".pdf"))
        shutil.move(str(pdf), destino_pdf)
    _marcar_facturado(cfg["_carpeta"], dia.name, comercio, total, c)
    return destino_xml, destino_pdf, aviso


def _marcar_facturado(carpeta, fecha, comercio, total, c):
    readme = readme_del_mes(carpeta, fecha[:7])
    lineas = readme.read_text(encoding="utf-8").splitlines()
    for i, celdas in _filas("\n".join(lineas)):
        if len(celdas) >= 4 and celdas[0] == fecha and celdas[1] == comercio and celdas[3] == "Pendiente":
            t = float(celdas[2].replace("$", "").replace(",", "") or 0)
            if abs(t - total) < TOLERANCIA:
                celdas += [""] * (8 - len(celdas))
                celdas[3], celdas[4], celdas[5] = "Facturado", c["uuid"], c["forma"]
                if abs(t - total) > 0.001:
                    celdas[7] = (celdas[7] + f" CFDI por ${total:.2f} (redondeo del portal)").strip()
                lineas[i] = "| " + " | ".join(celdas) + " |"
                break
    else:
        lineas.append(f"| {fecha} | {comercio} | ${total:.2f} | Facturado | {c['uuid']} | {c['forma']} | | sin ticket |")
    readme.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def ventana(cfg, comercio):
    """'5d' (días naturales desde el consumo), 'mes' (último día del mes de consumo), 'sin-plazo' o None."""
    ventanas = {slug(k): v for k, v in cfg.get("ventanas", {}).items()}
    return ventanas.get(slug(comercio))


def limite(fecha, regla):
    d = date.fromisoformat(fecha)
    if regla == "mes":
        return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
    m = re.fullmatch(r"(\d+)d", regla or "")
    return d + timedelta(days=int(m.group(1))) if m else None


def vigencias(cfg, mes, hoy):
    readme = cfg["_carpeta"] / mes / "README.md"
    if not readme.exists():
        return []
    salida = []
    for _, celdas in _filas(readme.read_text(encoding="utf-8")):
        if len(celdas) < 4 or celdas[3] != "Pendiente":
            continue
        fecha, comercio, total = celdas[0], celdas[1], celdas[2]
        regla = ventana(cfg, comercio)
        tope = limite(fecha, regla) if regla not in (None, "sin-plazo") else None
        if regla is None:
            salida.append((9999, "VENTANA DESCONOCIDA", fecha, comercio, total, "confírmala con el ticket o el comercio"))
        elif tope is None:
            salida.append((9998, "SIN PLAZO DURO", fecha, comercio, total, "ciérralo dentro del mes"))
        else:
            dias = (tope - hoy).days
            estado = (f"VENCIDO hace {-dias} días" if dias < 0 else "VENCE HOY" if dias == 0 else f"quedan {dias} días")
            salida.append((dias, estado, fecha, comercio, total, f"ventana {regla}, último día {tope}"))
    return sorted(salida)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="personal/autofactura.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("registrar", help="archiva un ticket nuevo y lo anota como Pendiente")
    s.add_argument("archivo")
    s.add_argument("--fecha", required=True, help="fecha de CONSUMO AAAA-MM-DD (la del ticket)")
    s.add_argument("--comercio", required=True)
    s.add_argument("--total", required=True, type=float)
    s.add_argument("--perfil", default="", help="perfil de receptor que usará la factura (p. ej. actividad, medicos)")
    s.add_argument("--notas", default="", help="identificadores de autofactura, portal, etc.")
    s = sub.add_parser("archivar", help="archiva un CFDI timbrado junto a su ticket")
    s.add_argument("xml")
    s.add_argument("pdf", nargs="?")
    s.add_argument("--comercio", required=True)
    s = sub.add_parser("vigencias", help="pendientes del mes ordenados por urgencia")
    s.add_argument("--mes", default=date.today().strftime("%Y-%m"))
    s.add_argument("--hoy", default=date.today().isoformat())
    a = p.parse_args(argv)
    cfg = cargar_config(a.config)
    if a.cmd == "registrar":
        print(registrar(cfg, a.archivo, a.fecha, a.comercio, a.total, a.perfil, a.notas))
    elif a.cmd == "archivar":
        try:
            x, pdf, aviso = archivar(cfg, a.xml, a.pdf, a.comercio)
        except RuntimeError as e:
            print(f"!! {e}", file=sys.stderr)
            sys.exit(1)
        print(x)
        if pdf:
            print(pdf)
        if aviso:
            print(f"!! {aviso}", file=sys.stderr)
    else:
        filas = vigencias(cfg, a.mes, date.fromisoformat(a.hoy))
        print(f"== Vigencias al {a.hoy} ({a.mes})")
        if not filas:
            print("No hay pendientes.")
        for _, estado, fecha, comercio, total, nota in filas:
            print(f"{estado:22} {fecha}  {comercio:20} {total:>12}  {nota}")


if __name__ == "__main__":
    main(sys.argv[1:])
