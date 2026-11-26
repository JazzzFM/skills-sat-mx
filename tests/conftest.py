import importlib.util
import pathlib
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="session")
def fiscal():
    return cargar("fiscal_mx", "herramientas/fiscal_mx.py")


@pytest.fixture(scope="session")
def tipo_cambio():
    return cargar("tipo_cambio_banxico", "herramientas/tipo_cambio_banxico.py")


@pytest.fixture(scope="session")
def documentos():
    return cargar("documentos", "herramientas/documentos.py")


@pytest.fixture()
def fx(tmp_path):
    fabrica = cargar("fabrica", "tests/fixtures/fabrica.py")
    return fabrica.generar(tmp_path / "fx")


@pytest.fixture(scope="session")
def cfdi():
    return cargar("cfdi_mx", "herramientas/cfdi_mx.py")


@pytest.fixture(scope="session")
def autofactura():
    return cargar("autofactura", "herramientas/autofactura.py")


@pytest.fixture(scope="session")
def xmls():
    return cargar("fixtures_cfdi", "tests/fixtures/cfdi.py")
