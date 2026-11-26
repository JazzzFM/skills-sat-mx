---
name: diagnosticando-asalariado-sat
description: Usar cuando una persona física con sueldos en México pregunta qué declaraciones anuales debió presentar, si le sale saldo a favor o a cargo, si sus deducciones personales cuentan, hasta cuándo recupera saldos, o cuando entrega su Constancia de Situación Fiscal, exportaciones del Visor de nómina (Anual.<RFC>.<año>.pdf, DetalleAnual, DetalleMensual), recibos de nómina en XML o facturas de gastos médicos y colegiaturas, y "nunca ha declarado".
---

# Diagnosticando a un asalariado ante el SAT

## Principio

Distingue siempre cuatro cosas: obligación **registrada** (Constancia), **legalmente aplicable** (ley + reglas del ejercicio), **presentada** (acuse) y **posiblemente omitida**. Que no aparezca un acuse entre los archivos no prueba que no exista: se confirma en el portal. **REQUIRED SUB-SKILL:** protegiendo-datos-y-tramites-sat.

## Flujo

1. **Leer** (local, enmascarado):
   `python3 -I herramientas/documentos.py csf <Csf.pdf>` (régimen y estatus) y
   `python3 -I herramientas/documentos.py visor --salida visor.csv <Anual.*.pdf>` (ingresos, exentos, ISR retenido y patrones por año; ignora descargas repetidas).
   Si tiene los recibos de nómina en XML: `python3 -I herramientas/cfdi_mx.py nomina <recibos*.xml>` (por año y patrón: gravado, exento, ISR, subsidio, topes de aguinaldo, prima y PTU entre patrones, y alertas de indemnización).
2. **Obligación por año** (LISR art. 98, fr. III). Hay que presentar si se cumple cualquiera de estos supuestos:
   - a) tuvo otros ingresos acumulables;
   - b) avisó al patrón que declararía;
   - c) dejó de trabajar antes del 31/12 o tuvo dos o más patrones a la vez;
   - d) cobró de patrones no obligados a retener o del extranjero;
   - e) sus salarios pasaron de $400,000.
   Cada RMF trae una regla de relevo para el ejercicio anterior (la RMF 2026 la llama 3.17.11: un solo patrón, sin ISR a cargo, CFDI de todo el ingreso e intereses nominales ≤ $20,000). Ese relevo no cubre jubilación, indemnización ni los incisos b), c) y d).
   **Si los salarios pasaron de $400,000, el año se clasifica como "obligado (inciso e)"**: la lista del SAT lo marca así, aunque la regla de relevo cite ese inciso, y con más de $400,000 el patrón no hace el cálculo anual (art. 97). La regla de relevo solo se menciona como nota.
3. **Estimar cada anual con la tarifa del ejercicio** (no la del año en que se presenta):
   `python3 -I herramientas/fiscal_mx.py anual --ejercicio <AAAA> --gravado <total-exento> --retenido <ISR>`.
   - **Topes de exentos:** aguinaldo (30 UMA), prima vacacional (15) y PTU (15) se topan por año entre todos los patrones. Si dos patrones exentaron, el exceso grava en la anual (ver DetalleMensual).
   - **Ingreso extranjero o sin retención:** sigue con **REQUIRED SUB-SKILL:** calculando-isr-sueldo-extranjero.
4. **Deducciones personales** (si tiene facturas): `python3 -I herramientas/cfdi_mx.py deducciones --rfc <RFC> --ejercicio <AAAA> --ingresos <total con exentos> <facturas*.xml>`.
   Revisa régimen del receptor (D01 a D10 no admiten 626: quien también es RESICO las pide con 605), pago no en efectivo, fecha del ejercicio, complemento de colegiatura y el tope global (menor de 5 UMA anuales y 15% de los ingresos). Las que fallen se piden reexpedidas antes de abril. Resta las válidas del gravado antes de `fiscal_mx.py anual`.
5. **Saldos a favor:**
   - **Año inmediato anterior:** devolución automática solo hasta el 31 de julio.
   - **Años anteriores:** Formato Electrónico de Devoluciones (FED) con e.firma.
   - **Compensación:** contra ISR propio, actualizado (CFF art. 23).
   - **Prescripción:** a los 5 años (CFF arts. 22 y 146); cuenta de forma conservadora desde el vencimiento de cada anual (30 de abril). Prioriza el más antiguo.
6. **Costo de atrasarse:**
   - **Multas:** sin multa si cumple antes de un requerimiento (CFF art. 73).
   - **Recargos:** tasa de cada año según `parametros_mx.json` (2025: 1.47% secundaria; 2026: 2.07%).
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

Además: supuestos marcados, fuente y calidad de cada tarifa (la herramienta la imprime), fechas límite de prescripción y la lista del portal.

## Errores comunes

| Error | Corrección |
|---|---|
| Recargos de 2025 aplicados a meses de 2026 (o al revés) | Tasa de cada año desde `parametros_mx.json` |
| Tarifa del año de presentación | Tarifa del ejercicio declarado |
| Contar dos veces "Anual 2025" y "Anual 2025-1" | La herramienta deduplica por texto |
| "No hay acuse, entonces es omitida" | "Posiblemente omitida; confirmar en el portal" |
| Prometer devolución automática de años viejos | FED con e.firma |
| Sumar exentos de dos patrones sin tope anual | Topar aguinaldo, prima y PTU por año |
| Cálculos a mano | `fiscal_mx.py`: tarifas validadas por pruebas |
