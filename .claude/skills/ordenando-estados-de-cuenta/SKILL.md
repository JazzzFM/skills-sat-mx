---
name: ordenando-estados-de-cuenta
description: Usar cuando el usuario descarga estados de cuenta, recibos, facturas o capturas de bancos y apps (Banamex, DólarApp/ARQ, Nu, Klar, DiDi, servicios) con nombres como EstadodeCuenta-12.pdf, credit-statement-123.pdf o archivos ._ de macOS, y pide ordenarlos, renombrarlos, deduplicarlos, copiarlos a un repositorio o sacar de ellos los depósitos de un empleador o cliente del extranjero.
---

# Ordenando estados de cuenta

## Principio

Ordenar no destruye. Todo archivo termina en un destino con nombre estándar o apartado, queda un manifiesto para revertir, y lo personal nunca entra a git. **REQUIRED SUB-SKILL:** protegiendo-datos-y-tramites-sat.

## Convención

`<institucion>/[<producto>/]AAAA-MM-DD_<institucion>-<producto>_<tipo>.<ext>` (si el usuario ya tiene una carpeta ordenada, pásala como `--referencia`). La fecha sale del contenido, nunca del nombre ni de la descarga:

| Documento | Fecha |
|---|---|
| Banamex MiCuenta ("Período del 5 de … al 4 de … del AAAA") | corte (fin del periodo) |
| DólarApp/ARQ ("Fecha de inicio … Fecha de fin …") | fin del periodo |
| Tarjetas (Klar, Nu, DiDi) | fecha de corte |
| Servicios (telefonía, internet) | fecha límite de pago |
| CFDI XML | atributo `Fecha` |

## Flujo

1. **Proteger el destino.** Si la copia va a un repo, confirma que la carpeta (p. ej. `personal/`) esté en `.gitignore` o `.git/info/exclude` **antes** de copiar.
2. **Planear sin mover:**
   `python3 -I herramientas/documentos.py planear --origen <carpeta> --referencia <carpeta_ya_ordenada>`
   - Duplicados por **texto** (el mismo estado descargado dos veces tiene hash distinto) → `_duplicados/`.
   - Idénticos a uno ya ordenado en la referencia → reutiliza ese nombre.
   - `._*` de macOS → `_metadatos_macos/`.
   - Sin regla, PDF cifrado, dañado o escaneado → `_por_clasificar/`.
3. **Decidir con el usuario lo que quedó en `_por_clasificar`.** Lees el contenido (si es escaneo, como imagen), propones nombre con la tabla, y lo pasas en un CSV `original,nuevo` con `--mapa`.
4. **Ejecutar:** `python3 -I herramientas/documentos.py ordenar --origen <carpeta> --referencia … --mapa … --copia personal/estados-cuenta`. No sobrescribe, verifica el md5 de cada copia y escribe `MANIFIESTO.csv` en ambos lados. Las carpetas de referencia de otros proyectos no se tocan.
5. **Reportar:** estructura final, conteos (canónicos, duplicados, metadatos, por clasificar) y periodos faltantes (huecos de meses).

## Depósitos del extranjero

`python3 -I herramientas/documentos.py depositos --pagador "<NOMBRE>" --salida personal/trabajo/depositos.csv <pdfs…>` lee Banamex ("PAGO RECIBIDO DE … DIVISA:USD IMPORTE: $X/TC $Y") y DólarApp ("Compra USDc + X USD … PAGADOR") sin contar dos veces estados repetidos. Marca con `!!` los PDF que no pudo leer o que no son de esos bancos: esos meses no están en el CSV y hay que capturarlos a mano. La herramienta rechaza `--salida` dentro del repo fuera de `personal/`.

El tipo de cambio que imprime el banco **no** es el fiscal. Para ISR se usa el publicado por Banxico en el DOF el día hábil anterior al cobro (CFF art. 20), columna `pagos` de `herramientas/tipo_cambio_banxico.py`. **REQUIRED SUB-SKILL:** calculando-isr-sueldo-extranjero para el impuesto.

## Errores comunes

| Error | Corrección |
|---|---|
| Borrar duplicados "porque son iguales" | Apartar en `_duplicados/`; el usuario decide después |
| Detectar duplicados solo por hash | Comparar texto: cambia `/CreationDate` en cada descarga |
| Dejar archivos sin clasificar en su carpeta original | `_por_clasificar/` y decidir con el usuario |
| Fechar por el nombre ("ARQ - 2026-04") o por la descarga | Fecha del contenido según la tabla |
| Copiar al repo sin revisar `.gitignore` | Paso 1 primero |
| Dar por completos los depósitos con avisos `!!` | Capturar a mano los meses de PDF no leídos |
| Usar el TC del banco para el ISR | DOF del día hábil anterior |
| Mostrar números de cuenta o CLABE | Solo últimos 4 dígitos |
