"""Archivo de tickets y CFDI de autofactura: una carpeta por día de consumo y una tabla por mes.

Subcomandos (`python3 -I herramientas/autofactura.py <subcomando> --help`):
  registrar  Mueve un ticket a <carpeta>/<AAAA-MM>/<AAAA-MM-DD>/<comercio>_<total>_ticket.<ext> y agrega su fila
             "Pendiente" al README del mes. Rechaza el mismo ticket dos veces.
  archivar   Verifica el receptor del XML timbrado contra tu configuración y lo mueve (con su PDF) junto a su ticket
             como <comercio>_<total>_<serie><folio>.{xml,pdf}; marca la fila "Facturado" con UUID y forma de pago.
  vigencias  Cruza los pendientes de todos los meses contra la ventana de autofactura de cada comercio.

Todo sale de tu configuración (ejemplos/autofactura.ejemplo.json copiado a personal/autofactura.json):
carpeta de facturas, receptor, perfiles y ventanas por comercio. Nunca sobrescribe ni borra archivos.
"""
import argparse
import calendar
import hashlib
import importlib.util
import json
import math
import pathlib
import re
import shutil
import sys
from datetime import date, timedelta

_AQUI = pathlib.Path(__file__).resolve().parent


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, _AQUI / f"{nombre}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


cfdi = _cargar("cfdi_mx")
rutas = _cargar("rutas")

ENCABEZADO = "| Fecha | Comercio | Total | Estado | UUID | Forma de pago | Perfil | Notas |"
SEPARADOR = "|---|---|---|---|---|---|---|---|"
TOLERANCIA = 0.0201   # los portales redondean IVA/IEPS y el CFDI puede diferir uno o dos centavos del ticket
MAX_DIAS_TICKET = 45  # un CFDI solo se empareja con un ticket de hasta 45 días antes


class ErrorAutofactura(Exception):
    pass


def cargar_config(ruta):
    ruta = pathlib.Path(ruta)
    if not ruta.exists():
        raise ErrorAutofactura(f"no existe {ruta}: copia ejemplos/autofactura.ejemplo.json a personal/autofactura.json "
                               "y llénalo con los datos de tu Constancia de Situación Fiscal")
    cfg = json.loads(ruta.read_text(encoding="utf-8"))
    carpeta = pathlib.Path(cfg.get("carpeta", "facturas")).expanduser()
    if not carpeta.is_absolute():
        carpeta = ruta.resolve().parent / carpeta
    carpeta = carpeta.resolve()
    try:
        rutas.exigir_fuera_del_repo_o_en_personal(carpeta, "la carpeta de facturas")
    except ValueError as e:
        raise ErrorAutofactura(str(e)) from None
    cfg["_carpeta"] = carpeta
    return cfg


def slug(s):
    s = cfdi.normalizar_nombre(s).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _monto(x):
    return f"{float(x):.2f}"


def _celda(s):
    return re.sub(r"[\r\n]+", " ", str(s or "")).replace("|", "/").strip()


def _fecha(fecha):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha or ""):
        raise ErrorAutofactura(f"fecha '{fecha}' inválida: usa AAAA-MM-DD")
    try:
        return date.fromisoformat(fecha).isoformat()
    except ValueError:
        raise ErrorAutofactura(f"fecha '{fecha}' inválida: usa AAAA-MM-DD") from None


def _md5(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 16), b""):
            h.update(bloque)
    return h.hexdigest()


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


def _agregar_fila(readme, celdas):
    texto = readme.read_text(encoding="utf-8")
    if texto and not texto.endswith("\n"):
        texto += "\n"
    readme.write_text(texto + "| " + " | ".join(_celda(c) for c in celdas) + " |\n", encoding="utf-8")


def _destino_libre(ruta):
    if not ruta.exists():
        return ruta
    n = 2
    while True:
        cand = ruta.with_name(f"{ruta.stem}-{n}{ruta.suffix}")
        if not cand.exists():
            return cand
        n += 1


def _dias(carpeta):
    return sorted(d for d in carpeta.glob("20??-??/20??-??-??") if d.is_dir())


