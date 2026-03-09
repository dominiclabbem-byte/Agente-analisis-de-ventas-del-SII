"""
Módulo para envío de mensajes WhatsApp vía Twilio.

Requisitos previos:
  1. Crear cuenta en https://www.twilio.com/try-twilio
  2. Activar WhatsApp Sandbox: Console > Messaging > Try it out > Send a WhatsApp message
  3. Pedir a cada cliente que envíe "join <palabra>" al número sandbox de Twilio
  4. (Producción) Solicitar número de WhatsApp Business aprobado

Variables de entorno necesarias:
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
"""
import logging
from typing import Optional

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

import config

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        if not config.TWILIO_ACCOUNT_SID or not config.TWILIO_AUTH_TOKEN:
            raise RuntimeError(
                "Faltan credenciales Twilio. "
                "Define TWILIO_ACCOUNT_SID y TWILIO_AUTH_TOKEN en .env"
            )
        _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _client


def enviar_mensaje(telefono: str, mensaje: str) -> dict:
    """
    Envía un mensaje WhatsApp al número indicado.

    Args:
        telefono: Número en formato E.164, ej: '+56912345678'
        mensaje:  Texto del mensaje (máx 1600 caracteres)

    Returns:
        dict con 'sid', 'estado' y 'error' (None si fue exitoso)
    """
    telefono = _normalizar_telefono(telefono)
    if not telefono:
        return {"sid": None, "estado": "ERROR", "error": "Número de teléfono inválido"}

    try:
        client = _get_client()
        message = client.messages.create(
            from_=f"whatsapp:{config.TWILIO_WHATSAPP_FROM}",
            to=f"whatsapp:{telefono}",
            body=mensaje[:1600],
        )
        logger.info("WhatsApp enviado a %s | SID: %s", telefono, message.sid)
        return {"sid": message.sid, "estado": message.status, "error": None}

    except TwilioRestException as e:
        logger.error("Error Twilio enviando a %s: %s", telefono, e.msg)
        return {"sid": None, "estado": "ERROR", "error": str(e.msg)}

    except Exception as e:
        logger.error("Error inesperado enviando WhatsApp a %s: %s", telefono, e)
        return {"sid": None, "estado": "ERROR", "error": str(e)}


def enviar_mensajes_masivos(destinatarios: list[dict]) -> list[dict]:
    """
    Envía mensajes a una lista de destinatarios.

    Args:
        destinatarios: Lista de dicts con 'telefono' y 'mensaje'

    Returns:
        Lista de resultados por destinatario
    """
    resultados = []
    for dest in destinatarios:
        resultado = enviar_mensaje(dest["telefono"], dest["mensaje"])
        resultado["telefono"] = dest["telefono"]
        resultados.append(resultado)
    return resultados


def _normalizar_telefono(telefono: str) -> str:
    """
    Normaliza el número al formato E.164.
    Asume prefijo chileno (+56) si no tiene código de país.
    """
    if not telefono:
        return ""
    limpio = "".join(c for c in telefono if c.isdigit() or c == "+")
    if not limpio.startswith("+"):
        # Si empieza con 56 y tiene 11 dígitos → +56...
        if limpio.startswith("56") and len(limpio) == 11:
            limpio = "+" + limpio
        # Si empieza con 9 y tiene 9 dígitos → +569...
        elif limpio.startswith("9") and len(limpio) == 9:
            limpio = "+56" + limpio
        else:
            limpio = "+56" + limpio
    return limpio
