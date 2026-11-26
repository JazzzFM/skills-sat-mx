---
name: diagnosticando-asalariado-sat
description: Usar cuando una persona física con sueldos en México pregunta qué declaraciones anuales debió presentar, si le sale saldo a favor o a cargo, cómo pedir su devolución, si sus deducciones personales cuentan, hasta cuándo recupera saldos, qué pasa con un finiquito, liquidación, indemnización o jubilación, o cuando entrega su Constancia de Situación Fiscal, exportaciones del Visor de nómina (Anual.<RFC>.<año>.pdf, DetalleAnual, DetalleMensual), recibos de nómina en XML o facturas de gastos médicos y colegiaturas, y "nunca ha declarado".
---

# Diagnosticando a un asalariado ante el SAT

## Principio

Distingue siempre cuatro cosas: obligación **registrada** (Constancia), **legalmente aplicable** (ley + reglas del ejercicio), **presentada** (acuse) y **posiblemente omitida**. Que no aparezca un acuse entre los archivos no prueba que no exista: se confirma en el portal. **REQUIRED SUB-SKILL:** protegiendo-datos-y-tramites-sat. Comandos desde la raíz del repo; salidas bajo `personal/`.

## Flujo

1. **Leer** (local, enmascarado):
   - `python3 -I herramientas/documentos.py csf personal/sat/<Csf.pdf>` (régimen y estatus).
   - `python3 -I herramientas/documentos.py visor --salida personal/trabajo/visor.csv personal/sat/Anual.*.pdf` (ingresos, exentos, ISR retenido y patrones por año; ignora descargas repetidas).
   - Recibos de nómina en XML: `python3 -I herramientas/cfdi_mx.py nomina personal/nomina/*.xml` (por año y patrón: gravado acumulable, separación, exento, ISR, subsidio y alertas).
2. **Obligación por año** (LISR art. 98, fr. III). Hay que presentar si se cumple cualquiera de estos supuestos:
   - a) tuvo otros ingresos acumulables;
   - b) avisó al patrón que declararía;
   - c) dejó de trabajar antes del 31/12 o tuvo dos o más patrones a la vez;
   - d) cobró de patrones no obligados a retener o del extranjero;
   - e) sus ingresos por sueldos pasaron de $400,000 (la herramienta suma gravado y exento, criterio conservador).
   Además: indemnización, liquidación o jubilación obligan a declarar. La RMF 2026 (regla 3.17.11) relevó el **ejercicio 2025** a quien tuvo un solo patrón, sin ISR a cargo, CFDI de todo el ingreso e intereses nominales ≤ $20,000; no cubre jubilación, indemnización ni los incisos b), c) y d). **Para el ejercicio 2026 el relevo depende de la RMF 2027** (fines de diciembre de 2026): no lo des por hecho.
   **Si pasó de $400,000, el año se clasifica como "obligado (inciso e)"**: la lista del SAT lo marca así, aunque la regla de relevo cite ese inciso, y con más de $400,000 el patrón no hace el cálculo anual (art. 97).
3. **Estimar cada anual con la tarifa del ejercicio** (no la del año en que se presenta):
   `python3 -I herramientas/fiscal_mx.py anual --ejercicio <AAAA> --gravado <gravado acumulable − deducciones> --retenido <ISR>`.
   - **Indemnización, separación o jubilación en una exhibición:** no van en `--gravado`; se gravan por el art. 95 (último sueldo mensual ordinario) y la herramienta no estima ese ISR. Dilo y revisa la precarga: si el patrón no reportó los años de servicio, se elimina y recaptura.
   - **Topes de exentos:** aguinaldo (30 UMA), prima vacacional (15) y PTU (15) son por año; con dos patrones, sumarlos es criterio conservador de la herramienta: confírmalo contra la precarga.
   - **Subsidio con dos patrones:** el SAT lo disminuye del ISR retenido; `nomina` imprime el `--retenido` ajustado.
   - **Ingreso extranjero o sin retención:** sigue con **REQUIRED SUB-SKILL:** calculando-isr-sueldo-extranjero.
