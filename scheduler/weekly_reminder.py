"""
Scheduler que ejecuta los recordatorios de stock cada lunes a la hora configurada.

Usa APScheduler con cron trigger.
"""
import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import config

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _job_recordatorios():
    """Job que ejecuta el agente de recordatorios semanales."""
    from agent.claude_agent import ejecutar_tarea_recordatorios
    logger.info("=== INICIANDO JOB SEMANAL DE RECORDATORIOS ===")
    try:
        resultado = ejecutar_tarea_recordatorios()
        logger.info("Job semanal completado:\n%s", resultado)
    except Exception as e:
        logger.exception("Error en job semanal de recordatorios: %s", e)


def iniciar_scheduler() -> BackgroundScheduler:
    """
    Inicia el scheduler en background.
    Ejecuta _job_recordatorios cada lunes a la hora configurada en REMINDER_TIME.
    """
    global _scheduler

    tz = pytz.timezone(config.TIMEZONE)
    hora, minuto = config.REMINDER_TIME.split(":")

    _scheduler = BackgroundScheduler(timezone=tz)

    # Trigger: cada lunes (day_of_week=0) a la hora configurada
    trigger = CronTrigger(
        day_of_week="mon",
        hour=int(hora),
        minute=int(minuto),
        timezone=tz,
    )

    _scheduler.add_job(
        _job_recordatorios,
        trigger=trigger,
        id="recordatorio_semanal",
        name="Recordatorio stock semanal (lunes)",
        replace_existing=True,
        misfire_grace_time=3600,   # Reintenta si se perdió la ejecución (hasta 1h después)
    )

    _scheduler.start()

    proximo = _scheduler.get_job("recordatorio_semanal").next_run_time
    logger.info(
        "Scheduler iniciado. Próximo recordatorio: %s",
        proximo.strftime("%A %d/%m/%Y %H:%M %Z"),
    )
    return _scheduler


def detener_scheduler():
    """Detiene el scheduler limpiamente."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido.")


def ejecutar_ahora():
    """Ejecuta el job de recordatorios de inmediato (para testing o ejecución manual)."""
    logger.info("Ejecutando recordatorios manualmente...")
    _job_recordatorios()
