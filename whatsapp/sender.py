"""
Módulo para envío de mensajes WhatsApp vía Meta Cloud API.

Requisitos previos:
  1. Crear app en https://developers.facebook.com/apps/
  2. Agregar producto "WhatsApp" a la app
  3. En WhatsApp > Configuración de la API obtener:
     - Phone Number ID
     - Token de acceso (temporal para pruebas, permanente para producción)
  4. (Producción) Verificar cuenta Meta Business y solicitar número aprobado

Variables de entorno necesarias:
  META_WHATSAPP_PHONE_NUMBER_ID, META_WHATSAPP_ACCESS_TOKEN, META_WHATSAPP_API_VERSION
"""
import logging
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

_GRAPH_API_BASE = "https://graph.facebook.com"


def _get_headers() -> dict:
    if not config.META_WHATSAPP_ACCESS_TOKEN:
        raise RuntimeError(
            "Falta credencial Meta. "
            "Define META_WHATSAPP_ACCESS_TOKEN en .env"
        )
    if not config.META_WHATSAPP_PHONE_NUMBER_ID:
        raise RuntimeError(
            "Falta ID de número. "
            "Define META_WHATSAPP_PHONE_NUMBER_ID en .env"
        )
    return {
        "Authorization": f"Bearer {config.META_WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _get_url() -> str:
    version = config.META_WHATSAPP_API_VERSION or "v19.0"
    phone_id = config.META_WHATSAPP_PHONE_NUMBER_ID
    return f"{_GRAPH_API_BASE}/{version}/{phone_id}/messages"


def enviar_mensaje(telefono: str, mensaje: str) -> dict:
    """
    Envía un mensaje WhatsApp al número indicado via Meta Cloud API.

    Args:
        telefono: Número en formato E.164, ej: '+56912345678'
        mensaje:  Texto del mensaje (máx 4096 caracteres)

    Returns:
        dict con 'message_id', 'estado' y 'error' (None si fue exitoso)
    """
    telefono = _normalizar_telefono(telefono)
    if not telefono:
        return {"message_id": None, "estado": "ERROR", "error": "Número de teléfono inválido"}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefono,
        "type": "text",
        "text": {"preview_url": False, "body": mensaje[:4096]},
    }

    try:
        response = requests.post(
            _get_url(),
            headers=_get_headers(),
            json=payload,
            timeout=15,
        )
        data = response.json()

        if response.ok and "messages" in data:
            msg_id = data["messages"][0].get("id", "")
            logger.info("WhatsApp enviado a %s | ID: %s", telefono, msg_id)
            return {"message_id": msg_id, "estado": "sent", "error": None}

        error_msg = data.get("error", {}).get("message", response.text)
        logger.error("Error Meta API enviando a %s: %s", telefono, error_msg)
        return {"message_id": None, "estado": "ERROR", "error": error_msg}

    except requests.RequestException as e:
        logger.error("Error de red enviando WhatsApp a %s: %s", telefono, e)
        return {"message_id": None, "estado": "ERROR", "error": str(e)}


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
