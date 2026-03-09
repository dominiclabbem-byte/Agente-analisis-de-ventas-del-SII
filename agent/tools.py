"""
Definición de herramientas (tools) para el agente Claude.
Cada tool mapea a una acción concreta sobre SII, BD o WhatsApp.
"""
import json
import logging
from datetime import date, datetime, timedelta

import config
from storage import database as db
from whatsapp.sender import enviar_mensaje, enviar_mensajes_masivos

logger = logging.getLogger(__name__)

# ── Definiciones de tools para Claude API ─────────────────────────────────────

TOOLS = [
    {
        "name": "sincronizar_facturas_sii",
        "description": (
            "Accede al portal del SII y descarga el historial de facturas emitidas "
            "para un rango de fechas. Guarda los datos en la base de datos local. "
            "Úsala cuando necesites actualizar el historial de ventas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha_desde": {
                    "type": "string",
                    "description": "Fecha inicio en formato YYYY-MM-DD",
                },
                "fecha_hasta": {
                    "type": "string",
                    "description": "Fecha término en formato YYYY-MM-DD",
                },
                "tipos_dte": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tipos de DTE a consultar. '33'=Factura, '39'=Boleta. Default: ['33','39']",
                },
            },
            "required": ["fecha_desde", "fecha_hasta"],
        },
    },
    {
        "name": "obtener_clientes",
        "description": (
            "Retorna la lista de clientes activos con sus datos de contacto "
            "y el último pedido registrado de cada uno."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "obtener_ultimo_pedido_cliente",
        "description": (
            "Retorna el último pedido (factura más reciente) de un cliente específico, "
            "incluyendo el detalle de productos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rut_cliente": {
                    "type": "string",
                    "description": "RUT del cliente con dígito verificador, ej: '12345678-9'",
                },
            },
            "required": ["rut_cliente"],
        },
    },
    {
        "name": "registrar_cliente",
        "description": (
            "Registra o actualiza un cliente en la base de datos con su número de WhatsApp."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rut": {"type": "string", "description": "RUT con dígito verificador"},
                "razon_social": {"type": "string", "description": "Nombre o razón social"},
                "telefono_wpp": {
                    "type": "string",
                    "description": "Número WhatsApp en formato +56XXXXXXXXX",
                },
                "email": {"type": "string"},
                "notas": {"type": "string", "description": "Notas adicionales sobre el cliente"},
            },
            "required": ["rut", "razon_social"],
        },
    },
    {
        "name": "enviar_recordatorio_whatsapp",
        "description": (
            "Envía un mensaje de WhatsApp de recordatorio de stock a UN cliente específico."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rut_cliente": {"type": "string", "description": "RUT del cliente"},
                "mensaje": {"type": "string", "description": "Texto del mensaje a enviar"},
            },
            "required": ["rut_cliente", "mensaje"],
        },
    },
    {
        "name": "enviar_recordatorios_masivos",
        "description": (
            "Envía recordatorios de stock a TODOS los clientes activos que tengan "
            "número de WhatsApp registrado. Genera un mensaje personalizado para cada uno "
            "basado en su último pedido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "semana": {
                    "type": "string",
                    "description": "Identificador de semana, ej: '2024-W05'. Si no se provee, usa la semana actual.",
                },
            },
        },
    },
    {
        "name": "resumen_ventas",
        "description": (
            "Genera un resumen de ventas para un período determinado: "
            "total vendido, número de facturas, ticket promedio y top clientes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha_desde": {"type": "string", "description": "YYYY-MM-DD"},
                "fecha_hasta": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["fecha_desde", "fecha_hasta"],
        },
    },
]


# ── Implementación de cada tool ────────────────────────────────────────────────

def ejecutar_tool(nombre: str, parametros: dict) -> str:
    """Despacha la llamada al tool correspondiente y retorna resultado como string."""
    try:
        if nombre == "sincronizar_facturas_sii":
            return _sincronizar_facturas_sii(**parametros)
        elif nombre == "obtener_clientes":
            return _obtener_clientes()
        elif nombre == "obtener_ultimo_pedido_cliente":
            return _obtener_ultimo_pedido_cliente(**parametros)
        elif nombre == "registrar_cliente":
            return _registrar_cliente(**parametros)
        elif nombre == "enviar_recordatorio_whatsapp":
            return _enviar_recordatorio_whatsapp(**parametros)
        elif nombre == "enviar_recordatorios_masivos":
            return _enviar_recordatorios_masivos(**parametros)
        elif nombre == "resumen_ventas":
            return _resumen_ventas(**parametros)
        else:
            return f"Tool '{nombre}' no reconocida."
    except Exception as e:
        logger.exception("Error ejecutando tool %s: %s", nombre, e)
        return f"Error ejecutando {nombre}: {e}"


