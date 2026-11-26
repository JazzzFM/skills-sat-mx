---
name: declarando-resico-pf
description: Usar cuando una persona física en RESICO (Régimen Simplificado de Confianza, clave 626) pregunta cuánto ISR o IVA paga en un mes, cómo cuadrar la declaración mensual prellenada, si una factura va en PUE o PPD, cuándo emitir el complemento de pago, cómo hacer la factura global, qué hacer con la retención de 1.25% o un saldo a favor, si debe presentar la anual RESICO, qué pasa si no declara un mes sin ingresos, o si puede entrar o seguir en RESICO (incluido quien además tiene sueldo).
---

# Declarando RESICO persona física

## Principio

El pago mensual del RESICO es **definitivo**: una sola tasa sobre lo **efectivamente cobrado** en el mes, sin IVA y sin deducciones (LISR art. 113-E). El SAT lo precarga con tus CFDI, así que la forma de facturar decide el impuesto. El agente calcula, cuadra y explica; el titular presenta, paga y timbra sus propias facturas. **REQUIRED SUB-SKILL:** protegiendo-datos-y-tramites-sat. Los comandos se corren desde la raíz del repo. Cifras vigentes para el ejercicio 2026 (corte de la investigación: 26/10/2026); revisa `herramientas/parametros_mx.json` antes de usarlas en otro ejercicio.

## 1. ¿Puede estar en RESICO?

| Puede | No puede |
|---|---|
| Actividad empresarial, honorarios, arrendamiento o agro, con ingresos del año anterior de hasta $3,500,000 (113-E) | Socios o accionistas de personas morales (salvo las excepciones de la regla 3.13.9) y partes relacionadas |
| Además con sueldo o intereses, si el total **en conjunto** no rebasa $3,500,000 (113-E, sexto párrafo) | Residentes en el extranjero con establecimiento permanente; ingresos de regímenes preferentes |
| RFC activo, opinión de cumplimiento positiva y fuera de la lista 69-B (113-H) | Asimilados de las fracciones III a VI del art. 94 (consejeros, honorarios preponderantes, quien optó por asimilados) |
| | Ingresos por plataformas que causan el ISR del art. 113-A, por esos ingresos (regla 3.13.3; la restricción está en la RMF, no en la LISR) |

Nunca sugieras pasar a un trabajador subordinado a RESICO: simularlo es calificativa de defraudación (CFF art. 108). La reforma de 2027 que sube el tope a $5,000,000 no aplica a 2026 (al corte solo la aprobó la Cámara de Diputados); verifica su publicación en el DOF.

## 2. Calcular el mes desde los XML

Pide los XML emitidos y recibidos del mes (portal "Consulta y recuperación de facturas", que el titular descarga) y córrelos:

```bash
python3 -I herramientas/cfdi_mx.py resico --rfc <RFC> --mes AAAA-MM personal/cfdi/AAAA-MM/*.xml [--excluir <UUID cancelados>]
```

Sin XML, aplica las mismas reglas a mano:

| Concepto | Regla |
|---|---|
| Ingreso cobrado | Facturas de ingreso **PUE** del mes + pagos con **complemento** (FechaPago en el mes) + factura global; sin IVA |
| Factura PPD | Cuenta en el mes en que se cobra, y el SAT solo la ve cuando existe su complemento de pago |
| Notas de crédito (egreso PUE) | Restan en su mes |
| Tasa | **Una sola** según el total del mes: hasta $25,000: 1.00%; $50,000: 1.10%; $83,333.33: 1.50%; $208,333.33: 2.00%; $3,500,000: 2.50%. Con $30,000 el ISR es $330, no un cálculo por tramos |
| ISR retenido | Las personas morales retienen 1.25% (113-J); se resta del ISR del mes |
| IVA | Trasladado cobrado − acreditable − retenido. Acreditable: IVA de gastos que serían deducibles para la actividad aunque no se deduzcan en ISR (regla 3.13.18); nunca gastos personales (D01-D10) |
| IVA retenido | Personas morales que reciben honorarios o arrendamiento retienen IVA (LIVA 1o.-A). Que sean dos terceras partes (10.6667%) viene del Reglamento, no verificado en fuente primaria |

## 3. Cuadrar contra la precarga (lo hace el titular en el portal)

Declaraciones "ISR simplificado de confianza. Personas físicas" e "IVA simplificado de confianza" (reglas 3.13.7 y 3.13.19), en Declaraciones y Pagos. Guíalo pantalla por pantalla:

1. Clic en "Total de ingresos efectivamente cobrados" para ver las facturas que tomó el SAT y compararlas con tu tabla.
2. Cobro sin complemento: primero emite el complemento; si ya no da tiempo, "Ingresos adicionales".
3. Factura en proceso de cancelación o ya acumulada en otro mes: "Ingresos a disminuir".
4. "ISR retenido por personas morales" → "Ver detalle" contra los CFDI con retención.
5. Vista previa, enviar, guardar acuse y, si hay saldo, la línea de captura. Una declaración se corrige con complementarias, con límite de tres (CFF art. 32): valida antes de enviar.

