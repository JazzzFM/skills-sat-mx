"""Genera documentos sintéticos (persona ficticia) para probar herramientas y skills.

Nada aquí corresponde a una persona real. Uso:
    python3 tests/fixtures/fabrica.py <directorio_destino>
Crea:
    <dest>/estados_desordenados/   carpeta "como la descarga el usuario" (duplicados, ._*, xml, imágenes)
    <dest>/referencia/                 carpeta ya ordenada con la convención institucion/fecha_inst-prod_tipo
    <dest>/sat/                    Constancia y exportaciones del Visor de nómina
"""
import pathlib
import sys

RFC = "LOPA900101AB1"
CURP = "LOPA900101MDFPRN01"
NOMBRE = "ANA LOPEZ PEREZ"
PATRON_EXT = "ACME LABS, INC."


def _escapar(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf(lineas, creado="20260101000000"):
    """PDF mínimo válido con una línea de texto por renglón (Helvetica, WinAnsi)."""
    cuerpo = ["BT /F1 9 Tf 40 800 Td 11 TL"]
    for l in lineas:
        cuerpo.append(f"({_escapar(l)}) Tj T*")
    cuerpo.append("ET")
    stream = "\n".join(cuerpo).encode("latin-1", "replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        f"<< /Producer (fabrica) /CreationDate (D:{creado}) >>".encode(),
    ]
    salida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objetos, 1):
        offsets.append(len(salida))
        salida += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        salida += f"{off:010d} 00000 n \n".encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(salida)


def banamex(periodo, movimientos):
    lineas = ["Página 1 de 3", "Estado de Cuenta", f"{NOMBRE} MiCuenta", "CALLE FICTICIA 1 COL CENTRO",
              periodo, "Detalle de Operaciones En pesos Moneda Nacional", "FECHA CONCEPTO RETIROS DEPÓSITOS SALDO"]
    for dia, usd, tc, mxn in movimientos:
        lineas += [f"{dia} PAGO RECIBIDO DE {PATRON_EXT}", "SU REF.G0000000001 PAYROLL", "DIVISA:USD IMPORTE:",
                   f"${usd:.2f}/TC ${tc:.2f}", f"HORA 12:00 SUC 2132 {mxn:,.2f} {mxn:,.2f}",
                   f"{dia} COMISION TRANSFERENCIA", "RECEPCION INTERNACIONAL", "HORA 12:00 SUC 2132 250.00"]
    return lineas


def dolarapp(mes_txt, inicio, fin, deposito):
    dia, usd = deposito
    return ["Dólares digitales Estado de Cuenta", "Generado el October 26, 2026", "DÓLARAPP MÉXICO S.A. DE C.V.",
            f"{NOMBRE}", "Fechas de Estado de Cuenta", f"Fecha de inicio {inicio}", f"Fecha de fin {fin}",
            "Fecha Tipo Monto Moneda Monto Local Descripción",
            f"{mes_txt} 02 Venta USDc - 58 MXN - 1,000 {NOMBRE}",
            f"{mes_txt} {dia} Compra USDc + {usd:,} USD + {usd:,} {PATRON_EXT}",
            f"{mes_txt} {dia} Comisión -3 N/A N/A Compra USDc comisión",
            f"{mes_txt} 20 Venta USDc - 600 MXN - 10,500 {NOMBRE}"]


def visor_anual(anio, ini, fin, total, exento, isr, patrones):
    l = ["Información de tus ingresos y retenciones", "por sueldos y salarios",
         f"Acumulado anual total - Ejercicio: {anio}", f"Periodo que ampara la información {anio} {ini} {fin}",
         f"RFC {RFC} CURP {CURP}", f"Nombre {NOMBRE}", "Sueldos y salarios",
         f"Total de ingresos por sueldos y salarios ${total:,.2f} $0.00", "correspondió",
         "Total de ingresos exento por sueldos y Subsidio para el empleo entregado en",
         f"${exento:,.2f} $0.00", "salarios efectivo", "Total de ingresos por indemnización $0.00 $0.00",
         "Impuesto sobre la renta retenido", f"ISR retenido ${isr:,.2f}", "Datos del retenedor(es)"]
    l += [f"RFC {r} {n}" for r, n in patrones]
    return l


