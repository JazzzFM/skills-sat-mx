"""Revisa que nada personal se vaya a publicar: rutas prohibidas, llaves y RFC, CURP o CLABE de personas físicas.

Modos:
  --staged  archivos en el índice de git (úsalo como pre-commit: git config core.hooksPath .githooks)
  --todo    todo lo rastreado (lo corre la CI)
  --hook    hook PreToolUse de Claude Code: lee el JSON de stdin y, si el comando Bash hace git add, commit o push,
            revisa lo rastreado y lo que `git add -A` agregaría; sale con 2 para bloquear el comando.

Exentos de la revisión de contenido: tests/ (persona ficticia) e investigacion/ (fuentes públicas). Las rutas
prohibidas se revisan en todos lados. Sale con 1 (o 2 con --hook) si encuentra algo.
"""
import argparse
import json
import re
import subprocess
import sys

RUTAS_PROHIBIDAS = [
    (re.compile(r"^personal(/|$)"), "documentos personales (personal/)"),
    (re.compile(r"\.(key|cer|pfx|p12|pem|req)$", re.I), "llave o certificado"),
    (re.compile(r"(^|/)\.env$"), "variables de entorno"),
    (re.compile(r"^[^/]+\.csv$"), "CSV en la raíz (las salidas van en personal/)"),
    (re.compile(r"(^|/)CLAUDE\.local\.md$"), "instrucciones locales del agente"),
    (re.compile(r"(^|/)settings\.local\.json$"), "configuración local del agente"),
]
EXENTOS_CONTENIDO = re.compile(r"^(tests|investigacion)/")
PERMITIDOS = {"LOPA900101AB1", "XAXX010101000", "XEXX010101000"}  # persona ficticia y RFC genéricos del SAT
PATRONES = [
    (re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d(?![A-Za-z0-9])"), "CURP"),
    (re.compile(r"(?<![A-Za-z0-9Ñ&])[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}(?![A-Za-z0-9])"), "RFC de persona física"),
    (re.compile(r"(?<!\d)\d{18}(?!\d)"), "posible CLABE"),
]


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def revisar(rutas_y_contenido):
    """[(ruta, texto o None)] -> lista de problemas."""
    problemas = []
    for ruta, texto in rutas_y_contenido:
        for patron, motivo in RUTAS_PROHIBIDAS:
            if patron.search(ruta):
                problemas.append(f"{ruta}: {motivo}")
        if texto is None or EXENTOS_CONTENIDO.match(ruta):
            continue
        for patron, motivo in PATRONES:
            for m in patron.finditer(texto):
                if m.group() not in PERMITIDOS:
                    linea = texto.count("\n", 0, m.start()) + 1
                    problemas.append(f"{ruta}:{linea}: {motivo} ({m.group()[:4]}…)")
    return problemas


def _leer(ruta, indice=False):
    try:
        datos = _git("show", f":{ruta}") if indice else open(ruta, encoding="utf-8").read()
        return datos
    except (UnicodeDecodeError, OSError, subprocess.CalledProcessError):
        return None  # binario o borrado: solo se revisa la ruta


def archivos_staged():
    nombres = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
    return [(n, _leer(n, indice=True)) for n in nombres]


def archivos_rastreados(con_no_rastreados=False):
    nombres = set(_git("ls-files").splitlines())
    if con_no_rastreados:
        nombres |= set(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return [(n, _leer(n)) for n in sorted(nombres)]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--staged", action="store_true")
    g.add_argument("--todo", action="store_true")
    g.add_argument("--hook", action="store_true")
    a = p.parse_args(argv)
    if a.hook:
        try:
            comando = json.load(sys.stdin).get("tool_input", {}).get("command", "")
        except (ValueError, AttributeError):
            return 0
        if not re.search(r"\bgit\b[^;&|]*\b(add|commit|push)\b", comando):
            return 0
        problemas = revisar(archivos_rastreados(con_no_rastreados=True))
    else:
        problemas = revisar(archivos_staged() if a.staged else archivos_rastreados())
    if problemas:
        print("Bloqueado: esto publicaría datos personales o llaves:", file=sys.stderr)
        for x in problemas[:30]:
            print(f"  - {x}", file=sys.stderr)
        print("Mueve esos archivos a personal/ (ignorado por git) o quita el dato; si es un ejemplo ficticio, "
              "agrégalo a PERMITIDOS en herramientas/revisar_publicacion.py.", file=sys.stderr)
        return 2 if a.hook else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