def registrar(cfg, archivo, fecha, comercio, total, perfil="", notas=""):
    fecha = _fecha(fecha)
    comercio = slug(comercio)
    origen = pathlib.Path(archivo).resolve()
    if not origen.is_file():
        raise ErrorAutofactura(f"no existe el ticket {archivo}")
    try:
        origen.relative_to(cfg["_carpeta"])
        raise ErrorAutofactura(f"{archivo} ya está dentro de la carpeta de facturas: ¿ya lo registraste?")
    except ValueError:
        pass
    huella = _md5(origen)
    for dia in _dias(cfg["_carpeta"]):
        for t in dia.glob("*_ticket*"):
            if t.is_file() and _md5(t) == huella:
                raise ErrorAutofactura(f"ese ticket ya está registrado como {t}")
    dia = cfg["_carpeta"] / fecha[:7] / fecha
    dia.mkdir(parents=True, exist_ok=True)
    destino = _destino_libre(dia / f"{comercio}_{_monto(total)}_ticket{origen.suffix.lower()}")
    readme = readme_del_mes(cfg["_carpeta"], fecha[:7])
    shutil.move(str(origen), destino)
    _agregar_fila(readme, [fecha, comercio, f"${_monto(total)}", "Pendiente", "", "", perfil, notas])
    return destino


def _cerca(nombre, comercio, total):
    m = re.match(rf"^{re.escape(comercio)}_(\d+\.\d{{2}})_", nombre)
    return bool(m) and abs(float(m.group(1)) - total) < TOLERANCIA


def _tickets_sin_cfdi(carpeta, comercio, total, fecha_cfdi):
    """Días con un ticket de ese comercio y total (± tolerancia) sin su CFDI, de 0 a 45 días antes del CFDI."""
    tope = date.fromisoformat(fecha_cfdi)
    candidatos = []
    for dia in _dias(carpeta):
        try:
            consumo = date.fromisoformat(dia.name)
        except ValueError:
            continue
        if not (tope - timedelta(days=MAX_DIAS_TICKET) <= consumo <= tope):
            continue
        tickets = [t for t in dia.glob(f"{comercio}_*_ticket*") if _cerca(t.name, comercio, total)]
        xmls = [x for x in dia.glob(f"{comercio}_*.xml") if _cerca(x.name, comercio, total)]
        if len(tickets) > len(xmls):
            candidatos.append(dia)
    return candidatos


def _fila_pendiente(carpeta, fecha, comercio, total):
    readme = carpeta / fecha[:7] / "README.md"
    if not readme.exists():
        return None
    for i, celdas in _filas(readme.read_text(encoding="utf-8")):
        if len(celdas) >= 4 and celdas[0] == fecha and celdas[1] == comercio and celdas[3] == "Pendiente":
            try:
                t = float(celdas[2].replace("$", "").replace(",", ""))
            except ValueError:
                continue
            if abs(t - total) < TOLERANCIA:
                return celdas + [""] * (8 - len(celdas))
    return None


def _ya_archivado(carpeta, uuid):
    for readme in sorted(carpeta.glob("20??-??/README.md")):
        if uuid in readme.read_text(encoding="utf-8"):
            return readme
    return None


