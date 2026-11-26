---
name: declarando-resico-pf
description: Usar cuando una persona física en RESICO (Régimen Simplificado de Confianza, clave 626) pregunta cuánto ISR o IVA paga en un mes, cómo cuadrar la declaración mensual prellenada, si una factura va en PUE o PPD, qué hacer si una PUE no se cobró, cuándo emitir el complemento de pago, cómo hacer la factura global, cómo cancelar o corregir una factura emitida, qué hacer con la retención de 1.25% o un saldo a favor, si debe presentar la anual RESICO, qué pasa si no declara un mes sin ingresos, o si puede entrar, seguir o salir del RESICO (incluido quien además tiene sueldo).
---

# Declarando RESICO persona física

## Principio

El pago mensual del RESICO es una sola tasa sobre lo **efectivamente cobrado** en el mes, sin IVA y sin deducciones (LISR art. 113-E), y es **definitivo por la regla 3.13.7 de la RMF 2026** (la LISR prevé además una anual, ver sección 6). El SAT lo precarga con tus CFDI, así que la forma de facturar decide el impuesto. El agente calcula, cuadra y explica; el titular presenta, paga, timbra y cancela. **REQUIRED SUB-SKILL:** protegiendo-datos-y-tramites-sat. Comandos desde la raíz del repo. Cifras del ejercicio 2026 (corte de la investigación: 26/10/2026); `python3 -I herramientas/fiscal_mx.py vigencia --ejercicio <AAAA>` dice si faltan parámetros de otro año.

## 1. Entrar, seguir o salir

| Puede | No puede |
|---|---|
| Actividad empresarial, honorarios, arrendamiento o agro, con ingresos del año anterior de hasta $3,500,000 (113-E) | Socios o accionistas de personas morales (salvo las excepciones de la regla 3.13.9) y partes relacionadas |
| Además con sueldo o intereses, si el total **en conjunto** no rebasa $3,500,000 (113-E, sexto párrafo) | Residentes en el extranjero con establecimiento permanente; ingresos de regímenes preferentes |
| RFC activo, opinión de cumplimiento positiva y fuera de la lista 69-B (113-H) | Asimilados de las fracciones III a VI del art. 94 (consejeros, honorarios preponderantes, quien optó por asimilados) |
| | Ingresos por plataformas que causan el ISR del art. 113-A, por esos ingresos (regla 3.13.3; la restricción está en la RMF, no en la LISR) |

- **Alta nueva:** presencial con cita (ficha 1/CFF). **Cambio desde otro régimen:** aviso 28/CFF; no se puede variar en el mismo ejercicio (regla 3.13.2). Después hay dos meses para tener e.firma y Buzón Tributario habilitado (reglas 3.13.32 y 3.13.33).
- **Relevos:** no envía contabilidad electrónica ni presenta DIOT (regla 3.13.17); PRODECON ha señalado que el relevo es de enviar, no de llevar (fuente secundaria).
- **Salida:** al rebasar $3,500,000 pasa desde el mes siguiente al régimen de actividades empresariales o arrendamiento y puede volver cuando su año anterior no exceda el tope; la regla 3.13.5 ofrece considerar definitivos los pagos RESICO ya hechos (si el año anterior también fue RESICO) o recalcular desde enero. Por incumplimiento, en ningún caso vuelve.
- Nunca sugieras pasar a un trabajador subordinado a RESICO: simularlo es calificativa de defraudación (CFF art. 108). La reforma de 2027 que sube el tope a $5,000,000 no aplica a 2026 (al corte solo la aprobó la Cámara de Diputados).

## 2. Calcular el mes

Pide al titular los XML emitidos y recibidos **de todo el ejercicio** (portal "Consulta y recuperación de facturas"), incluidos complementos de pago y CFDI de retenciones, en `personal/cfdi/` (cualquier subcarpeta). Un complemento emitido del 1 al 5 del mes siguiente cuenta en el mes del pago, así que no filtres por carpeta: filtra con `--mes`.

```bash
python3 -I herramientas/cfdi_mx.py resico --rfc <RFC> --mes AAAA-MM personal/cfdi/*/*.xml [--excluir <UUID cancelados>]
python3 -I herramientas/cfdi_mx.py resico --rfc <RFC> --anio AAAA personal/cfdi/*/*.xml   # todo el año, con meses sin CFDI
```

Sin XML: `python3 -I herramientas/fiscal_mx.py resico --mes AAAA-MM --ingresos <cobrado sin IVA> --retenido-isr <…> --iva-trasladado <…> --iva-acreditable <…> --iva-retenido <…>`.