def _sincronizar_facturas_sii(
    fecha_desde: str, fecha_hasta: str, tipos_dte: list = None
) -> str:
    # Import aquí para evitar cargar Playwright si no se necesita
    from sii.portal import SIIPortal

    f_desde = date.fromisoformat(fecha_desde)
    f_hasta = date.fromisoformat(fecha_hasta)
    tipos = tipos_dte or ["33", "39"]

    with SIIPortal(headless=True) as portal:
        total = portal.sincronizar_con_bd(f_desde, f_hasta, tipos)

    return (
        f"Sincronización completada. Se guardaron {total} facturas del "
        f"{fecha_desde} al {fecha_hasta}."
    )


def _obtener_clientes() -> str:
    clientes = db.get_clientes_activos()
    if not clientes:
        return "No hay clientes registrados en la base de datos."

    resultado = []
    for c in clientes:
        ultimo = db.get_ultimo_pedido(c.rut)
        resultado.append({
            "rut": c.rut,
            "razon_social": c.razon_social,
            "telefono_wpp": c.telefono_wpp or "Sin registrar",
            "ultimo_pedido_fecha": str(ultimo.fecha_emision) if ultimo else "Sin pedidos",
            "ultimo_pedido_total": f"${ultimo.monto_total:,.0f}" if ultimo else "-",
        })

    return json.dumps(resultado, ensure_ascii=False, indent=2)


def _obtener_ultimo_pedido_cliente(rut_cliente: str) -> str:
    cliente = None
    with db.get_session() as s:
        cliente = s.get(db.Cliente, rut_cliente)

    if not cliente:
        return f"Cliente {rut_cliente} no encontrado en la base de datos."

    factura = db.get_ultimo_pedido(rut_cliente)
    if not factura:
        return f"El cliente {cliente.razon_social} no tiene pedidos registrados."

    detalle = []
    if factura.detalle_json:
        try:
            detalle = json.loads(factura.detalle_json)
        except Exception:
            pass

    return json.dumps({
        "cliente": cliente.razon_social,
        "rut": rut_cliente,
        "folio": factura.folio,
        "tipo_dte": factura.tipo_dte,
        "fecha_emision": str(factura.fecha_emision),
        "monto_total": factura.monto_total,
        "detalle": detalle,
    }, ensure_ascii=False, indent=2)


def _registrar_cliente(rut: str, razon_social: str, telefono_wpp: str = None,
                       email: str = None, notas: str = None) -> str:
    db.upsert_cliente(rut, razon_social, telefono_wpp, email, notas)
    return f"Cliente {razon_social} ({rut}) registrado/actualizado correctamente."


def _enviar_recordatorio_whatsapp(rut_cliente: str, mensaje: str) -> str:
    with db.get_session() as s:
        cliente = s.get(db.Cliente, rut_cliente)

    if not cliente:
        return f"Cliente {rut_cliente} no encontrado."
    if not cliente.telefono_wpp:
        return f"El cliente {cliente.razon_social} no tiene número de WhatsApp registrado."

    resultado = enviar_mensaje(cliente.telefono_wpp, mensaje)
    semana = _semana_actual()
    db.registrar_recordatorio(
        cliente_rut=rut_cliente,
        semana=semana,
        mensaje=mensaje,
        enviado=resultado["error"] is None,
        error=resultado.get("error"),
    )

    if resultado["error"]:
        return f"Error enviando a {cliente.razon_social}: {resultado['error']}"
    return f"Mensaje enviado exitosamente a {cliente.razon_social} ({cliente.telefono_wpp})."