4. **Deducciones personales** (si tiene facturas): `python3 -I herramientas/cfdi_mx.py deducciones --rfc <RFC> --ejercicio <AAAA> --ingresos <total con exentos> personal/deducciones/*.xml`.
   - Revisa régimen del receptor (D01 a D10 no admiten 626: quien también es RESICO las pide con 605), pago no en efectivo, fecha del ejercicio, complemento de colegiatura y el tope global (menor de 5 UMA anuales y 15% de los ingresos).
   - Colegiaturas: fuera del tope global, con tope por alumno y nivel que la herramienta aplica: preescolar $14,200, primaria $12,900, secundaria $19,900, profesional técnico $17,100, bachillerato $24,500.
   - No son deducibles: medicinas de farmacia (salvo dentro de la factura del hospital), coaseguro, inscripción, uniformes y seguros de vida.
   - Las que fallen se piden reexpedidas antes de abril. Resta las válidas del gravado.
5. **Saldos a favor** (reglas de la RMF 2026 para el ejercicio 2025; para 2026, confírmalas en la RMF 2027):
   - **Devolución automática** (regla 2.3.2): elegir "Devolución" en una anual presentada a más tardar el 31 de julio, con CLABE activa a su nombre. Hasta $10,000 basta la Contraseña; de $10,001 a $150,000 exige **e.firma** (si no la tiene vigente, que la tramite antes de presentar); arriba de $150,000 no entra. No presentar un FED antes del resultado.
   - **Fuera de eso o años anteriores:** Formato Electrónico de Devoluciones (FED) con e.firma.
   - **Compensación:** contra ISR propio, actualizado (CFF art. 23).
   - **Prescripción:** a los 5 años (CFF arts. 22 y 146); cuenta de forma conservadora desde el vencimiento de cada anual (30 de abril). Prioriza el más antiguo.
6. **Costo de atrasarse:**
   - **Multas:** sin multa si cumple antes de un requerimiento (CFF art. 73).
   - **Recargos:** tasa de cada año según `parametros_mx.json` (2025: 1.47%, fuente secundaria; 2026: 2.07%).
   - **Caducidad:** 10 años de facultades del SAT si no presentó estando obligado (CFF art. 67).
7. **Lista de revisión en el portal** (solo consulta; la hace el usuario):
   - **Buzón Tributario primero:** un requerimiento quita la espontaneidad.
   - Declaraciones presentadas.
   - Opinión del cumplimiento.
   - Visor de nómina de los años faltantes.
   - Visor de deducciones personales.
   - Obligaciones en la Constancia.

## Salida

| Año | Patrones | Gravado | ISR anual | Retenido | Resultado | Obligado (inciso) | Presentada |
|---|---|---|---|---|---|---|---|

Además: supuestos marcados, fuente y calidad de cada tarifa (la herramienta la imprime), fechas límite de prescripción, requisitos de la devolución (Contraseña o e.firma según el monto) y la lista del portal.

## Errores comunes

| Error | Corrección |
|---|---|
| Recargos de 2025 aplicados a meses de 2026 (o al revés) | Tasa de cada año desde `parametros_mx.json` |
| Tarifa del año de presentación | Tarifa del ejercicio declarado |
| Contar dos veces "Anual 2025" y "Anual 2025-1" | La herramienta deduplica por texto |
| "No hay acuse, entonces es omitida" | "Posiblemente omitida; confirmar en el portal" |
| Sumar la indemnización al gravado | Art. 95, aparte |
| Presentar con Contraseña un saldo de más de $10,000 | e.firma para la devolución automática |
| Dar por hecho el relevo o la devolución del ejercicio en curso | Dependen de la RMF del año siguiente |
| Deducir farmacia, coaseguro o inscripción | No son deducibles |
| Cálculos a mano | `fiscal_mx.py` y `cfdi_mx.py`: tarifas y reglas con pruebas |
