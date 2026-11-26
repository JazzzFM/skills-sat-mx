"""Tipo de cambio peso-dólar para efectos fiscales (CFF art. 20) desde la consulta pública de Banxico.

Columnas: fix (determinado ese día), dof (publicado en el DOF ese día) y pagos (el que rige para pagos ese
día = publicado en el DOF el día hábil bancario anterior). Para un ingreso cobrado en la fecha F se usa
`pagos` de F: es "el tipo de cambio que Banxico publique en el DOF el día anterior".

Uso:
  python3 -I herramientas/tipo_cambio_banxico.py descargar --desde 2025-08-01 --hasta 2026-10-26 --salida tc.csv
  python3 -I herramientas/tipo_cambio_banxico.py consultar --tc tc.csv 2026-05-15 2026-06-17
Solo envía fechas a Banxico; ningún dato personal.
"""
import argparse
import csv
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

URL_FORM = "https://www.banxico.org.mx/tipcamb/tipCamMIAction.do?idioma=sp"
URL_DATOS = "https://www.banxico.org.mx/tipcamb/tipCamIHAction.do"
_FECHA = re.compile(r"\d{2}/\d{2}/\d{4}")
_VALOR = re.compile(r"\d+\.\d+|N/E")


class _Celdas(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pila, self.tablas, self.celda, self.en_td = [], [], [], False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.pila.append([])
        elif tag == "td":
            self.en_td, self.celda = True, []

    def handle_endtag(self, tag):
        if tag == "td" and self.en_td and self.pila:
            self.pila[-1].append(" ".join("".join(self.celda).split()))
            self.en_td = False
        elif tag == "table" and self.pila:
            self.tablas.append(self.pila.pop())

    def handle_data(self, data):
        if self.en_td:
            self.celda.append(data)


def parsear(html):
    p = _Celdas()
    p.feed(html)
    tabla_fechas = max(p.tablas, key=lambda t: sum(bool(_FECHA.fullmatch(c)) for c in t))
    fechas = [c for c in tabla_fechas if _FECHA.fullmatch(c)]
    columnas = [[c for c in t if _VALOR.fullmatch(c)] for t in p.tablas]
    columnas = [c for c in columnas if len(c) == len(fechas)][:3]
    if len(columnas) < 3:
        raise ValueError("Formato de Banxico inesperado: no se encontraron 3 columnas de valores")
    filas = []
    for i, f in enumerate(fechas):
        d, m, a = f.split("/")
        fix, dof, pagos = ("" if col[i] == "N/E" else col[i] for col in columnas)
        filas.append({"fecha": f"{a}-{m}-{d}", "fix": fix, "dof": dof, "pagos": pagos})
    return sorted(filas, key=lambda r: r["fecha"])


def tc_fiscal(fecha, filas):
    """Tipo de cambio fiscal para un cobro en `fecha`: columna pagos; si no hay dato, el último anterior."""
    previos = [r for r in filas if r["fecha"] <= fecha and r["pagos"]]
    if not previos:
        raise KeyError(f"Sin tipo de cambio publicado antes de {fecha}")
    return float(previos[-1]["pagos"])


def descargar(desde, hasta):
    """desde/hasta en AAAA-MM-DD. Devuelve filas parseadas."""
    fmt = lambda f: f"{f[8:10]}/{f[5:7]}/{f[0:4]}"
    abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    abridor.open(URL_FORM, timeout=60).read()
    datos = urllib.parse.urlencode({"idioma": "sp", "fechaInicial": fmt(desde), "fechaFinal": fmt(hasta),
                                    "salida": "HTML"}).encode()
    req = urllib.request.Request(URL_DATOS, data=datos, headers={"Referer": URL_FORM})
    html = abridor.open(req, timeout=90).read().decode("latin-1")
    return parsear(html)


def escribir_csv(filas, ruta):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["fecha", "fix", "dof", "pagos"])
        w.writeheader()
        w.writerows(filas)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("descargar")
    s.add_argument("--desde", required=True)
    s.add_argument("--hasta", required=True)
    s.add_argument("--salida", required=True)
    s = sub.add_parser("consultar")
    s.add_argument("--tc", required=True)
    s.add_argument("fechas", nargs="+")
    a = p.parse_args(argv)
    if a.cmd == "descargar":
        filas = descargar(a.desde, a.hasta)
        escribir_csv(filas, a.salida)
        print(f"{len(filas)} días: {filas[0]['fecha']} a {filas[-1]['fecha']} -> {a.salida}")
    else:
        filas = list(csv.DictReader(open(a.tc, encoding="utf-8")))
        for f in a.fechas:
            print(f"{f}: {tc_fiscal(f, filas):.4f} (publicado en el DOF el día hábil anterior)")


if __name__ == "__main__":
    main(sys.argv[1:])