def _enviar_recordatorios_masivos(semana: str = None) -> str:
    semana = semana or _semana_actual()
    clientes = db.get_clientes_activos()

    sin_telefono = []
    enviados = []
    errores = []

    for cliente in clientes:
        if not cliente.telefono_wpp:
            sin_telefono.append(cliente.razon_social)
            continue

        ultimo = db.get_ultimo_pedido(cliente.rut)
        mensaje = _generar_mensaje_recordatorio(cliente, ultimo)

        resultado = enviar_mensaje(cliente.telefono_wpp, mensaje)
        db.registrar_recordatorio(
            cliente_rut=cliente.rut,
            semana=semana,
            mensaje=mensaje,
            enviado=resultado["error"] is None,
            error=resultado.get("error"),
        )

        if resultado["error"]:
            errores.append(f"{cliente.razon_social}: {resultado['error']}")
        else:
            enviados.append(cliente.razon_social)

    resumen = (
        f"Recordatorios semana {semana}:\n"
        f"  - Enviados exitosamente: {len(enviados)}\n"
        f"  - Errores: {len(errores)}\n"
        f"  - Sin número WhatsApp: {len(sin_telefono)}\n"
    )
    if errores:
        resumen += f"\nErrores:\n" + "\n".join(f"  - {e}" for e in errores)
    if sin_telefono:
        resumen += f"\nSin WhatsApp:\n" + "\n".join(f"  - {n}" for n in sin_telefono)
    return resumen


def _resumen_ventas(fecha_desde: str, fecha_hasta: str) -> str:
    f_desde = date.fromisoformat(fecha_desde)
    f_hasta = date.fromisoformat(fecha_hasta)

    with db.get_session() as s:
        facturas = (
            s.query(db.Factura)
            .filter(
                db.Factura.fecha_emision >= f_desde,
                db.Factura.fecha_emision <= f_hasta,
                db.Factura.estado == "EMITIDA",
            )
            .all()
        )

    if not facturas:
        return f"No hay facturas entre {fecha_desde} y {fecha_hasta}."

    total = sum(f.monto_total for f in facturas)
    promedio = total / len(facturas)

    # Agrupar por cliente
    por_cliente: dict[str, float] = {}
    for f in facturas:
        por_cliente[f.cliente_rut] = por_cliente.get(f.cliente_rut, 0) + f.monto_total

    top = sorted(por_cliente.items(), key=lambda x: x[1], reverse=True)[:5]

    # Resolver nombres
    top_con_nombre = []
    for rut, monto in top:
        with db.get_session() as s:
            c = s.get(db.Cliente, rut)
        nombre = c.razon_social if c else rut
        top_con_nombre.append({"cliente": nombre, "total": monto})

    return json.dumps({
        "periodo": f"{fecha_desde} al {fecha_hasta}",
        "total_facturas": len(facturas),
        "total_vendido": total,
        "ticket_promedio": round(promedio, 2),
        "top_5_clientes": top_con_nombre,
    }, ensure_ascii=False, indent=2)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _semana_actual() -> str:
    hoy = date.today()
    return f"{hoy.isocalendar().year}-W{hoy.isocalendar().week:02d}"


def _generar_mensaje_recordatorio(cliente: db.Cliente, ultimo: db.Factura | None) -> str:
    """Genera el mensaje de recordatorio personalizado para un cliente."""
    nombre = cliente.razon_social.split()[0]  # Primer palabra del nombre

    if ultimo is None:
        return (
            f"Hola {nombre}! 👋\n\n"
            f"Te escribimos desde {config.EMPRESA['razon_social']}.\n"
            f"¿Necesitas stock para esta semana?\n\n"
            f"Escríbenos y te cotizamos de inmediato. 😊"
        )

    # Parsear detalle del último pedido
    detalle_str = ""
    if ultimo.detalle_json:
        try:
            items = json.loads(ultimo.detalle_json)
            if items:
                lineas = [
                    f"  • {it['nombre']} x{it['cantidad']}"
                    for it in items[:5]  # Máx 5 items
                ]
                detalle_str = "\n".join(lineas)
        except Exception:
            pass

    fecha_pedido = ultimo.fecha_emision.strftime("%d/%m/%Y")
    dias = (date.today() - ultimo.fecha_emision).days

    mensaje = (
        f"Hola {nombre}! 👋\n\n"
        f"Te escribimos desde {config.EMPRESA['razon_social']}.\n\n"
        f"Tu último pedido fue el *{fecha_pedido}* (hace {dias} días)"
    )

    if detalle_str:
        mensaje += f":\n{detalle_str}"

    mensaje += (
        f"\n\n¿Necesitas reponer stock para esta semana? "
        f"Cuéntanos y preparamos tu pedido. 📦"
    )

    return mensaje
