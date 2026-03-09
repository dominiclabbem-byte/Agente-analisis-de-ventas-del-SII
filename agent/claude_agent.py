"""
Agente Claude que orquesta las operaciones SII + WhatsApp.

Recibe instrucciones en lenguaje natural y decide qué tools usar.
"""
import logging
from typing import Optional

import anthropic

import config
from agent.tools import TOOLS, ejecutar_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""Eres un asistente de negocios inteligente para la empresa {config.EMPRESA['razon_social']}.

Tu rol principal es:
1. Acceder al historial de facturas del SII para conocer el último pedido de cada cliente.
2. Enviar recordatorios personalizados por WhatsApp cada lunes para preguntar si necesitan stock.
3. Responder consultas sobre ventas, clientes y análisis del negocio.

Principios:
- Siempre sincroniza las facturas antes de enviar recordatorios si el usuario lo solicita.
- Los mensajes de WhatsApp deben ser amigables, breves y personalizados con el último pedido.
- Si un cliente no tiene teléfono registrado, infórmalo al usuario.
- Presenta los resúmenes de ventas de forma clara con cifras formateadas en pesos chilenos.
- Cuando el usuario pida "enviar recordatorios", usa la tool enviar_recordatorios_masivos.

Contexto empresa:
- Razón social: {config.EMPRESA['razon_social']}
- Giro: {config.EMPRESA['giro']}
- RUT: {config.EMPRESA['rut']}
"""


class AgenteVentas:
    """Agente conversacional con acceso a SII y WhatsApp."""

    def __init__(self):
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("Define ANTHROPIC_API_KEY en tu archivo .env")
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.historial: list[dict] = []

    def chat(self, mensaje_usuario: str) -> str:
        """
        Procesa un mensaje del usuario y retorna la respuesta del agente.
        Mantiene el historial de conversación.
        """
        self.historial.append({"role": "user", "content": mensaje_usuario})

        respuesta = self._ciclo_agente()
        self.historial.append({"role": "assistant", "content": respuesta})
        return respuesta

    def _ciclo_agente(self) -> str:
        """
        Ciclo agentico: llama a Claude, ejecuta tools si es necesario,
        y repite hasta obtener una respuesta final de texto.
        """
        mensajes = list(self.historial)

        while True:
            respuesta = self.client.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=mensajes,
            )

            # Si Claude quiere usar tools
            if respuesta.stop_reason == "tool_use":
                # Agregar la respuesta de Claude al contexto
                mensajes.append({
                    "role": "assistant",
                    "content": respuesta.content,
                })

                # Ejecutar cada tool solicitado
                resultados_tools = []
                for bloque in respuesta.content:
                    if bloque.type == "tool_use":
                        logger.info("Ejecutando tool: %s con %s", bloque.name, bloque.input)
                        resultado = ejecutar_tool(bloque.name, bloque.input)
                        logger.info("Resultado tool %s: %s", bloque.name, resultado[:200])
                        resultados_tools.append({
                            "type": "tool_result",
                            "tool_use_id": bloque.id,
                            "content": resultado,
                        })

                # Agregar resultados al contexto y continuar el ciclo
                mensajes.append({
                    "role": "user",
                    "content": resultados_tools,
                })

            else:
                # Respuesta final de texto
                texto = ""
                for bloque in respuesta.content:
                    if hasattr(bloque, "text"):
                        texto += bloque.text
                return texto.strip()

    def reiniciar_conversacion(self):
        """Limpia el historial de conversación."""
        self.historial = []
        logger.info("Conversación reiniciada.")


def ejecutar_tarea_recordatorios() -> str:
    """
    Función autónoma que el scheduler llama cada lunes.
    Sincroniza facturas del último mes y envía recordatorios a todos los clientes.
    """
    from datetime import date, timedelta

    agente = AgenteVentas()
    hoy = date.today()
    hace_30_dias = hoy - timedelta(days=30)

    instruccion = (
        f"Es lunes {hoy.strftime('%d/%m/%Y')}. "
        f"Por favor: "
        f"1) Sincroniza las facturas del SII desde el {hace_30_dias} hasta hoy. "
        f"2) Envía recordatorios de stock por WhatsApp a todos los clientes activos."
    )

    logger.info("Iniciando tarea automática de recordatorios semanales...")
    resultado = agente.chat(instruccion)
    logger.info("Tarea completada: %s", resultado)
    return resultado
