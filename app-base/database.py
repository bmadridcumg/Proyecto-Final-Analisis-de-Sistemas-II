import os
import time
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "asilo")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "db_asilo")

if DB_HOST:
    URL_BASE_DATOS = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        "?charset=utf8mb4"
    )
else:
    # Sin MySQL (desarrollo fuera de Docker) se usa SQLite.
    URL_BASE_DATOS = os.getenv("DATABASE_URL", "sqlite:///asilo.db")

motor = create_engine(URL_BASE_DATOS, pool_pre_ping=True, future=True)
Sesion = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass

@contextmanager
def candado(nombre: str, segundos: int = 10):
    """Solo una peticion a la vez entra a la seccion protegida (GET_LOCK de MySQL).

    Usa una conexion aparte para que el candado no dependa de la transaccion.
    En SQLite (desarrollo) no hace nada: ahi no hay peticiones simultaneas.
    """
    if motor.dialect.name != "mysql":
        yield
        return
    with motor.connect() as conexion:
        obtenido = conexion.execute(text("SELECT GET_LOCK(:n, :s)"),
                                    {"n": nombre, "s": segundos}).scalar()
        if obtenido != 1:
            raise TimeoutError(nombre)
        try:
            yield
        finally:
            conexion.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": nombre})


def crear_tablas(intentos: int = 12, espera: int = 5) -> None:
    """MySQL en Docker tarda en aceptar conexiones: se reintenta."""
    import models  # noqa: F401  (registra las clases en el metadata)

    for intento in range(1, intentos + 1):
        try:
            Base.metadata.create_all(bind=motor)
            return
        except OperationalError as error:
            if intento == intentos:
                raise
            print(f"[base de datos] intento {intento}/{intentos}: {error.orig}")
            time.sleep(espera)