## 4. Saldo a favor, vencimientos y atrasos

- **Saldo a favor del mes** (retenciones mayores al impuesto): se pide en devolución en el mes inmediato siguiente, o la suma del ejercicio a partir del 17 de enero del año siguiente con el FED, ficha 70/CFF (regla 3.13.34). No digas que "se acredita en la anual".
- **Vencimiento:** día 17 del mes siguiente, recorrido al siguiente hábil (CFF art. 12; la herramienta lo imprime). La prórroga por viernes del art. 12 es solo para el pago en bancos. Los días adicionales por el sexto dígito del RFC solo tienen fuente secundaria para 2026: no cuentes con ellos.
- **Atraso:** sin multa si se cumple antes de un requerimiento (CFF art. 73), así que el titular revisa primero su Buzón Tributario. Los saldos a cargo causan actualización y recargos (2.07% mensual en 2026), que el portal calcula.
- **Omisiones:** tres o más pagos mensuales omitidos en un año calendario, consecutivos o no, sacan del RESICO **sin regreso** (113-I y 113-E, séptimo párrafo) y permiten restringir el sello digital (CFF 17-H Bis, fr. I). Cuenta las omisiones del año. Un mes sin ingresos se presenta **en ceros**: ninguna regla lo releva (salvo el sector primario exento); es inferencia, no texto expreso.

## 5. La anual: dos caras

Preséntalo así, siempre con las dos:

- **Ley:** LISR arts. 113-E (cuarto párrafo), 113-F y 113-G (fr. VII) exigen la anual, y el 113-I lista su omisión como causa de salida.
- **Facilidad:** la regla 3.13.7 de la RMF 2026 la releva "únicamente por los ingresos" RESICO, y el portal la rotula "Opcional". La anual del ejercicio 2026 (abril de 2027) dependerá de la RMF 2027, que sale a fines de diciembre: confírmala.
- **Con sueldo:** la anual por sueldos e intereses se determina **aparte** (regla 3.13.8), en otro formulario con su propio acuse, y su obligación se revisa con **REQUIRED SUB-SKILL:** diagnosticando-asalariado-sat.
- No está confirmado en fuente primaria que una anual RESICO opcional recupere la diferencia entre las tasas mensuales y la tabla anual: no lo prometas.

## 6. Facturar como emisor (timbra el titular)

El agente prepara los datos; el titular timbra con el Servicio gratuito de facturación del SAT, la app Factura SAT Móvil o su proveedor (PAC), con su e.firma o Contraseña.

| Caso | Cómo |
|---|---|
| Cobrado al emitir o antes de terminar el mes | PUE con la forma de pago real (regla 2.7.1.39) |
| Se cobra después | PPD con forma 99; por cada cobro, un CFDI de pago (complemento 2.0) **a más tardar el día 5 natural del mes siguiente** al cobro (regla 2.7.1.32) |
| Cliente persona moral | Régimen del emisor 626; retención de ISR 1.25% expresada en la factura (impuesto 001, tasa 0.012500; regla 3.13.13) |
| Cliente que no pide factura | Global a RFC XAXX010101000, "PUBLICO EN GENERAL", régimen 616, uso S01, dentro de las 24 horas siguientes al cierre del periodo (regla 2.7.1.21) |
| Cancelar | Nunca un CFDI al que el receptor ya dio efectos (113-F, último párrafo). La global se puede cancelar hasta abril del año siguiente por la regla 3.13.29, aunque la ley dice "en el mes" |

Todo lo cobrado debe tener CFDI: si el SAT detecta ingresos sin factura, sale del régimen (113-G, fr. VI).

## Salida

1. La tabla por mes de `cfdi_mx.py resico` (o la misma estructura a mano): cobrado, notas de crédito, ingresos, tasa, ISR, retenido, a cargo o a favor, IVA y vencimiento.
2. Acciones antes de declarar: complementos pendientes, cancelados a excluir, qué capturar en cada campo del portal.
3. Supuestos marcados y la fuente de cada cifra secundaria.
4. "Valida con un contador o con PRODECON antes de presentar."

## Errores comunes

| Error | Corrección |
|---|---|
| Tasa por tramos (1% de los primeros $25,000 y 1.1% del resto) | Una sola tasa sobre todo el mes |
| Contar la PPD cuando se emite | Cuenta al cobrarla, y el SAT la ve con su complemento |
| "El saldo a favor se acredita en la anual" | Devolución mensual o conjunta desde el 17 de enero (3.13.34) |
| "La anual RESICO es obligatoria" o "es opcional" a secas | Ley contra regla 3.13.7, y confirmar la RMF del año |
| Sumar sueldo y RESICO en una sola anual | Dos determinaciones separadas (3.13.8) |
| Dejar sin declarar un mes sin ingresos | En ceros; tres omisiones en el año sacan del régimen sin regreso |
| Contar con días adicionales por RFC | Fuente secundaria; usar el día 17 recorrido |
| IVA acreditable de gastos personales | Solo gastos de la actividad (3.13.18) |
| Aplicar el tope de $5 millones a 2026 | 2026 sigue en $3,500,000 |
