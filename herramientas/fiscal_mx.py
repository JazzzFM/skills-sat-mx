"""Cálculos de ISR para personas físicas en México (sueldos y RESICO), sin dependencias externas.

Subcomandos (ejecutar con `python3 -I herramientas/fiscal_mx.py <subcomando> --help`):
  provisionales  Pagos provisionales mensuales por sueldos de patrón no retenedor o del extranjero
                 (LISR art. 96 último párrafo) desde un CSV de depósitos, con tipo de cambio por fecha.
  anual          ISR anual (art. 152) contra lo retenido para un ejercicio.
  plazos         Pago inicial y parcialidades (CFF 66 y 66-A, tasas de la LIF).
  tarifa         Imprime una tarifa con su fuente y calidad.

Parámetros en parametros_mx.json (misma carpeta), cada uno con fuente y calidad.
"""
import argparse
import csv
import json
import pathlib
import sys
from collections import OrderedDict
from datetime import date, timedelta

PARAMS = json.loads((pathlib.Path(__file__).with_name("parametros_mx.json")).read_text(encoding="utf-8"))
INHABILES = {date.fromisoformat(f) for f in PARAMS["dias_inhabiles"]["fechas"]}


def _bloque(tipo, anio):
    for clave, bloque in PARAMS[f"tarifa_{tipo}"].items():
        if anio in bloque["ejercicios"]:
            return bloque
    raise KeyError(f"No hay tarifa {tipo} para el ejercicio {anio}; agrégala a parametros_mx.json con su fuente")


def tarifa(tipo, anio):
    return [tuple(f) for f in _bloque(tipo, anio)["filas"]]


def ejercicios_disponibles(tipo):
    return sorted(a for b in PARAMS[f"tarifa_{tipo}"].values() for a in b["ejercicios"])


def isr(base, filas):
    """ISR por tarifa progresiva: cuota fija + tasa sobre el excedente del límite inferior."""
    if base <= 0:
        return 0.0
    li, cuota, tasa = max(f for f in filas if f[0] <= base)
    return cuota + (base - li) * tasa


def resico_mensual(ingreso_cobrado):
    """RESICO PF: una sola tasa sobre todo lo cobrado del mes (no es marginal)."""
    for limite, tasa in PARAMS["resico_pf_mensual"]["filas"]:
        if ingreso_cobrado <= limite:
            return ingreso_cobrado * tasa
    raise ValueError("Ingreso mensual por encima del tope RESICO")


def vencimiento_mensual(anio, mes):
    """Día 17 del mes siguiente; si es sábado, domingo o inhábil, se recorre al siguiente hábil (CFF art. 12)."""
    a, m = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    d = date(a, m, 17)
    while d.weekday() >= 5 or d in INHABILES:
        d += timedelta(days=1)
    return d


def _meses_o_fraccion(desde, hasta):
    if hasta <= desde:
        return 0
    n = (hasta.year - desde.year) * 12 + (hasta.month - desde.month)
    return n + (1 if hasta.day > desde.day else 0)


def recargos_pct(desde, hasta):
    """Suma la tasa mensual de mora de cada mes o fracción transcurrido (CFF art. 21)."""
    tasas = PARAMS["recargos_mora_mensual"]["valores"]
    ultimo = max(tasas)
    total, a, m = 0.0, desde.year, desde.month
    for _ in range(_meses_o_fraccion(desde, hasta)):
        total += tasas.get(str(a), tasas[ultimo])
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return total


def parcialidad(saldo, n, tasa_mensual):
    """Mensualidad igual que amortiza el saldo en n meses a la tasa mensual dada."""
    return saldo * tasa_mensual / (1 - (1 + tasa_mensual) ** -n)


def elegible_plazos(vence, solicitud):
    """CFF art. 66-A, fr. VI, a): no procede pago a plazos de contribuciones que debieron pagarse en el año de
    calendario en curso ni en los seis meses anteriores al mes de la solicitud (salvo seguridad social)."""
    if vence.year == solicitud.year:
        return False
    meses = (solicitud.year - vence.year) * 12 + (solicitud.month - vence.month)
    return meses > 6


def tasa_plazos(n, anio=2026):
    t = PARAMS["recargos_plazos_mensual"][str(anio)]
    return t["hasta_12"] if n <= 12 else t["hasta_24"] if n <= 24 else t["mas_de_24_o_diferido"]


def provisionales(depositos, tipos_cambio, hoy, pago):
    """Agrupa depósitos por mes de cobro y calcula ISR provisional, vencimiento y recargos (techo).

    depositos: dicts con fecha (AAAA-MM-DD), usd y/o mxn. Si hay usd se usa el tipo de cambio de esa fecha
    (tipos_cambio[fecha], publicado en el DOF el día hábil anterior); si solo hay mxn, se usa tal cual.
    """
    meses = OrderedDict()
    for d in sorted(depositos, key=lambda x: x["fecha"]):
        f = d["fecha"]
        if d.get("usd"):
            if f not in tipos_cambio:
                raise KeyError(f"Falta el tipo de cambio fiscal del {f}")
            tc = tipos_cambio[f]
            mxn = float(d["usd"]) * tc
        else:
            tc, mxn = None, float(d["mxn"])
        meses.setdefault(f[:7], []).append({**d, "tc": tc, "mxn_fiscal": mxn})
    salida = []
    for mes, detalle in meses.items():
        anio, m = int(mes[:4]), int(mes[5:])
        mxn = sum(x["mxn_fiscal"] for x in detalle)
        impuesto = isr(mxn, tarifa("mensual", anio))
        vence = vencimiento_mensual(anio, m)
        vencido = vence < hoy
        salida.append({"mes": mes, "detalle": detalle, "mxn": mxn, "isr": impuesto, "vence": vence,
                       "vencido": vencido, "recargos": impuesto * recargos_pct(vence, pago) if vencido else 0.0})
    return salida


