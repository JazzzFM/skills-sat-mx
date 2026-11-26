# skills-sat-mx

[![pruebas](https://github.com/JazzzFM/skills-sat-mx/actions/workflows/pruebas.yml/badge.svg)](https://github.com/JazzzFM/skills-sat-mx/actions/workflows/pruebas.yml)

Skills para agentes de código (Claude Code y compatibles) y herramientas en Python para la contabilidad personal ante el Servicio de Administración Tributaria (SAT): **asalariados**, **sueldo de patrón extranjero**, **Régimen Simplificado de Confianza (RESICO) de persona física** y **timbrado de facturas de tickets** en portales de autofactura. El agente lee tus documentos, calcula, cuadra contra lo que el SAT precarga y te guía. Las declaraciones, pagos, firmas, cancelaciones y tus propias facturas los haces tú en el portal.

> No es asesoría fiscal. Las cifras corresponden al ejercicio 2026, con la investigación cortada al 26 de octubre de 2026 (ver `investigacion/`). Valida con un contador o con la Procuraduría de la Defensa del Contribuyente (PRODECON) antes de presentar.

## Siglas

- Registro Federal de Contribuyentes (RFC) y Clave Única de Registro de Población (CURP).
- Comprobante Fiscal Digital por Internet (CFDI): la factura electrónica, un archivo en lenguaje de marcado extensible (XML).
- Pago en una sola exhibición (PUE) y pago en parcialidades o diferido (PPD).
- Impuesto sobre la renta (ISR) e impuesto al valor agregado (IVA).
- Ley del ISR (LISR), Ley del IVA (LIVA), Código Fiscal de la Federación (CFF) y Ley de Ingresos de la Federación (LIF).
- Resolución Miscelánea Fiscal (RMF): las reglas anuales del SAT.
- Unidad de Medida y Actualización (UMA): la publica el INEGI cada enero.
- Certificado de sello digital (CSD), con el que se timbran facturas, y proveedor autorizado de certificación (PAC).
- Formato Electrónico de Devoluciones (FED) y Clave Bancaria Estandarizada (CLABE) de 18 dígitos.
- Diario Oficial de la Federación (DOF) e Índice Nacional de Precios al Consumidor (INPC), que actualiza los adeudos.

## Skills (`.claude/skills/`)

| Skill | Para qué |
|---|---|
| `protegiendo-datos-y-tramites-sat` | Reglas de credenciales, sesiones del SAT, avisos falsos y publicación de datos. Las demás la requieren. |
| `diagnosticando-asalariado-sat` | Qué anuales debías presentar, saldo a favor o a cargo, devolución, indemnización, deducciones personales y prescripción. |
| `calculando-isr-sueldo-extranjero` | Pagos provisionales y anual de un sueldo sin retención, tipo de cambio fiscal, recargos y plan de pago. |
| `ordenando-estados-de-cuenta` | Ordenar y renombrar estados de cuenta sin borrar, con manifiesto, y extraer depósitos del extranjero. |
| `declarando-resico-pf` | ISR e IVA mensual desde tus XML, cuadre con la precarga, PUE o PPD, complemento, global, cancelación, saldos a favor, omisiones y la anual. |
| `timbrando-facturas-de-tickets` | Facturar tickets en portales de autofactura con el navegador, elegir régimen y uso de CFDI, verificar el XML y archivar por día. |

Cada skill se probó con escenarios simulados con y sin la skill, con datos ficticios.

## Primer uso

1. **Requisitos:** Python 3.9 o más reciente (solo biblioteca estándar) y `pdftotext` (`sudo apt install poppler-utils` o `brew install poppler`). Para timbrar en portales, la extensión Claude in Chrome u otra herramienta de navegador del agente.
2. **Clona y prepara:**
   ```bash
   git clone https://github.com/JazzzFM/skills-sat-mx.git
   cd skills-sat-mx
   git config core.hooksPath .githooks        # bloquea commits con datos personales
   python3 -m venv .venv && .venv/bin/pip install "pytest<9" && .venv/bin/python -m pytest -q tests/
   claude
   ```
   Las skills de `.claude/skills/` se cargan solas al abrir Claude Code en esta carpeta o en una subcarpeta. La primera vez, Claude Code pide confiar en el proyecto: eso activa los permisos y el hook de `.claude/settings.json`.
3. **Crea tu carpeta personal** (git la ignora) y pon cada documento en su lugar:
   ```text
   personal/
     sat/             Constancia de Situación Fiscal y exportaciones anuales del Visor de nómina
     nomina/          recibos de nómina en XML
     deducciones/     facturas de gastos médicos, colegiaturas y demás deducciones personales
     cfdi/AAAA-MM/    XML emitidos, recibidos, complementos de pago y retenciones (RESICO)
     estados-cuenta/  estados de cuenta ordenados
     trabajo/         salidas de las herramientas (CSV)
     entrada/         tickets por registrar
     descargas/       XML y PDF recién bajados de portales
     facturas/        tickets y CFDI archivados por día de consumo
     autofactura.json configuración para timbrar tickets
   ```
4. **Baja tus documentos del SAT** (entras tú, con tu Contraseña o e.firma):
   - Constancia de Situación Fiscal: portal del SAT, SAT Móvil o SAT ID.
   - Visor de nómina: minisitio de la Declaración Anual, sección Visores.
   - XML de facturas: Factura electrónica, "Consultar facturas emitidas" y "recibidas" (500 por consulta, hasta 2,000 XML por día).
5. **Para timbrar tickets:** `cp ejemplos/autofactura.ejemplo.json personal/autofactura.json` y llénalo con los datos de tu Constancia (RFC, nombre exacto, código postal), tus perfiles de régimen y uso de CFDI y la ventana de autofactura de cada comercio.

Otros agentes que leen el formato de skills (un `SKILL.md` con encabezado de metadatos) pueden usar las mismas carpetas, por ejemplo con un enlace simbólico a su directorio de skills.

## Ejemplos de uso

- "Tengo los XML de 2026 en `personal/cfdi/`, soy RESICO: ¿cuánto pago de ISR e IVA en octubre y qué reviso en la precarga?"
- "Aquí está mi Constancia y las exportaciones del Visor de nómina; nunca he declarado. ¿Qué debo?"
- "Mi empresa en Estados Unidos me paga en dólares sin retenerme. ¿Cuánto debo de este año?"
- "Subí 10 fotos de tickets a `personal/entrada/`: regístralos y factura los que vencen primero."

## Herramientas (`herramientas/`)

```bash
python3 -I herramientas/fiscal_mx.py --help            # provisionales, anual, resico, plazos, tarifa, vigencia
python3 -I herramientas/cfdi_mx.py --help              # ver, verificar, resico, nomina, deducciones
python3 -I herramientas/autofactura.py --help          # registrar, archivar, vigencias
python3 -I herramientas/tipo_cambio_banxico.py --help  # tipo de cambio fiscal (DOF del día hábil anterior)
python3 -I herramientas/documentos.py --help           # planear/ordenar, depositos, visor, csf
python3 -I herramientas/revisar_publicacion.py --help  # que nada personal se publique
```

Leen CFDI 4.0 y 3.3, Pagos 2.0, Nómina 1.2, colegiaturas y CFDI de Retenciones 2.0. Solo `tipo_cambio_banxico.py` consulta un servicio público (Banxico) y únicamente envía fechas.

## Privacidad y controles

- **Lo que lee el agente sale de tu equipo.** Las herramientas corren en local, pero el texto que el agente lee (la salida de `pdftotext`, los XML, tus respuestas, las páginas del portal) viaja al proveedor del modelo como parte de la conversación, y Claude Code guarda las transcripciones en `~/.claude/projects/`. Para guardarlas menos tiempo, ajusta `cleanupPeriodDays` en tu configuración de Claude Code. Las salidas de las herramientas enmascaran el RFC de persona física, la CURP y las cuentas; el timbrado sí necesita tu RFC completo.
- **Qué impide publicar datos:** `.gitignore` excluye `personal/`, llaves (`*.key`, `*.cer`, `*.pfx`, `*.p12`) y CSV en la raíz; `herramientas/revisar_publicacion.py` revisa rutas, RFC, CURP y CLABE antes de cada commit (hook de Claude Code, pre-commit de git y CI); las herramientas rechazan escribir salidas dentro del repo fuera de `personal/`.
- **Límites:** las reglas de `.claude/settings.json` que niegan leer llaves no son una barrera de seguridad (un script puede abrir el archivo por su cuenta). Lo que protege tu Contraseña y tu e.firma es no dárselas nunca al agente; la skill de protección lo pide así.

## Mantenimiento

Los parámetros por ejercicio (tarifas, tabla RESICO, UMA, recargos, topes de colegiatura) viven en `herramientas/parametros_mx.json`, cada uno con fuente y calidad (primaria o secundaria). `python3 -I herramientas/fiscal_mx.py vigencia --ejercicio 2027` lista lo que falta de un año y sale con error si falta algo. Varias reglas que usan las skills son facilidades de la RMF que se renuevan cada año. Revisa:

- **Diciembre:** RMF y Anexo 8 del año siguiente, Ley de Ingresos (recargos, retenciones), relevo de la anual RESICO (regla 3.13.7) y de asalariados (3.17.11), devolución automática (2.3.2).
- **Enero:** UMA del INEGI (vigente desde el 1 de febrero).
- **Marzo y abril:** guías y preguntas frecuentes de la anual.

Agrega los valores nuevos al JSON con su fuente y corre las pruebas. La integración continua las corre en Linux con Python 3.9 y 3.13 y en macOS con 3.13.

## Licencia

MIT. Ver `LICENSE`.
