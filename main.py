"""
Punto de entrada principal del agente.

Modos de ejecución:
  python main.py              → Inicia el scheduler (modo daemon para producción)
  python main.py --chat       → Chat interactivo en terminal
  python main.py --recordar   → Ejecuta los recordatorios ahora mismo (testing)
  python main.py --sync       → Sincroniza facturas del SII (últimos 30 días)
"""
import argparse
import logging
import signal
import sys
import time
from datetime import date, timedelta

# Configurar logging antes de cualquier import del proyecto
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def modo_daemon():
    """Inicia el scheduler en background y mantiene el proceso vivo."""
    from storage.database import init_db
    from scheduler.weekly_reminder import iniciar_scheduler, detener_scheduler

    logger.info("=" * 60)
    logger.info("  Agente SII - Recordatorios de Stock Semanales")
    logger.info("=" * 60)

    init_db()
    scheduler = iniciar_scheduler()

    # Manejar señales de apagado (Ctrl+C, kill)
    def _shutdown(signum, frame):
        logger.info("Señal de apagado recibida. Cerrando...")
        detener_scheduler()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Agente corriendo. Presiona Ctrl+C para detener.")
    logger.info("Los recordatorios se enviarán cada lunes automáticamente.")

    try:
        while True:
            time.sleep(60)  # Keep-alive loop
    except (KeyboardInterrupt, SystemExit):
        detener_scheduler()


def modo_chat():
    """Chat interactivo en terminal para probar el agente."""
    from storage.database import init_db
    from agent.claude_agent import AgenteVentas

    init_db()
    agente = AgenteVentas()

    print("\n" + "=" * 60)
    print("  Agente SII - Chat Interactivo")
    print("  (escribe 'salir' para terminar, 'nuevo' para nueva conversación)")
    print("=" * 60 + "\n")

    while True:
        try:
            entrada = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nChau!")
            break

        if not entrada:
            continue
        if entrada.lower() == "salir":
            print("Hasta luego!")
            break
        if entrada.lower() == "nuevo":
            agente.reiniciar_conversacion()
            print("Conversación reiniciada.\n")
            continue

        print("\nAgente: ", end="", flush=True)
        respuesta = agente.chat(entrada)
        print(respuesta)
        print()


def modo_recordar():
    """Ejecuta los recordatorios de inmediato."""
    from storage.database import init_db
    from scheduler.weekly_reminder import ejecutar_ahora

    init_db()
    ejecutar_ahora()


def modo_sync(dias: int = 30):
    """Sincroniza facturas del SII de los últimos N días."""
    from storage.database import init_db
    from sii.portal import SIIPortal

    init_db()
    hoy = date.today()
    desde = hoy - timedelta(days=dias)

    logger.info("Sincronizando facturas desde %s hasta %s ...", desde, hoy)
    with SIIPortal(headless=True) as portal:
        total = portal.sincronizar_con_bd(desde, hoy, tipos_dte=["33", "39"])
    logger.info("Sincronización completa: %d facturas importadas.", total)


def main():
    parser = argparse.ArgumentParser(
        description="Agente SII - Recordatorios de Stock por WhatsApp"
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Iniciar chat interactivo en terminal",
    )
    parser.add_argument(
        "--recordar",
        action="store_true",
        help="Ejecutar recordatorios ahora mismo (sin esperar el lunes)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Sincronizar facturas SII de los últimos 30 días",
    )
    parser.add_argument(
        "--dias",
        type=int,
        default=30,
        help="Número de días hacia atrás para sincronizar (default: 30)",
    )

    args = parser.parse_args()

    if args.chat:
        modo_chat()
    elif args.recordar:
        modo_recordar()
    elif args.sync:
        modo_sync(args.dias)
    else:
        modo_daemon()


if __name__ == "__main__":
    main()
