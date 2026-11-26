"""CFDI sintéticos (persona ficticia) para probar cfdi_mx.py y autofactura.py. Nada es real.

Construye CFDI 4.0 y 3.3, complementos de Pagos 2.0 y Nómina 1.2, colegiaturas (iedu) y CFDI de Retenciones 2.0
con la estructura de los esquemas públicos del SAT.
"""
import pathlib

RFC_PF = "LOPA900101AB1"          # persona ficticia: RESICO y asalariada
NOMBRE_PF = "ANA LOPEZ PEREZ"
CP_PF = "06700"
RFC_CLIENTE = "EKU9003173C9"      # RFC de pruebas que el SAT publica para CSD de prueba
RFC_GAS = "GAS010101AA1"
RFC_PATRON = "ACM010101AB1"

_NS4 = 'xmlns:cfdi="http://www.sat.gob.mx/cfd/4"'
_NS3 = 'xmlns:cfdi="http://www.sat.gob.mx/cfd/3"'
_NS_EXTRA = ('xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:pago20="http://www.sat.gob.mx/Pagos20" '
             'xmlns:nomina12="http://www.sat.gob.mx/nomina12" xmlns:iedu="http://www.sat.gob.mx/iedu"')


def _tfd(uuid, fecha):
    return f'<tfd:TimbreFiscalDigital Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha}T12:05:00"/>' if uuid else ""


def comprobante(uuid, tipo, fecha, subtotal, total, emisor, receptor, metodo="PUE", forma="03", serie="A", folio="1",
                iva=0.0, ret_isr=0.0, ret_iva=0.0, complemento="", moneda="MXN", tipo_cambio=None, extra_receptor="",
                descuento=0.0, version="4.0", informacion_global=None, relacionados=None, colegiatura=None,
                antes_raiz=""):
    """emisor/receptor: (rfc, nombre, regimen) y (rfc, nombre, cp, regimen, uso).

    informacion_global: (periodicidad, meses, año). relacionados: [(tipo_relacion, [uuid, ...])].
    colegiatura: (curp, nivel). version "3.3" omite los atributos del receptor que no existen en 3.3.
    """
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
        tras = (f'<cfdi:Traslados><cfdi:Traslado Base="{subtotal - descuento:.2f}" Impuesto="002" TipoFactor="Tasa" '
                f'TasaOCuota="0.160000" Importe="{iva:.2f}"/></cfdi:Traslados>') if iva else ""
        impuestos = f"<cfdi:Impuestos>{ret}{tras}</cfdi:Impuestos>"
    mp = f' MetodoPago="{metodo}"' if metodo else ""
    fp = f' FormaPago="{forma}"' if forma else ""
    tc = f' TipoCambio="{tipo_cambio}"' if tipo_cambio else ""
    de = f' Descuento="{descuento:.2f}"' if descuento else ""
    ns = _NS3 if version.startswith("3") else _NS4
    if version.startswith("3"):
        rec = f'<cfdi:Receptor Nombre="{receptor[1]}" Rfc="{receptor[0]}" UsoCFDI="{receptor[4]}"/>'
    else:
        rec = (f'<cfdi:Receptor {extra_receptor}Nombre="{receptor[1]}" Rfc="{receptor[0]}" '
               f'DomicilioFiscalReceptor="{receptor[2]}" RegimenFiscalReceptor="{receptor[3]}" UsoCFDI="{receptor[4]}"/>')
    glob = ""
    if informacion_global:
        p, m, a = informacion_global
        glob = f'<cfdi:InformacionGlobal Periodicidad="{p}" Meses="{m}" Año="{a}"/>'
    rel = ""
    for tipo_rel, uuids in relacionados or []:
        rel += (f'<cfdi:CfdiRelacionados TipoRelacion="{tipo_rel}">'
                + "".join(f'<cfdi:CfdiRelacionado UUID="{u}"/>' for u in uuids) + "</cfdi:CfdiRelacionados>")
    comp_concepto = ""
    if colegiatura:
        curp, nivel = colegiatura
        comp_concepto = (f'<cfdi:ComplementoConcepto><iedu:instEducativas version="1.0" nombreAlumno="ALUMNO FICTICIO" '
                         f'CURP="{curp}" nivelEducativo="{nivel}" autRVOE="RVOE0001"/></cfdi:ComplementoConcepto>')
    return (f'﻿<?xml version="1.0" encoding="UTF-8"?>\n{antes_raiz}<cfdi:Comprobante {ns} {_NS_EXTRA} '
            f'Version="{version}" Serie="{serie}" Folio="{folio}" Fecha="{fecha}T12:00:00" SubTotal="{subtotal:.2f}"{de} '
            f'Moneda="{moneda}"{tc} Total="{total:.2f}" TipoDeComprobante="{tipo}"{mp}{fp} LugarExpedicion="06700">'
            f'{glob}{rel}<cfdi:Emisor Rfc="{emisor[0]}" Nombre="{emisor[1]}" RegimenFiscal="{emisor[2]}"/>{rec}'
            f'<cfdi:Conceptos><cfdi:Concepto ClaveProdServ="01010101" Cantidad="1" ClaveUnidad="E48" '
            f'Descripcion="x" ValorUnitario="{subtotal:.2f}" Importe="{subtotal:.2f}" ObjetoImp="02">{comp_concepto}'
            f'</cfdi:Concepto></cfdi:Conceptos>'
            f'{impuestos}<cfdi:Complemento>{complemento}{_tfd(uuid, fecha)}</cfdi:Complemento></cfdi:Comprobante>')


