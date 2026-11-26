"""Cálculos de ISR para personas físicas en México (sueldos y RESICO), sin dependencias externas.

Subcomandos (ejecutar con `python3 -I herramientas/fiscal_mx.py <subcomando> --help`):
  provisionales  Pagos provisionales mensuales por sueldos de patrón no retenedor o del extranjero
                 (LISR art. 96 último párrafo) desde un CSV de depósitos, con tipo de cambio por fecha.
  anual          ISR anual (art. 152) contra lo retenido para un ejercicio.
  resico         ISR e IVA de un mes RESICO PF a partir de montos (sin XML).
  plazos         Pago inicial y parcialidades (CFF 66 y 66-A, tasas de la LIF del año).
  tarifa         Imprime una tarifa con su fuente y calidad.
  vigencia       Qué parámetros faltan para un ejercicio (tarifas, UMA, recargos, tabla RESICO).

Parámetros en parametros_mx.json (misma carpeta), cada uno con fuente y calidad.
"""
import argparse
import csv
import json
import pathlib
import sys
from collections import OrderedDict
from datetime import date, timedelta
from functools import lru_cache

PARAMS = json.loads((pathlib.Path(__file__).with_name("parametros_mx.json")).read_text(encoding="utf-8"))
_INHABILES_EXTRA = {date.fromisoformat(f) for f in PARAMS["dias_inhabiles"]["fechas"]}


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


def tabla_resico(anio):
    """Bloque de la tabla mensual RESICO PF (LISR 113-E) del ejercicio, con fuente, calidad y tope anual."""
    for bloque in PARAMS["resico_pf_mensual"].values():
        if anio in bloque["ejercicios"]:
            return bloque
    raise KeyError(f"No hay tabla RESICO para el ejercicio {anio}; agrégala a parametros_mx.json con su fuente")


def tasa_resico(ingreso_cobrado, anio):
    """Una sola tasa según el total cobrado del mes (no es marginal). Por encima del último renglón devuelve la
    última tasa: quien llama debe avisar que el mes rebasa el tope."""
    filas = tabla_resico(anio)["filas"]
    for limite, tasa in filas:
        if ingreso_cobrado <= limite:
            return tasa
    return filas[-1][1]


def resico_mensual(ingreso_cobrado, anio):
    """ISR mensual RESICO PF del ejercicio `anio`."""
    return ingreso_cobrado * tasa_resico(ingreso_cobrado, anio) if ingreso_cobrado > 0 else 0.0


