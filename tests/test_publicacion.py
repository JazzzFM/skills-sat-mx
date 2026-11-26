"""El repo no publica datos personales: rutas prohibidas y RFC, CURP o CLABE de personas físicas."""
import pathlib
import shutil
import subprocess

import pytest


def test_detecta_rutas_y_contenido(revisor):
    problemas = revisor.revisar([
        ("personal/constancia.pdf", None),
        ("Claveprivada_FIEL.key", None),
        ("visor.csv", "fecha,total"),
        ("README.md", "Mi RFC es GOAM850101AB1 y mi CLABE 012180001234567890"),
        ("tests/fixtures/x.py", "RFC = 'GOAM850101AB1'"),          # exento: persona ficticia
        ("ejemplos/config.json", '{"rfc": "LOPA900101AB1"}'),     # permitido
    ])
    texto = "\n".join(problemas)
    assert "personal/constancia.pdf" in texto and ".key" in texto and "visor.csv" in texto
    assert "README.md:1: RFC" in texto and "CLABE" in texto
    assert "tests/fixtures" not in texto and "ejemplos" not in texto


@pytest.mark.skipif(shutil.which("git") is None, reason="requiere git")
def test_lo_rastreado_no_trae_datos_personales(revisor):
    raiz = pathlib.Path(__file__).resolve().parents[1]
    if not (raiz / ".git").exists():
        pytest.skip("no es un clon de git")
    salida = subprocess.run(["git", "ls-files"], cwd=raiz, capture_output=True, text=True).stdout.splitlines()
    archivos = []
    for n in salida:
        try:
            archivos.append((n, (raiz / n).read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            archivos.append((n, None))
    assert revisor.revisar(archivos) == []
