# Plataformas de autofactura: comportamiento observado

Muchos comercios usan la misma plataforma con otro nombre o subdominio. Identifica la plataforma por la URL a la que redirige el portal del ticket. Lo de abajo se observó en 2026 con las herramientas de navegador de Claude (Claude in Chrome); los portales cambian, así que tómalo como punto de partida y anota lo nuevo.

## Problemas generales del navegador

- La captura de pantalla falla a ratos ("Cannot attach", timeout). Usa `read_page`, `find` o `get_page_text` para leer la página.
- `form_input` sobre el ref del campo es más confiable que teclear por coordenadas, que cae en el campo equivocado.
- Las ventanas emergentes (`window.open`) a veces no aparecen: lee la URL del botón y navega directo.
- `file_upload` solo acepta archivos del directorio de trabajo de la sesión. Si el usuario aceptó subir un documento, usa la copia que está en `personal/` (dentro del repo y fuera de git), nunca una copia en otra carpeta.
- Chrome bloquea descargas disparadas con `.click()` programático. `window.location.href = <href>` desde `javascript_tool` sí descarga, a la carpeta de descargas del usuario.
- Los anuncios a pantalla completa que tapan un formulario suelen quitarse recargando la URL del formulario.

## Soft Restaurant (`mefacturo.mx/<sucursal>` redirige a `admin.softrestaurant.com/<sucursal>`)

Usado por restaurantes y cafeterías; cada sucursal es un "tenant" distinto y no son intercambiables.

- Pide código de facturación, folio y RFC. Hay **dos campos de RFC**: llena ambos.
- Flujo: Facturar → Prefactura (el receptor se llena desde el SAT) → Siguiente (vista previa PDF) → confirmar con correos.
- La vista previa es un PDF dentro de un iframe (ViewerJS): se lee con `contentDocument.body.innerText` para comparar RFC, nombre, total y forma de pago.
- **El botón de confirmar ya timbra:** el diálogo de correos aparece con la factura emitida. No busques otro botón de timbrar ni repitas el clic; revisa si la pantalla dice que el comprobante se generó.
- La forma de pago viene del ticket y no se puede cambiar.
- El spinner "Generando comprobante" puede quedarse colgado aunque ya timbró. "Recuperar comprobante" con el RFC lista lo emitido para ese receptor: úsalo **antes** de timbrar (contra duplicados) y después del spinner.
- Las ligas de descarga de XML y PDF son URLs firmadas que bajan con `curl` sin cookies. El zip de "Descargar archivos" a veces responde 403 sin la sesión: descárgalo desde el navegador con `window.location.href`.
- El XML trae BOM UTF-8 y el orden de los atributos cambia entre emisores: no lo valides con `grep`, usa `cfdi_mx.py verificar`.
- Totales con uno o dos centavos de diferencia contra el ticket por redondeo de IVA o IEPS.
- Si la sucursal emite fuera de la ventana, el PDF trae en observaciones los folios de los tickets: sirve para emparejar cada factura con su ticket.

## facturasgas.com (gasolineras)

- Pide RFC (con lupa que carga un receptor guardado), razón social, correo, CP, régimen, uso, forma de pago y el **número de rastreo** del ticket (no el de transacción).
- Dos pasos: **Agregar** valida el ticket y lo acumula; después **Solicitar factura**. Sin Agregar, el ticket no se envía.
- No hay vista previa: verifica los campos en pantalla.
- El envío por automatización se ha quedado colgado varias veces seguidas. Antes de reintentar, busca en la consulta de facturas (RFC y rastreo) si existe. Si se cuelga, deja el formulario lleno y que el usuario dé el clic en su pestaña.
- Las ligas de descarga son `href="#"`; la ruta real sigue el patrón `https://facturasgas.com/cfdi/<AAAA-MM>/<RFC emisor>/<RFC receptor>/<archivo>.{xml,pdf}` y se obtiene con `javascript_tool` en la página de consulta.
- El número de rastreo no viene en el XML; el PDF sí lo trae al pie.

## gasofac.mx (AlvicFac, gasolineras)

- Paso 1: referencia, fecha e importe, con **Cloudflare Turnstile**: lo resuelve el usuario.
- Elige la fecha en el calendario: tecleada, el selector la puede leer como mes/día.
- Una referencia con `&` puede leerse como `8`. Si el portal dice a la vez que el importe y la fecha no corresponden, sospecha de la referencia.
- Paso 2: busca el RFC con la lupa. **La forma de pago viene en 01 Efectivo**: cámbiala. Uso y régimen son selects aparte. Timbra directo, sin vista previa.
- Descarga con ruta predecible del mismo estilo: `https://gasofac.mx/cfdi/<AAAA-MM>/<RFC emisor>/<RFC receptor>/<archivo>.{xml,pdf}`.

## mybusinesspos (`postools.mybusinesspos.net/autofactura33.aspx?rfc=<RFC emisor>&cuid=<token>`)

Tiendas cuyo ticket trae número de venta y token.

- El botón del sitio del comercio abre una ventana emergente que puede no aparecer: navega directo a esa URL.
- **Teclea el RFC y sal con Tab**: eso consulta y llena nombre, CP y correo guardados. Con `form_input` el valor no llega al servidor ("El R.F.C. es requerido"). No teclees encima de lo autocompletado: se duplica.
- Sin vista previa ni campo de forma de pago. Confirmar timbra directo y lleva al detalle con ligas a XML y PDF que bajan con `curl`.

## Portales con captcha de suma (algunas cadenas de gasolineras)

- Uno o dos captchas por sesión: los teclea el usuario.
- Pueden pedir banco y últimos cuatro dígitos de la tarjeta (del voucher).
- Sin uso de CFDI (sale G03) ni forma de pago (la toma de la tarjeta): revisa que G03 sea válido para el perfil antes de usar ese portal.
- La consulta para descargar suele ser por fecha de **timbrado**, no de consumo.

## Formularios que piden la Constancia y entregan por correo

- Piden la Constancia de Situación Fiscal reciente (algunos, con menos de tres meses) en PDF o imagen. Condicionar la factura a ella es infracción (CFF art. 83, fr. IX): ofrece primero la Cédula y sube la Constancia solo con el "sí" del usuario para ese portal.
- La forma de pago es obligatoria aunque el ticket no la imprima: pregúntala, no la deduzcas.
- No timbran al momento: la factura llega por correo en uno o dos días hábiles. Deja la fila "Pendiente" con nota "solicitada".
- Para pedir solo nombre, RFC, régimen y CP, la **Cédula de datos fiscales** del SAT expone menos datos que la Constancia.

## Apps de viaje y servicios

- La factura se pide dentro de la app, con la cuenta del viaje; el CFDI llega al correo registrado en la app.
- El recibo del viaje no es comprobante fiscal: archívalo como `comercio_total_recibo.pdf` en el día del viaje y, cuando llegue el CFDI, `archivar` lo pone junto.

## Sin autofactura

Algunos comercios solo facturan en ventanilla o por correo, dentro del mes. Márcalo en la configuración como ventana `"mes"` y en las notas cómo se pide.