def _lunes(anio, mes, n):
    d = date(anio, mes, 1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d + timedelta(weeks=n - 1)


@lru_cache(maxsize=None)
def inhabiles(anio):
    """Días inhábiles del CFF art. 12 para cualquier año (1 ene, primer lunes de feb, tercer lunes de mar, 1 y 5 de
    may, 16 sep, tercer lunes de nov, 25 dic) más los que se agreguen a mano en parametros_mx.json."""
    reglas = {date(anio, 1, 1), _lunes(anio, 2, 1), _lunes(anio, 3, 3), date(anio, 5, 1), date(anio, 5, 5),
              date(anio, 9, 16), _lunes(anio, 11, 3), date(anio, 12, 25)}
    return frozenset(reglas | {d for d in _INHABILES_EXTRA if d.year == anio})


def vencimiento_mensual(anio, mes):
    """Día 17 del mes siguiente; si es sábado, domingo o inhábil, se recorre al siguiente hábil (CFF art. 12)."""
    a, m = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    d = date(a, m, 17)
    while d.weekday() >= 5 or d in inhabiles(d.year):
        d += timedelta(days=1)
    return d


def _meses_o_fraccion(desde, hasta):
    if hasta <= desde:
        return 0
    n = (hasta.year - desde.year) * 12 + (hasta.month - desde.month)
    return n + (1 if hasta.day > desde.day else 0)


def recargos_pct(desde, hasta, supuestos=None):
    """Suma la tasa mensual de mora de cada mes o fracción transcurrido (CFF art. 21). Los años sin tasa en
    parametros_mx.json usan la del último año disponible y se agregan a `supuestos` (un set) para avisarlo."""
    tasas = PARAMS["recargos_mora_mensual"]["valores"]
    ultimo = max(tasas)
    total, a, m = 0.0, desde.year, desde.month
    for _ in range(_meses_o_fraccion(desde, hasta)):
        if str(a) not in tasas and supuestos is not None:
            supuestos.add((a, ultimo))
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


def tasa_plazos(n, anio):
    t = PARAMS["recargos_plazos_mensual"].get(str(anio))
    if t is None:
        raise KeyError(f"No hay tasas de pago a plazos para {anio} (LIF {anio}, art. 11); agrégalas a parametros_mx.json")
    return t["hasta_12"] if n <= 12 else t["hasta_24"] if n <= 24 else t["mas_de_24_o_diferido"]


def tc_para(fecha, tipos_cambio):
    """(tipo de cambio, fecha de la que se tomó): el de esa fecha o, si falta, el último publicado antes."""
    if fecha in tipos_cambio:
        return tipos_cambio[fecha], fecha
    previas = [f for f in tipos_cambio if f < fecha]
    if not previas:
        raise KeyError(f"Falta el tipo de cambio fiscal del {fecha} y no hay uno anterior en el CSV")
    f = max(previas)
    return tipos_cambio[f], f


def provisionales(depositos, tipos_cambio, hoy, pago):
    """Agrupa depósitos por mes de cobro y calcula ISR provisional, vencimiento y recargos sin actualizar.

    depositos: dicts con fecha (AAAA-MM-DD), usd y/o mxn. Si hay usd se usa el tipo de cambio "para pagos" de esa
    fecha (publicado en el DOF el día hábil anterior) o el último publicado antes; si solo hay mxn, se usa tal cual.
    """
    meses = OrderedDict()
    for d in sorted(depositos, key=lambda x: x["fecha"]):
        f = d["fecha"]
        if d.get("usd"):
            tc, tc_fecha = tc_para(f, tipos_cambio)
            mxn = float(d["usd"]) * tc
        else:
            tc, tc_fecha, mxn = None, None, float(d["mxn"])
        meses.setdefault(f[:7], []).append({**d, "tc": tc, "tc_fecha": tc_fecha, "mxn_fiscal": mxn})
    salida = []
    for mes, detalle in meses.items():
        anio, m = int(mes[:4]), int(mes[5:])
        mxn = sum(x["mxn_fiscal"] for x in detalle)
        impuesto = isr(mxn, tarifa("mensual", anio))
        vence = vencimiento_mensual(anio, m)
        vencido = vence < hoy
        supuestos = set()
        recargos = impuesto * recargos_pct(vence, pago, supuestos) if vencido else 0.0
        salida.append({"mes": mes, "detalle": detalle, "mxn": mxn, "isr": impuesto, "vence": vence,
                       "vencido": vencido, "recargos": recargos, "supuestos": supuestos})
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
    print("| Mes | Depósitos | Ingreso fiscal MXN | ISR provisional | Vence | Estado | Recargos sin actualizar (mínimo) "
          "| ¿Pago a plazos? |")
    print("|---|---|---|---|---|---|---|---|")
    por_anio, supuestos, tc_previos = {}, set(), []
    for m in meses:
        dets = "; ".join(f"{x['fecha']} " + (f"{float(x['usd']):,.2f} USD x {x['tc']:.4f}" if x["tc"] else
                                              f"{x['mxn_fiscal']:,.2f} MXN") for x in m["detalle"])
        tc_previos += [x for x in m["detalle"] if x["tc"] and x["tc_fecha"] != x["fecha"]]
        estado = "vencido" if m["vencido"] else "en tiempo"
        plazos = "sí" if elegible_plazos(m["vence"], solicitud) else "no (66-A VI a)"
        print(f"| {m['mes']} | {dets} | {m['mxn']:,.2f} | {m['isr']:,.2f} | {m['vence']} | {estado} | "
              f"{m['recargos']:,.2f} | {plazos} |")
        supuestos |= m["supuestos"]
        t = por_anio.setdefault(m["mes"][:4], {"mxn": 0, "isr": 0, "vencido": 0, "rec": 0})
        t["mxn"] += m["mxn"]; t["isr"] += m["isr"]; t["rec"] += m["recargos"]
        t["vencido"] += m["isr"] if m["vencido"] else 0
    print()
    for anio, t in por_anio.items():
        print(f"- {anio}: ingreso {t['mxn']:,.2f}; ISR provisional {t['isr']:,.2f} (vencido {t['vencido']:,.2f}); "
              f"recargos sin actualizar {t['rec']:,.2f}")
        b = _bloque("mensual", int(anio))
        print(f"  Tarifa mensual {anio}: {b['fuente']} ({b['calidad']})")
    print(f"- Recargos hasta {a.pago}, por mes o fracción, calculados sobre el ISR SIN actualizar: son un mínimo. "
          "La actualización por INPC y los recargos sobre el monto actualizado los calcula el portal.")
    for anio, base in sorted(supuestos):
        print(f"- !! {anio}: sin tasa de recargos en parametros_mx.json; se usó la de {base}. Agrega la de la LIF {anio}.")
    for x in tc_previos:
        print(f"- !! {x['fecha']}: sin tipo de cambio en el CSV; se usó el del {x['tc_fecha']} (último publicado).")


def _cmd_anual(a):
    impuesto = isr(a.gravado, tarifa("anual", a.ejercicio))
    dif = a.retenido + a.pagado - impuesto
    print(f"Ejercicio {a.ejercicio}: gravado {a.gravado:,.2f}; ISR anual {impuesto:,.2f}; "
          f"retenido {a.retenido:,.2f}; pagos provisionales {a.pagado:,.2f}")
    print(("Saldo a favor" if dif >= 0 else "ISR a cargo") + f": {abs(dif):,.2f}")
    print(f"Tarifa: {_bloque('anual', a.ejercicio)['fuente']} ({_bloque('anual', a.ejercicio)['calidad']})")


def _cmd_resico(a):
    anio, mes = int(a.mes[:4]), int(a.mes[5:7])
    b = tabla_resico(anio)
    tasa = tasa_resico(a.ingresos, anio) if a.ingresos > 0 else 0.0
    impuesto = a.ingresos * tasa
    isr_cargo = impuesto - a.retenido_isr
    iva_cargo = a.iva_trasladado - a.iva_acreditable - a.iva_retenido
    print(f"RESICO PF {a.mes}: ingresos cobrados sin IVA {a.ingresos:,.2f}; tasa única {tasa:.2%}; ISR {impuesto:,.2f}")
    print(f"- ISR retenido por personas morales {a.retenido_isr:,.2f} -> "
          + (f"a cargo {isr_cargo:,.2f}" if isr_cargo >= 0 else f"a favor {-isr_cargo:,.2f}"))
    print(f"- IVA: trasladado {a.iva_trasladado:,.2f} - acreditable {a.iva_acreditable:,.2f} - retenido "
          f"{a.iva_retenido:,.2f} -> " + (f"a cargo {iva_cargo:,.2f}" if iva_cargo >= 0 else f"a favor {-iva_cargo:,.2f}"))
    print(f"- Vence: {vencimiento_mensual(anio, mes)} (día 17 recorrido, CFF art. 12)")
    if a.ingresos > b["filas"][-1][0]:
        print(f"- !! El mes rebasa el último renglón de la tabla ({b['filas'][-1][0]:,.2f}): revisa la salida del régimen.")
    print(f"- Tabla: {b['fuente']} ({b['calidad']})")


def _cmd_plazos(a):
    inicial = 0.20 * a.monto
    print(f"Adeudo {a.monto:,.2f}; pago inicial 20%: {inicial:,.2f} (CFF art. 66)")
    for n in (12, 24, 36):
        tasa = tasa_plazos(n, a.ejercicio)
        c = parcialidad(a.monto - inicial, n, tasa)
        print(f"- {n} parcialidades al {tasa:.2%} (LIF {a.ejercicio}): ~{c:,.2f} al mes; total ~{inicial + c * n:,.2f}")
    print("Sin garantía si se paga cada parcialidad a tiempo (RMF 2026 regla 2.11.5).")
    print("OJO: solo entran adeudos que NO vencieron en el año en curso ni en los 6 meses previos a la solicitud "
          "(CFF 66-A, fr. VI, a). Usa la columna '¿Pago a plazos?' de 'provisionales' para separar el monto elegible.")


def _cmd_tarifa(a):
    b = _bloque(a.tipo, a.ejercicio)
    print(f"Tarifa {a.tipo} {a.ejercicio}: {b['fuente']} ({b['calidad']})")
    for li, cuota, tasa in b["filas"]:
        print(f"  desde {li:>14,.2f}  cuota {cuota:>14,.2f}  tasa {tasa:.2%}")


def vigencia(anio):
    """Lista de (parámetro, presente, de dónde sale) para el ejercicio."""
    def hay(f):
        try:
            f()
            return True
        except KeyError:
            return False
    return [
        ("Tarifa mensual art. 96", hay(lambda: _bloque("mensual", anio)),
         f"Anexo 8 de la RMF {anio} (DOF de fines de diciembre de {anio - 1})"),
        ("Tarifa anual art. 152", hay(lambda: _bloque("anual", anio)), f"Anexo 8 de la RMF {anio}"),
        ("Tabla RESICO PF art. 113-E", hay(lambda: tabla_resico(anio)), "LISR vigente (revisar reformas del año)"),
        ("UMA diaria", str(anio) in PARAMS["uma_diaria"]["valores"], f"INEGI, enero de {anio}"),
        ("Recargos por mora", str(anio) in PARAMS["recargos_mora_mensual"]["valores"], f"LIF {anio}, art. 11, x 1.5 (CFF art. 21)"),
        ("Tasas de pago a plazos", str(anio) in PARAMS["recargos_plazos_mensual"], f"LIF {anio}, art. 11"),
    ]


def _cmd_vigencia(a):
    filas = vigencia(a.ejercicio)
    faltan = [f for f in filas if not f[1]]
    print(f"Parámetros del ejercicio {a.ejercicio} en parametros_mx.json:")
    for nombre, presente, fuente in filas:
        print(f"- {'OK   ' if presente else 'FALTA'} {nombre}" + ("" if presente else f": {fuente}"))
    print("- Días inhábiles: se generan con las reglas del CFF art. 12; agrega a mano los días extra que publique el SAT.")
    print("- Facilidades anuales de la RMF (relevo de la anual 3.17.11 y 3.13.7, devolución automática 2.3.2): "
          f"confírmalas en la RMF {a.ejercicio + 1} antes de la anual del ejercicio {a.ejercicio}.")
    if faltan:
        sys.exit(1)


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
    s.add_argument("--gravado", type=float, required=True,
                   help="ingresos acumulables menos exentos y deducciones personales (sin indemnización: art. 95)")
    s.add_argument("--retenido", type=float, default=0.0)
    s.add_argument("--pagado", type=float, default=0.0, help="pagos provisionales efectivamente hechos")
    s.set_defaults(f=_cmd_anual)
    s = sub.add_parser("resico", help="ISR e IVA de un mes RESICO PF a partir de montos")
    s.add_argument("--mes", required=True, help="AAAA-MM")
    s.add_argument("--ingresos", type=float, required=True, help="cobrado en el mes sin IVA, menos notas de crédito")
    s.add_argument("--retenido-isr", type=float, default=0.0, help="ISR retenido por personas morales (1.25%%)")
    s.add_argument("--iva-trasladado", type=float, default=0.0)
    s.add_argument("--iva-acreditable", type=float, default=0.0)
    s.add_argument("--iva-retenido", type=float, default=0.0)
    s.set_defaults(f=_cmd_resico)
    s = sub.add_parser("plazos", help="opciones de pago a plazos")
    s.add_argument("--monto", type=float, required=True)
    s.add_argument("--ejercicio", type=int, default=date.today().year, help="año de la LIF cuyas tasas se aplican")
    s.set_defaults(f=_cmd_plazos)
    s = sub.add_parser("tarifa", help="imprime una tarifa con su fuente")
    s.add_argument("--tipo", choices=["mensual", "anual"], required=True)
    s.add_argument("--ejercicio", type=int, required=True)
    s.set_defaults(f=_cmd_tarifa)
    s = sub.add_parser("vigencia", help="qué parámetros faltan para un ejercicio (sale con 1 si falta alguno)")
    s.add_argument("--ejercicio", type=int, default=date.today().year)
    s.set_defaults(f=_cmd_vigencia)
    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main(sys.argv[1:])
