"""
Capa de base de datos SQLite.
Guarda clientes, facturas y registro de recordatorios enviados.
"""
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Integer, Float,
    DateTime, Boolean, Text, ForeignKey, Date
)
from sqlalchemy.orm import DeclarativeBase, relationship, Session
import config


engine = create_engine(config.DATABASE_URL, echo=False)


class Base(DeclarativeBase):
    pass


class Cliente(Base):
    __tablename__ = "clientes"

    rut = Column(String(12), primary_key=True)
    razon_social = Column(String(200), nullable=False)
    email = Column(String(100))
    telefono_wpp = Column(String(20))   # Formato: +56912345678
    activo = Column(Boolean, default=True)
    notas = Column(Text)
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    facturas = relationship("Factura", back_populates="cliente")
    recordatorios = relationship("Recordatorio", back_populates="cliente")


class Factura(Base):
    __tablename__ = "facturas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    folio = Column(Integer, nullable=False)
    tipo_dte = Column(String(10), nullable=False)   # 33=Factura, 39=Boleta, etc.
    cliente_rut = Column(String(12), ForeignKey("clientes.rut"))
    fecha_emision = Column(Date, nullable=False)
    monto_neto = Column(Float, default=0)
    monto_iva = Column(Float, default=0)
    monto_total = Column(Float, default=0)
    estado = Column(String(20), default="EMITIDA")  # EMITIDA, ANULADA, ACEPTADA
    detalle_json = Column(Text)   # JSON con líneas de detalle
    sincronizado_sii = Column(Boolean, default=False)
    creado_en = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="facturas")


class Recordatorio(Base):
    __tablename__ = "recordatorios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_rut = Column(String(12), ForeignKey("clientes.rut"))
    fecha_envio = Column(DateTime, default=datetime.utcnow)
    semana = Column(String(10))   # Ej: "2024-W05"
    mensaje = Column(Text)
    enviado = Column(Boolean, default=False)
    error = Column(Text)

    cliente = relationship("Cliente", back_populates="recordatorios")


def init_db():
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


# ── Helpers ──────────────────────────────────────────────────────────────────

def upsert_cliente(rut: str, razon_social: str, telefono_wpp: str = None,
                   email: str = None, notas: str = None) -> Cliente:
    with get_session() as s:
        cliente = s.get(Cliente, rut)
        if cliente is None:
            cliente = Cliente(rut=rut, razon_social=razon_social)
            s.add(cliente)
        cliente.razon_social = razon_social
        if telefono_wpp:
            cliente.telefono_wpp = telefono_wpp
        if email:
            cliente.email = email
        if notas:
            cliente.notas = notas
        cliente.actualizado_en = datetime.utcnow()
        s.commit()
        s.refresh(cliente)
        return cliente


def guardar_factura(folio: int, tipo_dte: str, cliente_rut: str,
                    fecha_emision, monto_neto: float, monto_iva: float,
                    monto_total: float, detalle_json: str = None) -> Factura:
    with get_session() as s:
        existe = s.query(Factura).filter_by(folio=folio, tipo_dte=tipo_dte).first()
        if existe:
            return existe
        factura = Factura(
            folio=folio, tipo_dte=tipo_dte, cliente_rut=cliente_rut,
            fecha_emision=fecha_emision, monto_neto=monto_neto,
            monto_iva=monto_iva, monto_total=monto_total,
            detalle_json=detalle_json, sincronizado_sii=True,
        )
        s.add(factura)
        s.commit()
        s.refresh(factura)
        return factura


def get_ultimo_pedido(cliente_rut: str) -> Factura | None:
    with get_session() as s:
        return (
            s.query(Factura)
            .filter_by(cliente_rut=cliente_rut, estado="EMITIDA")
            .order_by(Factura.fecha_emision.desc())
            .first()
        )


def get_clientes_activos() -> list[Cliente]:
    with get_session() as s:
        return s.query(Cliente).filter_by(activo=True).all()


def registrar_recordatorio(cliente_rut: str, semana: str, mensaje: str,
                            enviado: bool, error: str = None):
    with get_session() as s:
        r = Recordatorio(
            cliente_rut=cliente_rut,
            semana=semana,
            mensaje=mensaje,
            enviado=enviado,
            error=error,
        )
        s.add(r)
        s.commit()
