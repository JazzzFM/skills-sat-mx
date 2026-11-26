# skills-sat-mx

Skills para agentes de código (Claude Code y compatibles) y herramientas en Python para la contabilidad personal ante el SAT: **asalariados**, **sueldo de patrón extranjero**, **RESICO persona física** y **timbrado de facturas de tickets** en portales de autofactura. El agente lee tus documentos en local, calcula, cuadra contra lo que el SAT precarga y te guía; las declaraciones, pagos, firmas y tus propias facturas los haces tú en el portal.

> No es asesoría fiscal. Las cifras corresponden al ejercicio 2026 con corte de la investigación al 26/10/2026 (ver `investigacion/`). Valida con un contador o con PRODECON antes de presentar.

## Skills (`.claude/skills/`)

| Skill | Para qué |
|---|---|
| `protegiendo-datos-y-tramites-sat` | Reglas de credenciales, trámites y publicación de datos. Las demás la requieren. |
| `diagnosticando-asalariado-sat` | Qué anuales debías presentar, saldo a favor o a cargo, deducciones personales, prescripción y revisión del portal. |
| `calculando-isr-sueldo-extranjero` | Pagos provisionales y anual de un sueldo sin retención, tipo de cambio fiscal, recargos y plan de pago. |
| `ordenando-estados-de-cuenta` | Ordenar y renombrar estados de cuenta sin borrar, con manifiesto, y extraer depósitos del extranjero. |
| `declarando-resico-pf` | ISR e IVA mensual desde tus XML, cuadre con la precarga, PUE/PPD, complemento, factura global, saldos a favor, omisiones y la anual. |
| `timbrando-facturas-de-tickets` | Facturar tickets en portales de autofactura con el navegador, elegir régimen y uso de CFDI, verificar el XML y archivar por día. |

Cada skill se probó con escenarios simulados con y sin la skill, con datos ficticios.

## Instalación

Requisitos: Python 3.9 o más reciente (solo biblioteca estándar) y `pdftotext` (`sudo apt install poppler-utils` o `brew install poppler`). Para timbrar en portales, la extensión Claude in Chrome u otra herramienta de navegador del agente.

```bash
git clone <url-de-este-repo> skills-sat-mx
cd skills-sat-mx
python3 -m pytest -q tests/     # opcional: requiere pytest
claude                          # las skills de .claude/skills/ se cargan solas en este directorio
```

Trabaja **dentro de esta carpeta**: los comandos de las skills usan rutas relativas a la raíz (`herramientas/…`) y tus documentos van en `personal/`, que git ignora. Otros agentes que leen el formato de skills (`SKILL.md` con frontmatter) pueden usar las mismas carpetas, por ejemplo con un enlace simbólico a su directorio de skills.

## Configuración para timbrar tickets

```bash
mkdir -p personal && cp ejemplos/autofactura.ejemplo.json personal/autofactura.json
```

Llénalo con los datos de tu Constancia de Situación Fiscal (RFC, nombre exacto, CP), tus perfiles de régimen y uso de CFDI, y la ventana de autofactura de cada comercio que uses. La skill explica qué perfil corresponde a cada tipo de gasto.

## Ejemplos de uso

- "Tengo estos XML de octubre en `personal/cfdi/2026-10/`, soy RESICO: ¿cuánto pago de ISR e IVA y qué reviso en la precarga?"
- "Aquí está mi Constancia y las exportaciones del Visor de nómina; nunca he declarado. ¿Qué debo?"
- "Mi empresa en Estados Unidos me paga en dólares sin retenerme. ¿Cuánto debo de este año?"
- "Subí 10 fotos de tickets a `personal/entrada/`: regístralos y factura los que vencen primero."

## Herramientas (`herramientas/`)

```bash
python3 -I herramientas/fiscal_mx.py --help            # provisionales, anual, plazos, tarifa
python3 -I herramientas/cfdi_mx.py --help              # ver, verificar, resico, nomina, deducciones
python3 -I herramientas/autofactura.py --help          # registrar, archivar, vigencias
python3 -I herramientas/tipo_cambio_banxico.py --help  # tipo de cambio fiscal (DOF del día hábil anterior)
python3 -I herramientas/documentos.py --help           # planear/ordenar, depositos, visor, csf
```

Todo corre en local. Solo `tipo_cambio_banxico.py` consulta un servicio público (Banxico) y únicamente envía fechas.

## Mantenimiento

Los parámetros por ejercicio (tarifas, UMA, recargos, días inhábiles) viven en `herramientas/parametros_mx.json`, cada uno con fuente y calidad (primaria o secundaria). Varias reglas que usan las skills son facilidades de la Resolución Miscelánea Fiscal que se renuevan cada año. Revisa:

- **Diciembre:** RMF y Anexo 8 del año siguiente, Ley de Ingresos (recargos, retenciones), relevo de la anual RESICO (regla 3.13.7) y de asalariados (3.17.11).
- **Enero:** UMA del INEGI (vigente desde el 1 de febrero).
- **Marzo y abril:** guías y preguntas frecuentes de la anual.

Agrega la tarifa nueva al JSON con su fuente y corre las pruebas.

## Licencia

MIT. Ver `LICENSE`.