def archivar(cfg, xml, pdf, comercio, forzar=False):
    """Devuelve (xml destino, pdf destino o None, avisos). Lanza ErrorAutofactura sin mover nada si algo no cuadra."""
    try:
        c = cfdi.leer(xml)
    except (ValueError, cfdi.ET.ParseError) as e:
        raise ErrorAutofactura(f"no es un CFDI válido: {e}") from None
    if not c["uuid"]:
        raise ErrorAutofactura(f"{xml} no trae timbre fiscal: no es un CFDI emitido")
    if pdf and not pathlib.Path(pdf).is_file():
        raise ErrorAutofactura(f"no existe el PDF {pdf}")
    previo = _ya_archivado(cfg["_carpeta"], c["uuid"])
    if previo:
        raise ErrorAutofactura(f"el UUID {c['uuid']} ya está archivado (ver {previo}); no se duplica")
    comercio = slug(comercio)
    total, avisos = c["total"], []
    candidatos = _tickets_sin_cfdi(cfg["_carpeta"], comercio, total, c["fecha"])
    if len(candidatos) > 1:
        raise ErrorAutofactura(f"ambiguo: {len(candidatos)} tickets de {comercio} por {total:.2f} sin CFDI: "
                               + ", ".join(d.name for d in candidatos) + ". Muévelo a mano.")
    fila = _fila_pendiente(cfg["_carpeta"], candidatos[0].name, comercio, total) if candidatos else None
    if cfg.get("receptor"):
        esperado = dict(cfg["receptor"])
        perfil = fila[6] if fila else ""
        if perfil:
            if perfil not in cfg.get("perfiles", {}):
                raise ErrorAutofactura(f"la fila del ticket usa el perfil '{perfil}', que no está en la configuración")
            esperado.update(cfg["perfiles"][perfil])
        problemas, notas = cfdi.verificar(c, esperado)
        avisos += notas
        if problemas and not forzar:
            raise ErrorAutofactura("receptor incorrecto: " + "; ".join(problemas) + ". No se archiva: pide al comercio "
                                   "cancelar y reexpedir (o usa --forzar si ya lo revisaste)")
        if problemas:
            avisos.append("archivado con --forzar pese a: " + "; ".join(problemas))
    if candidatos:
        dia = candidatos[0]
    else:
        dia = cfg["_carpeta"] / c["fecha"][:7] / c["fecha"]
        avisos.append(f"sin ticket de {comercio} por {total:.2f} en los 45 días previos: se archiva por la fecha del XML "
                      f"({c['fecha']}); verifica")
    dia = dia.resolve()
    dia.relative_to(cfg["_carpeta"])  # la fecha ya se validó; esto impide escribir fuera de la carpeta
    serie_folio = re.sub(r"[^A-Za-z0-9-]+", "-", f"{c['serie']}{c['folio']}").strip("-") or c["uuid"][:8]
    destino_xml = _destino_libre(dia / f"{comercio}_{total:.2f}_{serie_folio}.xml")
    destino_pdf = _destino_libre(destino_xml.with_suffix(".pdf")) if pdf else None
    dia.mkdir(parents=True, exist_ok=True)
    readme = readme_del_mes(cfg["_carpeta"], dia.name[:7])
    shutil.move(str(xml), destino_xml)
    if pdf:
        shutil.move(str(pdf), destino_pdf)
    _marcar_facturado(readme, dia.name, comercio, total, c, bool(candidatos))
    return destino_xml, destino_pdf, avisos


def _marcar_facturado(readme, fecha, comercio, total, c, con_ticket):
    lineas = readme.read_text(encoding="utf-8").splitlines()
    for i, celdas in _filas("\n".join(lineas)):
        if len(celdas) >= 4 and celdas[0] == fecha and celdas[1] == comercio and celdas[3] == "Pendiente":
            try:
                t = float(celdas[2].replace("$", "").replace(",", ""))
            except ValueError:
                continue
            if abs(t - total) < TOLERANCIA:
                celdas += [""] * (8 - len(celdas))
                celdas[3], celdas[4], celdas[5] = "Facturado", c["uuid"], _celda(c["forma"])
                if abs(t - total) > 0.001:
                    celdas[7] = (celdas[7] + f" CFDI por ${total:.2f} (redondeo del portal)").strip()
                lineas[i] = "| " + " | ".join(celdas) + " |"
                readme.write_text("\n".join(lineas) + "\n", encoding="utf-8")
                return
    _agregar_fila(readme, [fecha, comercio, f"${total:.2f}", "Facturado", c["uuid"], c["forma"], "",
                           "con ticket sin fila" if con_ticket else "sin ticket"])


def ventana(cfg, comercio):
    """La regla de la configuración para el comercio, o None si no tiene."""
    ventanas = {slug(k): v for k, v in cfg.get("ventanas", {}).items()}
    return ventanas.get(slug(comercio))