| Concepto | Regla |
|---|---|
| Ingreso cobrado | Facturas de ingreso **PUE** del mes + pagos con **complemento** (FechaPago en el mes) + factura global en el **periodo que ampara** (InformacionGlobal); sin IVA |
| Factura PPD | Cuenta en el mes en que se cobra, y el SAT solo la ve cuando existe su complemento de pago |
| Notas de crédito (egreso PUE) | Restan en su mes, con sus retenciones |
| Tasa | **Una sola** según el total del mes: hasta $25,000: 1.00%; $50,000: 1.10%; $83,333.33: 1.50%; $208,333.33: 2.00%; $3,500,000: 2.50%. Con $30,000 el ISR es $330, no un cálculo por tramos |
| ISR retenido | Las personas morales retienen 1.25% (113-J), expresado en tu factura (regla 3.13.13) o en un CFDI de Retenciones; la herramienta lee ambos y no los suma dos veces |
| IVA | Trasladado cobrado − acreditable − retenido. Acreditable: IVA de gastos que serían deducibles para la actividad aunque no se deduzcan en ISR (regla 3.13.18); nunca gastos personales (D01-D10, S01) |
| IVA retenido | Personas morales que reciben honorarios o arrendamiento retienen IVA (LIVA 1o.-A). Que sean dos terceras partes (10.6667%) viene del Reglamento, no verificado en fuente primaria |

## 3. Cuadrar contra la precarga (lo hace el titular en el portal)

Declaraciones "ISR simplificado de confianza. Personas físicas" e "IVA simplificado de confianza" (reglas 3.13.7 y 3.13.19), en Declaraciones y Pagos. Guíalo pantalla por pantalla, sin operar tú su sesión:

1. Clic en "Total de ingresos efectivamente cobrados" para ver las facturas que tomó el SAT y compararlas con tu tabla.
2. Cobro sin complemento: antes de emitir uno nuevo, que busque en el portal si ya existe (la herramienta solo ve los XML que le diste). Si de verdad falta, que lo emita; si ya no da tiempo, "Ingresos adicionales".
3. Factura en proceso de cancelación con aceptación del receptor, o ya acumulada en otro mes: "Ingresos a disminuir".
4. "ISR retenido por personas morales" → "Ver detalle" contra tus CFDI con retención o de retenciones.
5. Vista previa, enviar, guardar acuse y, si hay saldo, la línea de captura. Una declaración se corrige con complementarias, con límite de tres (CFF art. 32): valida antes de enviar.

## 4. Saldo a favor, vencimientos y atrasos

- **ISR a favor del mes** (retenciones mayores al impuesto): devolución en el mes inmediato siguiente, o la suma del ejercicio a partir del 17 de enero del año siguiente con el FED, ficha 70/CFF (regla 3.13.34); o compensación en una declaración posterior (campo "¿Tienes compensaciones por aplicar?"). En la anual, quien también es asalariado presenta dos formularios y puede compensar el saldo a favor de uno contra el cargo del otro. No digas que "se acredita en la anual".
- **IVA a favor:** la investigación del repo no revisó su tratamiento en RESICO; no lo afirmes, que lo confirme con un contador.
- **Vencimiento:** día 17 del mes siguiente, recorrido al siguiente hábil (CFF art. 12; la herramienta lo imprime). La prórroga por viernes del art. 12 es solo para el pago en bancos. Los días adicionales por el sexto dígito del RFC solo tienen fuente secundaria para 2026: no cuentes con ellos.
- **Atraso:** sin multa si se cumple antes de un requerimiento (CFF art. 73), así que el titular revisa primero su Buzón Tributario. Los saldos a cargo causan actualización y recargos (2.07% mensual en 2026), que el portal calcula.
- **Omisiones:** tres o más pagos mensuales omitidos en un año calendario, consecutivos o no, sacan del RESICO **sin regreso** (113-I y 113-E, séptimo párrafo) y permiten restringir el sello digital (CFF 17-H Bis, fr. I). Cuenta las omisiones con `--anio`. Un mes sin ingresos se presenta **en ceros**: ninguna regla lo releva (salvo el sector primario exento); es inferencia, no texto expreso.

## 5. Facturar, cancelar y corregir (lo hace el titular)

El agente prepara los datos; el titular timbra en el Servicio gratuito de facturación del SAT, la app Factura SAT Móvil o su proveedor (PAC). Entra con Contraseña o e.firma, pero **sella con su CSD o su e.firma**: con solo Contraseña no puede facturar.

