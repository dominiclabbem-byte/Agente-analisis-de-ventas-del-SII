import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Directorios
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CAF_DIR = DATA_DIR / "caf"
DTE_DIR = DATA_DIR / "dte"

for d in [DATA_DIR, CAF_DIR, DTE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# SII
SII_RUT = os.getenv("SII_RUT", "")
SII_CLAVE = os.getenv("SII_CLAVE", "")
SII_AMBIENTE = os.getenv("SII_AMBIENTE", "CERTIFICACION")

# URLs SII según ambiente
SII_URLS = {
    "CERTIFICACION": {
        "login": "https://hercules.sii.cl/cgi_AUT2000/autenticacion/ingreso.html",
        "portal_mipyme": "https://www4.sii.cl/mipeFacturacion/",
        "consulta_dte": "https://www4.sii.cl/consdteweb/",
    },
    "PRODUCCION": {
        "login": "https://homer.sii.cl/",
        "portal_mipyme": "https://www4.sii.cl/mipeFacturacion/",
        "consulta_dte": "https://www4.sii.cl/consdteweb/",
    },
}

SII_BASE_URLS = SII_URLS[SII_AMBIENTE]

# Empresa
EMPRESA = {
    "razon_social": os.getenv("EMPRESA_RAZON_SOCIAL", ""),
    "giro": os.getenv("EMPRESA_GIRO", ""),
    "direccion": os.getenv("EMPRESA_DIRECCION", ""),
    "comuna": os.getenv("EMPRESA_COMUNA", ""),
    "rut": SII_RUT,
}

# WhatsApp / Meta Cloud API
META_WHATSAPP_PHONE_NUMBER_ID = os.getenv("META_WHATSAPP_PHONE_NUMBER_ID", "")
META_WHATSAPP_ACCESS_TOKEN = os.getenv("META_WHATSAPP_ACCESS_TOKEN", "")
META_WHATSAPP_API_VERSION = os.getenv("META_WHATSAPP_API_VERSION", "v19.0")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Scheduler
REMINDER_TIME = os.getenv("REMINDER_TIME", "09:00")
TIMEZONE = os.getenv("TIMEZONE", "America/Santiago")

# Base de datos
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/sii_agent.db")
