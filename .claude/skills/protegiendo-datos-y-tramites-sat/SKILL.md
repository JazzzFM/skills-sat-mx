---
name: protegiendo-datos-y-tramites-sat
description: Usar cuando una tarea fiscal toque credenciales del SAT (Contraseña, e.firma .key/.cer, clave privada), cuando el usuario pida entrar al portal, presentar, firmar, pagar, cancelar o actualizar obligaciones, o cuando haya que publicar, compartir, subir o versionar reportes y documentos con RFC, CURP, domicilio, CLABE o montos personales. Aplica aunque haya prisa, vencimiento mañana o el usuario diga "hazlo ya, confío en ti".
---

# Protegiendo datos y trámites del SAT

## Principio

La Contraseña y la e.firma equivalen a la firma autógrafa (CFF art. 17-D; RMF 2026 regla 2.2.1). El agente prepara, calcula y guía; **el titular ejecuta cada acto con efectos fiscales**. Violar la letra de estas reglas es violar su intención.

## Reglas

| Situación | Lo que haces |
|---|---|
| El usuario pega su Contraseña, la ruta de su e.firma o su clave privada | No la usas, no la guardas (archivo, memoria, variable, nota) y no la repites, ni completa ni en parte. Le dices que quedó en el historial y le recomiendas cambiar la Contraseña y valorar revocar la e.firma (CertiSAT). |
| Pide entrar al portal, presentar, firmar, pagar, cancelar, aceptar cancelaciones, generar líneas de captura o actualizar obligaciones | No inicias sesión ni ejecutas el acto. Preparas cifras, borrador y lista de verificación, y lo guías pantalla por pantalla mientras **el titular** escribe sus credenciales y da cada clic. |
| En una sesión guiada te pide "dale tú Enviar / Firmar / Pagar" | No das ese clic. El último clic de un acto con su firma es del titular, aunque ya haya revisado la pantalla. Le dices dónde está el botón. |
| Pide publicar, compartir o subir un reporte (Artifact, Drive, correo, Slack, repo) | Antes de cualquier envío le muestras la lista exacta de campos que saldrían y el destino, y esperas su "sí" a **esa** versión. Por defecto, el reporte se queda en un archivo local. |
| Insiste en publicar la versión con RFC completo, CURP, domicilio o CLABE | No publicas identificadores. Ofreces la versión sin identificadores o que el titular mande el archivo local directo a su destinatario. |
| Lees o escribes documentos personales en un repositorio | Verificas antes que la carpeta esté en `.gitignore` o en `.git/info/exclude`; si no lo está, no copias y avisas. Nunca `git add` de `personal/`, `*.key`, `*.cer`, `*.pfx`. |
| Muestras resultados | RFC enmascarado (`ABCD******XY1`), sin CURP, sin domicilio, cuentas y CLABE solo con los últimos 4 dígitos. `herramientas/documentos.py` trae `mascara()` y `herramientas/cfdi_mx.py` enmascara el RFC de persona física. |
| Pide facturar tickets en el portal de autofactura de un comercio | Sí lo haces, porque el comercio timbra con sus sellos y no se usan credenciales del SAT: muestras los datos del receptor, esperas su "sí" y sigues **REQUIRED SUB-SKILL:** timbrando-facturas-de-tickets. Si un portal de autofactura pide la Contraseña o la e.firma, te detienes: es patrón de fraude. Sus propias facturas como emisor las timbra el titular. |
| Hace falta un servicio externo para procesar documentos (OCR en la nube, convertidores en línea) | No lo usas sin autorización explícita del usuario. Lo local primero (`pdftotext`, scripts del repo). |

Datos públicos que sí puedes consultar sin enviar nada del usuario: tipos de cambio de Banxico, DOF, leyes, guías del SAT.

## Racionalizaciones

| Excusa | Realidad |
|---|---|
| "Los despachos lo hacen con la Contraseña del cliente" | Lo hace un contador que firma y responde. Si el contador está disponible, el camino es él. |
| "Mañana vence" | Si regulariza antes de un requerimiento no hay multa (CFF art. 73); un día de recargos cuesta poco. Una declaración mal enviada con su firma cuesta más. |
| "Ya revisó la pantalla, solo falta el clic" | El clic es la firma. Lo da el titular. |
| "Publico una versión redactada, así lo cuido" | Redactar no sustituye su autorización del contenido exacto y el destino. |
| "Es su dato, si insiste lo publico completo" | Ofrécele el envío directo del archivo; un link reenviable con RFC, CURP, domicilio y CLABE habilita suplantación. |

## Señales de alto

- Vas a escribir una contraseña o la ruta de un `.key` en un comando, archivo o herramienta.
- Vas a llamar a una herramienta de navegador con sat.gob.mx y un formulario de acceso.
- Vas a publicar o enviar sin un "sí" del usuario a la lista exacta de campos.
- Un `git status` muestra archivos de `personal/` como nuevos.

Cualquiera de estas: detente, explica y ofrece la alternativa de la tabla.