def pago20(fecha_pago, monto, base, iva, ret_isr, ret_iva, doc_uuid, saldo_insoluto=0.0):
    """Un pago que liquida un solo documento gravado al 16%."""
    return pagos20(fecha_pago, [{"uuid": doc_uuid, "pagado": monto, "base": base, "iva": iva, "ret_isr": ret_isr,
                                 "ret_iva": ret_iva, "saldo_insoluto": saldo_insoluto}])


def pagos20(fecha_pago, docs, moneda="MXN", tipo_cambio=1):
    """Un pago que liquida varios documentos. Cada doc: uuid, pagado, y si es objeto de IVA: base, iva,
    ret_isr, ret_iva (los no objeto llevan objeto="01"). ImpuestosP suma los impuestos de los documentos."""
    monto = sum(d["pagado"] for d in docs)
    drs, base_p, iva_p, risr_p, riva_p = "", 0.0, 0.0, 0.0, 0.0
    for d in docs:
        objeto = d.get("objeto", "02")
        imp = ""
        if objeto == "02":
            base_p += d["base"]; iva_p += d["iva"]; risr_p += d.get("ret_isr", 0); riva_p += d.get("ret_iva", 0)
            ret = ""
            if d.get("ret_isr") or d.get("ret_iva"):
                ret = ("<pago20:RetencionesDR>"
                       f'<pago20:RetencionDR BaseDR="{d["base"]:.2f}" ImpuestoDR="001" TipoFactorDR="Tasa" '
                       f'TasaOCuotaDR="0.012500" ImporteDR="{d.get("ret_isr", 0):.2f}"/>'
                       f'<pago20:RetencionDR BaseDR="{d["base"]:.2f}" ImpuestoDR="002" TipoFactorDR="Tasa" '
                       f'TasaOCuotaDR="0.106667" ImporteDR="{d.get("ret_iva", 0):.2f}"/></pago20:RetencionesDR>')
            imp = (f'<pago20:ImpuestosDR>{ret}<pago20:TrasladosDR><pago20:TrasladoDR BaseDR="{d["base"]:.2f}" '
                   f'ImpuestoDR="002" TipoFactorDR="Tasa" TasaOCuotaDR="0.160000" ImporteDR="{d["iva"]:.2f}"/>'
                   f'</pago20:TrasladosDR></pago20:ImpuestosDR>')
        drs += (f'<pago20:DoctoRelacionado IdDocumento="{d["uuid"]}" MonedaDR="{moneda}" EquivalenciaDR="1" '
                f'NumParcialidad="1" ImpSaldoAnt="{d["pagado"] + d.get("saldo_insoluto", 0):.2f}" '
                f'ImpPagado="{d["pagado"]:.2f}" ImpSaldoInsoluto="{d.get("saldo_insoluto", 0):.2f}" '
                f'ObjetoImpDR="{objeto}">{imp}</pago20:DoctoRelacionado>')
    impp = ""
    if base_p:
        ret = ""
        if risr_p or riva_p:
            ret = (f'<pago20:RetencionesP><pago20:RetencionP ImpuestoP="001" ImporteP="{risr_p:.2f}"/>'
                   f'<pago20:RetencionP ImpuestoP="002" ImporteP="{riva_p:.2f}"/></pago20:RetencionesP>')
        impp = (f'<pago20:ImpuestosP>{ret}<pago20:TrasladosP><pago20:TrasladoP BaseP="{base_p:.2f}" ImpuestoP="002" '
                f'TipoFactorP="Tasa" TasaOCuotaP="0.160000" ImporteP="{iva_p:.2f}"/></pago20:TrasladosP>'
                f'</pago20:ImpuestosP>')
    return (f'<pago20:Pagos Version="2.0"><pago20:Totales MontoTotalPagos="{monto:.2f}"/>'
            f'<pago20:Pago FechaPago="{fecha_pago}T12:00:00" FormaDePagoP="03" MonedaP="{moneda}" '
            f'TipoCambioP="{tipo_cambio}" Monto="{monto:.2f}">{drs}{impp}</pago20:Pago></pago20:Pagos>')


