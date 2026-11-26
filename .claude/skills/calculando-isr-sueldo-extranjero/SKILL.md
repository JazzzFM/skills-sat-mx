---
name: calculando-isr-sueldo-extranjero
description: Usar cuando un residente en México cobra sueldo de una empresa extranjera o de un patrón que no le retiene ISR (transferencias en USD a Banamex, DólarApp/ARQ, Wise; "the taxes are your responsibility"; "external service provider" con contrato laboral) y pregunta cuánto debe, cómo se calcula, qué tipo de cambio usar, cómo regularizarse o si le conviene RESICO u honorarios.
---

# Calculando el ISR de un sueldo de patrón extranjero

## Principio

Si hay trabajo personal subordinado, es **sueldo** aunque la carta diga "contractor" (LISR art. 94). El patrón extranjero sin establecimiento no retiene, así que el trabajador hace **pago provisional mensual** con la tarifa del art. 96, a más tardar el día 17, concepto "ISR personas físicas. Salarios" (LISR art. 96, último párrafo; RMF 2026 regla 3.12.3). La anual es obligatoria (art. 98, fr. III). No causa IVA (LIVA art. 14, último párrafo). **REQUIRED SUB-SKILL:** protegiendo-datos-y-tramites-sat.

## Flujo

1. **Clasificar con evidencia.** Contrato contra carta oferta:
   - **Indicios de sueldo:** subordinación, horario, vacaciones, exclusividad, herramientas de la empresa.
   - **Ambigüedades a preguntar al patrón:** si "salario neto" significa neto de impuestos mexicanos, si tiene entidad en México que pueda pagar nómina, qué formulario firmó el trabajador (W-8BEN o W-9).
   - **Tratado México-EUA (art. 15):** el sueldo por trabajo hecho en México solo se grava en México.
2. **Depósitos reales**, no lo pactado. Sale de los estados de cuenta (**REQUIRED SUB-SKILL:** ordenando-estados-de-cuenta) a un CSV con `fecha,usd,mxn,nota`:
   - con monto en USD, llena `usd`;
   - si solo se conoce el monto en pesos, llena `mxn` y márcalo como provisional;
   - pagos devueltos o reenviados van con su fecha real de cobro.
3. **Tipo de cambio fiscal:** el de Banxico publicado en el DOF el día hábil anterior al cobro (CFF art. 20). El del banco no sirve.
   `python3 -I herramientas/tipo_cambio_banxico.py descargar --desde AAAA-MM-DD --hasta AAAA-MM-DD --salida tc.csv`
4. **Provisionales por mes de cobro** (se suman los depósitos del mes), tarifa del año de cobro, recargos de cada año y elegibilidad para plazos:
   `python3 -I herramientas/fiscal_mx.py provisionales --depositos dep.csv --tc tc.csv --hoy <hoy> --pago <fecha_pago>`
5. **Anual de cada ejercicio** con el gravado de todos los patrones:
   `python3 -I herramientas/fiscal_mx.py anual --ejercicio AAAA --gravado <mex + extranjero> --retenido <patrón MX> --pagado <provisionales pagados>`.
   El tope de aguinaldo (30 UMA), prima vacacional y PTU es **por año**: si un patrón mexicano ya lo usó, lo del extranjero grava completo.
6. **Plan de pago:**
   - **Multas:** no hay si regulariza antes de un requerimiento (CFF art. 73).
   - **Pago a plazos** (`fiscal_mx.py plazos`) solo para lo que **no** venció en el año en curso ni en los 6 meses previos a la solicitud (CFF art. 66-A, fr. VI, a). Lo demás se paga de contado, del mes más antiguo al más reciente.
   - **Compensar** saldos a favor de años anteriores (CFF art. 23).

## Salida

Tabla por mes con estas columnas:

| Columna | Qué lleva |
|---|---|
| Fecha | día del cobro |
| USD | monto cobrado |
| TC DOF | tipo de cambio fiscal |
| MXN | ingreso fiscal |
| ISR | pago provisional |
| Vence | día 17 recorrido |
| Recargos | techo |
| ¿Plazos? | si entra al pago a plazos |

Además:
- totales por año y la anual;
- supuestos marcados;
- lo no incluido: actualización por INPC (la calcula el portal al generar la línea de captura; suele ser 1-2%), bonos y RSU;
- "valida con un contador o con PRODECON antes de presentar".

## Errores comunes

| Error | Corrección |
|---|---|
| TC impreso por el banco o promedio mensual | DOF del día hábil anterior a cada cobro |
| Tarifa 2026 para meses de 2025 (o al revés) | Tarifa del año de cobro |
| Recargos de 2025 para 2026 | 2025: 1.47%; 2026: 2.07% (`parametros_mx.json`) |
| Ofrecer pago a plazos de todo | Solo lo elegible por 66-A VI a; revisa la columna |
| Exentar el aguinaldo extranjero otra vez | Tope anual ya usado por otro patrón |
| RESICO u honorarios para bajar la tasa del pasado | Es sueldo; RESICO solo con relación realmente independiente, hacia adelante, y con IVA (0% solo si cumple LIVA 29-IV, que excluye VPN y servicios aplicados en México) |
| Calcular con lo pactado | Calcular con lo depositado |
| Ignorar el "neto" del contrato | Preguntar si el patrón asume el ISR; es la palanca más grande |
