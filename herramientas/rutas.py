"""Reglas de rutas compartidas: los datos personales viven fuera del repo o dentro de personal/, nunca en otro lado.

git solo ignora personal/ (y los patrones de .gitignore); un CSV o una carpeta de facturas creada en la raíz o en
ejemplos/ se versionaría con un `git add -A`. Las herramientas que escriben datos personales llaman a
`exigir_fuera_del_repo_o_en_personal` antes de escribir.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def dentro_del_repo_fuera_de_personal(ruta):
    p = pathlib.Path(ruta).expanduser().resolve()
    try:
        p.relative_to(RAIZ)
    except ValueError:
        return False  # fuera del repo
    try:
        p.relative_to((RAIZ / "personal").resolve())
    except ValueError:
        return True
    return False


def exigir_fuera_del_repo_o_en_personal(ruta, que="el archivo"):
    if dentro_del_repo_fuera_de_personal(ruta):
        raise ValueError(f"{que} {ruta} quedaría dentro del repo pero fuera de personal/ y git lo versionaría; "
                         "usa una ruta bajo personal/ (por ejemplo personal/trabajo/)")
    return pathlib.Path(ruta)