def _leer_tc(ruta):
    with open(ruta, newline="", encoding="utf-8") as f:
        return {r["fecha"]: float(r["pagos"]) for r in csv.DictReader(f) if r.get("pagos")}


def _cmd_provisionales(a):
    with open(a.depositos, newline="", encoding="utf-8") as f:
        deps = list(csv.DictReader(f))
    tc = _leer_tc(a.tc) if a.tc else {}
    meses = provisionales(deps, tc, date.fromisoformat(a.hoy), date.fromisoformat(a.pago))
    solicitud = date.fromisoformat(a.pago)
    print("| Mes | Depósitos | Ingreso fiscal MXN | ISR provisional | Vence | Estado | Recargos (techo) | ¿Pago a plazos? |")
    print("|---|---|---|---|---|---|---|---|")
    por_anio = {}
    for m in meses:
        dets = "; ".join(f"{x['fecha']} " + (f"{float(x['usd']):,.2f} USD x {x['tc']:.4f}" if x["tc"] else
                                              f"{x['mxn_fiscal']:,.2f} MXN") for x in m["detalle"])
        estado = "vencido" if m["vencido"] else "en tiempo"
        plazos = "sí" if elegible_plazos(m["vence"], solicitud) else "no (66-A VI a)"
        print(f"| {m['mes']} | {dets} | {m['mxn']:,.2f} | {m['isr']:,.2f} | {m['vence']} | {estado} | "
              f"{m['recargos']:,.2f} | {plazos} |")
        t = por_anio.setdefault(m["mes"][:4], {"mxn": 0, "isr": 0, "vencido": 0, "rec": 0})
        t["mxn"] += m["mxn"]; t["isr"] += m["isr"]; t["rec"] += m["recargos"]
        t["vencido"] += m["isr"] if m["vencido"] else 0
    print()
    for anio, t in por_anio.items():
        print(f"- {anio}: ingreso {t['mxn']:,.2f}; ISR provisional {t['isr']:,.2f} (vencido {t['vencido']:,.2f}); "
              f"recargos techo {t['rec']:,.2f}")
    print(f"- Recargos calculados como techo hasta {a.pago}, por mes o fracción, sin actualización por INPC.")


def _cmd_anual(a):
    impuesto = isr(a.gravado, tarifa("anual", a.ejercicio))
    dif = a.retenido + a.pagado - impuesto
    print(f"Ejercicio {a.ejercicio}: gravado {a.gravado:,.2f}; ISR anual {impuesto:,.2f}; "
          f"retenido {a.retenido:,.2f}; pagos provisionales {a.pagado:,.2f}")
    print(("Saldo a favor" if dif >= 0 else "ISR a cargo") + f": {abs(dif):,.2f}")
    print(f"Tarifa: {_bloque('anual', a.ejercicio)['fuente']} ({_bloque('anual', a.ejercicio)['calidad']})")


def _cmd_plazos(a):
    inicial = 0.20 * a.monto
    print(f"Adeudo {a.monto:,.2f}; pago inicial 20%: {inicial:,.2f} (CFF art. 66)")
    for n in (12, 24, 36):
        tasa = tasa_plazos(n)
        c = parcialidad(a.monto - inicial, n, tasa)
        print(f"- {n} parcialidades al {tasa:.2%}: ~{c:,.2f} al mes; total ~{inicial + c * n:,.2f}")
    print("Sin garantía si se paga cada parcialidad a tiempo (RMF 2026 regla 2.11.5).")
    print("OJO: solo entran adeudos que NO vencieron en el año en curso ni en los 6 meses previos a la solicitud "
          "(CFF 66-A, fr. VI, a). Usa la columna '¿Pago a plazos?' de 'provisionales' para separar el monto elegible.")


def _cmd_tarifa(a):
    b = _bloque(a.tipo, a.ejercicio)
    print(f"Tarifa {a.tipo} {a.ejercicio}: {b['fuente']} ({b['calidad']})")
    for li, cuota, tasa in b["filas"]:
        print(f"  desde {li:>14,.2f}  cuota {cuota:>14,.2f}  tasa {tasa:.2%}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("provisionales", help="pagos provisionales mensuales por sueldos sin retención")
    s.add_argument("--depositos", required=True, help="CSV con columnas fecha,usd,mxn[,cuenta,fuente,nota]")
    s.add_argument("--tc", help="CSV de tipo_cambio_banxico.py (columna pagos = DOF del día hábil anterior)")
    s.add_argument("--hoy", default=date.today().isoformat())
    s.add_argument("--pago", required=True, help="fecha supuesta de pago para recargos (AAAA-MM-DD)")
    s.set_defaults(f=_cmd_provisionales)
    s = sub.add_parser("anual", help="ISR anual contra retenido y pagos provisionales")
    s.add_argument("--ejercicio", type=int, required=True)
    s.add_argument("--gravado", type=float, required=True, help="ingresos totales menos exentos (menos deducciones personales)")
    s.add_argument("--retenido", type=float, default=0.0)
    s.add_argument("--pagado", type=float, default=0.0, help="pagos provisionales efectivamente hechos")
    s.set_defaults(f=_cmd_anual)
    s = sub.add_parser("plazos", help="opciones de pago a plazos")
    s.add_argument("--monto", type=float, required=True)
    s.set_defaults(f=_cmd_plazos)
    s = sub.add_parser("tarifa", help="imprime una tarifa con su fuente")
    s.add_argument("--tipo", choices=["mensual", "anual"], required=True)
    s.add_argument("--ejercicio", type=int, required=True)
    s.set_defaults(f=_cmd_tarifa)
    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main(sys.argv[1:])
