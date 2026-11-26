"""CFDI 4.0 sintéticos (persona ficticia) para probar cfdi_mx.py y autofactura.py. Nada es real."""
import pathlib

RFC_PF = "LOPA900101AB1"          # persona ficticia: RESICO y asalariada
NOMBRE_PF = "ANA LOPEZ PEREZ"
CP_PF = "06700"
RFC_CLIENTE = "EKU9003173C9"      # RFC de pruebas que el SAT publica para CSD de prueba
RFC_GAS = "GAS010101AA1"
RFC_PATRON = "ACM010101AB1"

_NS = ('xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
       'xmlns:pago20="http://www.sat.gob.mx/Pagos20" xmlns:nomina12="http://www.sat.gob.mx/nomina12" '
       'xmlns:iedu="http://www.sat.gob.mx/iedu"')


def _tfd(uuid, fecha):
    return f'<tfd:TimbreFiscalDigital Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha}T12:05:00"/>'


def comprobante(uuid, tipo, fecha, subtotal, total, emisor, receptor, metodo="PUE", forma="03", serie="A", folio="1",
                iva=0.0, ret_isr=0.0, ret_iva=0.0, complemento="", moneda="MXN", tipo_cambio=None, extra_receptor=""):
    """emisor/receptor: (rfc, nombre, regimen) y (rfc, nombre, cp, regimen, uso)."""
    impuestos = ""
    if iva or ret_isr or ret_iva:
        ret = ""
        if ret_isr or ret_iva:
            ret = "<cfdi:Retenciones>"
            if ret_isr:
                ret += f'<cfdi:Retencion Impuesto="001" Importe="{ret_isr:.2f}"/>'
            if ret_iva:
                ret += f'<cfdi:Retencion Impuesto="002" Importe="{ret_iva:.2f}"/>'
            ret += "</cfdi:Retenciones>"
        tras = (f'<cfdi:Traslados><cfdi:Traslado Base="{subtotal:.2f}" Impuesto="002" TipoFactor="Tasa" '
                f'TasaOCuota="0.160000" Importe="{iva:.2f}"/></cfdi:Traslados>') if iva else ""
        impuestos = f"<cfdi:Impuestos>{ret}{tras}</cfdi:Impuestos>"
    mp = f' MetodoPago="{metodo}"' if metodo else ""
    fp = f' FormaPago="{forma}"' if forma else ""
    tc = f' TipoCambio="{tipo_cambio}"' if tipo_cambio else ""
    return (f'﻿<?xml version="1.0" encoding="UTF-8"?>\n<cfdi:Comprobante {_NS} Version="4.0" Serie="{serie}" '
            f'Folio="{folio}" Fecha="{fecha}T12:00:00" SubTotal="{subtotal:.2f}" Moneda="{moneda}"{tc} '
            f'Total="{total:.2f}" TipoDeComprobante="{tipo}"{mp}{fp} LugarExpedicion="06700">'
            f'<cfdi:Emisor Rfc="{emisor[0]}" Nombre="{emisor[1]}" RegimenFiscal="{emisor[2]}"/>'
            f'<cfdi:Receptor {extra_receptor}Nombre="{receptor[1]}" Rfc="{receptor[0]}" DomicilioFiscalReceptor="{receptor[2]}" '
            f'RegimenFiscalReceptor="{receptor[3]}" UsoCFDI="{receptor[4]}"/>'
            f'<cfdi:Conceptos><cfdi:Concepto ClaveProdServ="01010101" Cantidad="1" ClaveUnidad="E48" '
            f'Descripcion="x" ValorUnitario="{subtotal:.2f}" Importe="{subtotal:.2f}" ObjetoImp="02"/></cfdi:Conceptos>'
            f'{impuestos}<cfdi:Complemento>{complemento}{_tfd(uuid, fecha)}</cfdi:Complemento></cfdi:Comprobante>')


def pago20(fecha_pago, monto, base, iva, ret_isr, ret_iva, doc_uuid):
    return (f'<pago20:Pagos Version="2.0"><pago20:Totales MontoTotalPagos="{monto:.2f}"/>'
            f'<pago20:Pago FechaPago="{fecha_pago}T12:00:00" FormaDePagoP="03" MonedaP="MXN" TipoCambioP="1" '
            f'Monto="{monto:.2f}"><pago20:DoctoRelacionado IdDocumento="{doc_uuid}" MonedaDR="MXN" EquivalenciaDR="1" '
            f'NumParcialidad="1" ImpSaldoAnt="{monto:.2f}" ImpPagado="{monto:.2f}" ImpSaldoInsoluto="0.00" ObjetoImpDR="02"/>'
            f'<pago20:ImpuestosP><pago20:RetencionesP><pago20:RetencionP ImpuestoP="001" ImporteP="{ret_isr:.2f}"/>'
            f'<pago20:RetencionP ImpuestoP="002" ImporteP="{ret_iva:.2f}"/></pago20:RetencionesP>'
            f'<pago20:TrasladosP><pago20:TrasladoP BaseP="{base:.2f}" ImpuestoP="002" TipoFactorP="Tasa" '
            f'TasaOCuotaP="0.160000" ImporteP="{iva:.2f}"/></pago20:TrasladosP></pago20:ImpuestosP>'
            f'</pago20:Pago></pago20:Pagos>')