def generar(dest):
    dest = pathlib.Path(dest)
    d = dest / "estados_desordenados"
    (d / "Finanzas_Legal").mkdir(parents=True, exist_ok=True)
    (d / "Nu").mkdir(exist_ok=True)
    escribir = lambda p, b: (p.parent.mkdir(parents=True, exist_ok=True), p.write_bytes(b))

    nov = banamex("Período del 5 de octubre al 4 de noviembre del 2025", [("14 OCT", 2500.00, 18.20, 45500.00)])
    dic = banamex("Período del 5 de noviembre al 4 de diciembre del 2025", [("14 NOV", 2500.00, 18.10, 45250.00)])
    ene = banamex("Período del 5 de diciembre del 2025 al 4 de enero del 2026", [("15 DIC", 2800.00, 17.80, 49840.00)])
    escribir(d / "EstadodeCuenta.pdf", pdf(nov, "20261026100000"))
    escribir(d / "EstadodeCuenta-1.pdf", pdf(dic, "20261026100100"))
    escribir(d / "EstadodeCuenta-2.pdf", pdf(dic, "20261026100200"))  # mismo texto, otro hash
    escribir(d / "EstadodeCuenta-3.pdf", pdf(ene, "20261026100300"))
    escribir(d / "Estado de cuenta ARQ - 2026-05.pdf",
             pdf(dolarapp("May", "1 May 2026", "31 May 2026", (15, 2700))))
    # DólarApp escribe el mes completo en las fechas del periodo cuando no es de 3 letras
    escribir(d / "Estado de cuenta ARQ - 2026-04.pdf",
             pdf(dolarapp("Apr", "1 April 2026", "30 April 2026", (15, 2500))))
    # Con meses largos el bloque de fechas se parte en renglones y se mezcla con la columna de saldos
    sep = dolarapp("Sep", "", "", (15, 2700))
    sep[5:7] = ["Fecha de inicio 1 September Balance de inicio $ 0.49", "Fecha de fin 2026 Ingresos $ 2,700.00",
                "Duración 30 September Retiros $ 2,700.43", "2026 Balance Final $ 0.05", "(30 Días)"]
    escribir(d / "Estado de cuenta ARQ - 2026-09.pdf", pdf(sep))
    escribir(d / "._EstadodeCuenta.pdf", b"\x00\x05\x16\x07" + b"\x00" * 4092)
    escribir(d / "EstadodeCuenta.xml", (
        '<?xml version="1.0" encoding="utf-8"?>\n<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        'Fecha="2025-11-05T12:00:00" TipoDeComprobante="I" Total="290.00"><cfdi:Emisor Nombre="BANCO FICTICIO" '
        'Rfc="BFI010101AAA"/><cfdi:Conceptos><cfdi:Concepto Descripcion="COMISION COBRADA"/></cfdi:Conceptos>'
        '</cfdi:Comprobante>\n').encode())
    escribir(d / "Finanzas_Legal" / "Factura_Oct 2025.pdf",
             pdf(["TELEFONIA FICTICIA", "Periodo: 15-Sep-2025 al 14-Oct-2025", "Fecha límite de pago: 30 - Oct - 25",
                  "Total a pagar $499.00"]))
    tdc = pdf(["Klar", "Estado de cuenta tarjeta de crédito", "Fecha de corte 31/10/2025", "Saldo $1,200.00"])
    escribir(d / "Finanzas_Legal" / "credit-statement-123456.pdf", tdc)
    escribir(d / "Finanzas_Legal" / "IMG_0001.PNG",
             bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                           "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"))
    escribir(dest / "referencia" / "klar" / "2025-10-31_klar-tdc_estado-cuenta.pdf", tdc)

    s = dest / "sat"
    escribir(s / f"Csf_{RFC}.pdf", pdf([
        "CONSTANCIA DE SITUACIÓN FISCAL", f"RFC: {RFC}", f"CURP: {CURP}", "Nombre (s): ANA",
        "Estatus en el padrón: ACTIVO", "Actividades Económicas:", "1 Asalariado 100 01/03/2018",
        "Regímenes:", "Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios 01/03/2018"]))
    escribir(s / f"Anual.{RFC}.2023.pdf", pdf(visor_anual(2023, "Enero", "Diciembre", 380000.00, 20000.00,
                                                          70000.00, [("EFI010101AAA", "EMPRESA FICTICIA SA DE CV")])))
    escribir(s / f"Anual.{RFC}.2024.pdf", pdf(visor_anual(2024, "Enero", "Diciembre", 450000.00, 25000.00,
                                                          90000.00, [("EFI010101AAA", "EMPRESA FICTICIA SA DE CV"),
                                                                      ("OTR020202BBB", "OTRA FICTICIA SA DE CV")])))
    anual_2025 = visor_anual(2025, "Enero", "Julio", 300000.00, 8000.00, 55000.00,
                             [("EFI010101AAA", "EMPRESA FICTICIA SA DE CV")])
    escribir(s / f"Anual.{RFC}.2025.pdf", pdf(anual_2025, "20261026090000"))
    escribir(s / f"Anual.{RFC}.2025-1.pdf", pdf(anual_2025, "20261026090500"))  # misma descarga repetida
    return dest


if __name__ == "__main__":
    print(generar(sys.argv[1]))