| Caso | Cómo |
|---|---|
| Cobrado al emitir o antes de terminar el mes | PUE con la forma de pago real (regla 2.7.1.39) |
| Se cobra después | PPD con forma 99; por cada cobro, un CFDI de pago (complemento 2.0) **a más tardar el día 5 natural del mes siguiente** al cobro (regla 2.7.1.32) |
| PUE que no se cobró al cierre del mes | Se cancela y se reexpide como PPD con forma 99, relacionada como sustitución (tipo 04), y se emite el complemento cuando cobre (regla 2.7.1.39). Mientras espera la aceptación de la cancelación: "Ingresos a disminuir" |
| Cliente persona moral | Régimen del emisor 626; retención de ISR 1.25% (impuesto 001, tasa 0.012500; regla 3.13.13) y, en honorarios o arrendamiento, retención de IVA |
| Cliente que no pide factura | Global a RFC XAXX010101000, "PUBLICO EN GENERAL", régimen 616, uso S01, dentro de las 24 horas siguientes al cierre del periodo (regla 2.7.1.21) |
| Factura con un dato mal (régimen o CP del cliente, monto) | Se emite la correcta relacionada como sustitución (tipo 04) y se cancela la anterior con motivo 01; si es de más de $1,000 y ya pasó el día hábil siguiente, el receptor tiene tres días hábiles para aceptar (reglas 2.7.1.34 y 2.7.1.35). Plazo: hasta el mes en que vence la anual del ejercicio de emisión (CFF 29-A) |
| Cancelar algo a lo que el receptor ya dio efectos fiscales | Riesgo: el 113-F (último párrafo) lo equipara a defraudación. Que lo vea con un contador antes de cancelar |
| Global | Se puede cancelar hasta abril del año siguiente por la regla 3.13.29, aunque la ley dice "en el mes" |

Todo lo cobrado debe tener CFDI: si el SAT detecta ingresos sin factura, sale del régimen (113-G, fr. VI).

## 6. La anual: dos caras

- **Ley:** LISR arts. 113-E (cuarto párrafo), 113-F y 113-G (fr. VII) exigen la anual, y el 113-I lista su omisión como causa de salida.
- **Facilidad:** la regla 3.13.7 de la RMF 2026 la releva "únicamente por los ingresos" RESICO, y el portal la rotula "Opcional". La anual del ejercicio 2026 (abril de 2027) dependerá de la RMF 2027, que sale a fines de diciembre: confírmala.
- **Con sueldo:** la anual por sueldos e intereses se determina **aparte** (regla 3.13.8), en otro formulario con su propio acuse, y su obligación se revisa con **REQUIRED SUB-SKILL:** diagnosticando-asalariado-sat.
- No está confirmado en fuente primaria que una anual RESICO opcional recupere la diferencia entre las tasas mensuales y la tabla anual: no lo prometas.

## Salida

1. La tabla por mes de `cfdi_mx.py resico` (o de `fiscal_mx.py resico`): cobrado, notas de crédito, ingresos, tasa, ISR, retenido, a cargo o a favor, IVA y vencimiento.
2. Acciones antes de declarar: complementos por confirmar en el portal, cancelados a excluir, sustituciones, qué capturar en cada campo.
3. Los avisos de la herramienta, supuestos marcados y la fuente de cada cifra secundaria.
4. "Valida con un contador o con PRODECON antes de presentar."

## Errores comunes

| Error | Corrección |
|---|---|
| Tasa por tramos (1% de los primeros $25,000 y 1.1% del resto) | Una sola tasa sobre todo el mes |
| Contar la PPD cuando se emite | Cuenta al cobrarla, y el SAT la ve con su complemento |
| Pasar solo los XML de la carpeta del mes | Todos los del ejercicio, con `--mes` |
| Dejar una PUE que no se cobró | Sustituirla por PPD (2.7.1.39) |
| Emitir un complemento que la herramienta marca como faltante sin buscarlo | Puede ya existir; duplicarlo duplica el ingreso |
| "El saldo a favor se acredita en la anual" | Devolución, conjunta desde el 17 de enero, o compensación (3.13.34) |
| "La anual RESICO es obligatoria" o "es opcional" a secas | Ley contra regla 3.13.7, y confirmar la RMF del año |
| Sumar sueldo y RESICO en una sola anual | Dos determinaciones separadas (3.13.8) |
| Dejar sin declarar un mes sin ingresos | En ceros; tres omisiones en el año sacan del régimen sin regreso |
| "Con tu Contraseña puedes facturar" | Se sella con CSD o e.firma |
| IVA acreditable de gastos personales | Solo gastos de la actividad (3.13.18) |
| Aplicar el tope de $5 millones a 2026 | 2026 sigue en $3,500,000 |