def nomina(fecha_pago, gravado, exento, isr, subsidio=0.0, tipo="O", aguinaldo_exento=0.0):
    perc = f'<nomina12:Percepcion TipoPercepcion="001" Clave="001" Concepto="Sueldo" ImporteGravado="{gravado:.2f}" ImporteExento="0.00"/>'
    if aguinaldo_exento:
        perc += (f'<nomina12:Percepcion TipoPercepcion="002" Clave="002" Concepto="Aguinaldo" ImporteGravado="0.00" '
                 f'ImporteExento="{aguinaldo_exento:.2f}"/>')
    otros = (f'<nomina12:OtrosPagos><nomina12:OtroPago TipoOtroPago="002" Clave="002" Concepto="Subsidio" '
             f'Importe="{subsidio:.2f}"><nomina12:SubsidioAlEmpleo SubsidioCausado="{subsidio:.2f}"/>'
             f'</nomina12:OtroPago></nomina12:OtrosPagos>') if subsidio else ""
    return (f'<nomina12:Nomina Version="1.2" TipoNomina="{tipo}" FechaPago="{fecha_pago}" FechaInicialPago="{fecha_pago}" '
            f'FechaFinalPago="{fecha_pago}" NumDiasPagados="15">'
            f'<nomina12:Percepciones TotalSueldos="{gravado + exento:.2f}" TotalGravado="{gravado:.2f}" '
            f'TotalExento="{exento:.2f}">{perc}</nomina12:Percepciones>'
            f'<nomina12:Deducciones TotalImpuestosRetenidos="{isr:.2f}"><nomina12:Deduccion TipoDeduccion="002" '
            f'Clave="002" Concepto="ISR" Importe="{isr:.2f}"/></nomina12:Deducciones>{otros}</nomina12:Nomina>')


def escribir(ruta, texto):
    ruta = pathlib.Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta


YO_RESICO = (RFC_PF, NOMBRE_PF, "626")
CLIENTE = (RFC_CLIENTE, "ESCUELA KEMPER URGATE", "601")


def octubre_resico(d):
    """Caso de octubre 2026: PUE 30,000; PPD de septiembre cobrada el 10/oct; nota de crédito 2,000; laptop."""
    d = pathlib.Path(d)
    cliente = (RFC_CLIENTE, "ESCUELA KEMPER URGATE", "26015", "601", "G03")
    u_ppd = "AAAAAAAA-0000-0000-0000-000000000002"
    escribir(d / "pue.xml", comprobante("AAAAAAAA-0000-0000-0000-000000000001", "I", "2026-10-03", 30000, 32425,
                                        YO_RESICO, cliente, iva=4800, ret_isr=375, ret_iva=3200, forma="03"))
    escribir(d / "ppd.xml", comprobante(u_ppd, "I", "2026-09-25", 20000, 20816.67, YO_RESICO, cliente,
                                        metodo="PPD", forma="99", iva=3200, ret_isr=250, ret_iva=2133.33))
    escribir(d / "rep.xml", comprobante("AAAAAAAA-0000-0000-0000-000000000003", "P", "2026-11-20", 0, 0, YO_RESICO,
                                        (RFC_CLIENTE, "ESCUELA KEMPER URGATE", "26015", "601", "CP01"),
                                        metodo="", forma="", complemento=pago20("2026-10-10", 20816.67, 20000, 3200,
                                                                                250, 2133.33, u_ppd)))
    escribir(d / "nc.xml", comprobante("AAAAAAAA-0000-0000-0000-000000000004", "E", "2026-10-20", 2000, 2320,
                                       YO_RESICO, (RFC_CLIENTE, "ESCUELA KEMPER URGATE", "26015", "601", "G02"),
                                       iva=320))
    escribir(d / "laptop.xml", comprobante("AAAAAAAA-0000-0000-0000-000000000005", "I", "2026-10-12", 15000, 17400,
                                           ("CTI000101AB1", "COMPUTO TIENDA", "601"),
                                           (RFC_PF, NOMBRE_PF, CP_PF, "626", "I04"), iva=2400, forma="04"))
    escribir(d / "consulta.xml", comprobante("AAAAAAAA-0000-0000-0000-000000000006", "I", "2026-10-15", 1000, 1000,
                                             ("MEDA800101AB1", "DRA MEDICA", "612"),
                                             (RFC_PF, NOMBRE_PF, CP_PF, "605", "D01"), forma="04"))
    escribir(d / "pue-copia.xml", (d / "pue.xml").read_text(encoding="utf-8"))  # descarga repetida
    return d