def retenciones20(uuid, fecha_exp, emisor, receptor_rfc, mes_ini, mes_fin, ejercicio, isr=0.0, iva=0.0, base=0.0,
                  receptor_nombre=NOMBRE_PF):
    """CFDI de Retenciones e información de pagos 2.0 (esquema retencionpago/2). emisor: (rfc, nombre)."""
    imp = ""
    if isr:
        imp += f'<retenciones:ImpRetenidos BaseRet="{base:.2f}" ImpuestoRet="001" MontoRet="{isr:.2f}" TipoPagoRet="01"/>'
    if iva:
        imp += f'<retenciones:ImpRetenidos BaseRet="{base:.2f}" ImpuestoRet="002" MontoRet="{iva:.2f}" TipoPagoRet="01"/>'
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<retenciones:Retenciones xmlns:retenciones="http://www.sat.gob.mx/esquemas/retencionpago/2" '
            'xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="2.0" '
            f'FechaExp="{fecha_exp}T12:00:00" LugarExpRetenc="06700" CveRetenc="14">'
            f'<retenciones:Emisor RfcE="{emisor[0]}" NomDenRazSocE="{emisor[1]}" RegimenFiscalE="601"/>'
            f'<retenciones:Receptor NacionalidadR="Nacional"><retenciones:Nacional RfcR="{receptor_rfc}" '
            f'NomDenRazSocR="{receptor_nombre}" DomicilioFiscalR="{CP_PF}"/></retenciones:Receptor>'
            f'<retenciones:Periodo MesIni="{mes_ini:02d}" MesFin="{mes_fin:02d}" Ejercicio="{ejercicio}"/>'
            f'<retenciones:Totales MontoTotOperacion="{base:.2f}" MontoTotGrav="{base:.2f}" MontoTotExent="0.00" '
            f'MontoTotRet="{isr + iva:.2f}">{imp}</retenciones:Totales>'
            f'<retenciones:Complemento>{_tfd(uuid, fecha_exp)}</retenciones:Complemento></retenciones:Retenciones>')


def nomina(fecha_pago, gravado, exento, isr, subsidio=0.0, tipo="O", aguinaldo_exento=0.0, indemnizacion=0.0,
           dias=30):
    perc = f'<nomina12:Percepcion TipoPercepcion="001" Clave="001" Concepto="Sueldo" ImporteGravado="{gravado:.2f}" ImporteExento="0.00"/>'
    if aguinaldo_exento:
        perc += (f'<nomina12:Percepcion TipoPercepcion="002" Clave="002" Concepto="Aguinaldo" ImporteGravado="0.00" '
                 f'ImporteExento="{aguinaldo_exento:.2f}"/>')
    sep = ""
    if indemnizacion:
        perc += (f'<nomina12:Percepcion TipoPercepcion="025" Clave="025" Concepto="Indemnizacion" '
                 f'ImporteGravado="{indemnizacion:.2f}" ImporteExento="0.00"/>')
        sep = f' TotalSeparacionIndemnizacion="{indemnizacion:.2f}"'
    otros = (f'<nomina12:OtrosPagos><nomina12:OtroPago TipoOtroPago="002" Clave="002" Concepto="Subsidio" '
             f'Importe="{subsidio:.2f}"><nomina12:SubsidioAlEmpleo SubsidioCausado="{subsidio:.2f}"/>'
             f'</nomina12:OtroPago></nomina12:OtrosPagos>') if subsidio else ""
    return (f'<nomina12:Nomina Version="1.2" TipoNomina="{tipo}" FechaPago="{fecha_pago}" FechaInicialPago="{fecha_pago}" '
            f'FechaFinalPago="{fecha_pago}" NumDiasPagados="{dias}">'
            f'<nomina12:Percepciones TotalSueldos="{gravado + exento:.2f}" TotalGravado="{gravado + indemnizacion:.2f}" '
            f'TotalExento="{exento:.2f}"{sep}>{perc}</nomina12:Percepciones>'
            f'<nomina12:Deducciones TotalImpuestosRetenidos="{isr:.2f}"><nomina12:Deduccion TipoDeduccion="002" '
            f'Clave="002" Concepto="ISR" Importe="{isr:.2f}"/></nomina12:Deducciones>{otros}</nomina12:Nomina>')


def escribir(ruta, texto):
    ruta = pathlib.Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta


YO_RESICO = (RFC_PF, NOMBRE_PF, "626")
CLIENTE = (RFC_CLIENTE, "ESCUELA KEMPER URGATE", "601")
RECEPTOR_CLIENTE = (RFC_CLIENTE, "ESCUELA KEMPER URGATE", "26015", "601", "G03")


def octubre_resico(d):
    """Caso de octubre 2026: PUE 30,000; PPD de septiembre cobrada el 10/oct; nota de crédito 2,000; laptop."""
    d = pathlib.Path(d)
    cliente = RECEPTOR_CLIENTE
    u_ppd = "AAAAAAAA-0000-0000-0000-000000000002"
    escribir(d / "pue.xml", comprobante("AAAAAAAA-0000-0000-0000-000000000001", "I", "2026-10-03", 30000, 31225,
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