def limite(fecha, regla):
    """(estado, último día). estado: 'ok', 'sin-plazo', 'desconocida' (sin regla) o 'invalida' (no se entiende).

    Reglas: "mes" (último día del mes de consumo), "Nd" o "N días" (días naturales desde el consumo),
    "Nh" o "N horas" (se redondea hacia arriba a días) y "sin-plazo"."""
    if regla is None:
        return "desconocida", None
    r = str(regla).strip().lower()
    d = date.fromisoformat(fecha)
    if r == "sin-plazo":
        return "sin-plazo", None
    if r == "mes":
        return "ok", date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
    m = re.fullmatch(r"(\d+)\s*(d|dias|días|h|horas)?", r)
    if not m:
        return "invalida", None
    n = int(m.group(1))
    dias = math.ceil(n / 24) if (m.group(2) or "").startswith("h") else n
    return "ok", d + timedelta(days=dias)


def vigencias(cfg, hoy, mes=None):
    """Pendientes de todos los meses (o hasta `mes`, AAAA-MM), ordenados por urgencia."""
    salida = []
    for readme in sorted(cfg["_carpeta"].glob("20??-??/README.md")):
        for _, celdas in _filas(readme.read_text(encoding="utf-8")):
            if len(celdas) < 4 or celdas[3] != "Pendiente":
                continue
            fecha, comercio, total = celdas[0], celdas[1], celdas[2]
            if mes and fecha[:7] > mes:
                continue
            regla = ventana(cfg, comercio)
            try:
                estado, tope = limite(fecha, regla)
            except ValueError:
                estado, tope = "invalida", None
            if estado == "desconocida":
                salida.append((9999, "VENTANA DESCONOCIDA", fecha, comercio, total, "confírmala con el ticket o el comercio"))
            elif estado == "invalida":
                salida.append((9999, "VENTANA INVÁLIDA", fecha, comercio, total,
                               f"no se entiende '{regla}': usa mes, 5d, 72h o sin-plazo"))
            elif estado == "sin-plazo":
                salida.append((9998, "SIN PLAZO DURO", fecha, comercio, total, "ciérralo dentro del mes"))
            else:
                dias = (tope - hoy).days
                txt = f"VENCIDO hace {-dias} días" if dias < 0 else "VENCE HOY" if dias == 0 else f"quedan {dias} días"
                salida.append((dias, txt, fecha, comercio, total, f"ventana {regla}, último día {tope}"))
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
    s = sub.add_parser("archivar", help="verifica y archiva un CFDI timbrado junto a su ticket")
    s.add_argument("xml")
    s.add_argument("pdf", nargs="?")
    s.add_argument("--comercio", required=True)
    s.add_argument("--forzar", action="store_true", help="archiva aunque el receptor no cuadre (ya revisado a mano)")
    s = sub.add_parser("vigencias", help="pendientes ordenados por urgencia")
    s.add_argument("--mes", help="AAAA-MM: solo pendientes de ese mes y anteriores")
    s.add_argument("--hoy", default=date.today().isoformat())
    a = p.parse_args(argv)
    try:
        cfg = cargar_config(a.config)
        if a.cmd == "registrar":
            print(registrar(cfg, a.archivo, a.fecha, a.comercio, a.total, a.perfil, a.notas))
        elif a.cmd == "archivar":
            x, pdf, avisos = archivar(cfg, a.xml, a.pdf, a.comercio, a.forzar)
            print(x)
            if pdf:
                print(pdf)
            for aviso in avisos:
                print(f"!! {aviso}", file=sys.stderr)
        else:
            filas = vigencias(cfg, date.fromisoformat(a.hoy), a.mes)
            print(f"== Vigencias al {a.hoy}" + (f" (hasta {a.mes})" if a.mes else ""))
            if not filas:
                print("No hay pendientes.")
            for _, estado, fecha, comercio, total, nota in filas:
                print(f"{estado:22} {fecha}  {comercio:20} {total:>12}  {nota}")
    except ErrorAutofactura as e:
        print(f"!! {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
