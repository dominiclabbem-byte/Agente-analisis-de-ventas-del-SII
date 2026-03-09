"""
Script de prueba: conecta al SII via requests (sin navegador).
Prueba login y consulta de DTE emitidos.
Ejecutar con: python test_sii.py
"""
import sys
import json
import logging
import requests
from datetime import date, timedelta
from urllib.parse import urlencode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

import config

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9",
}


def test_login_sii():
    print("\n" + "="*60)
    print("  PRUEBA DE CONEXIÓN AL SII (via HTTP)")
    print("="*60)
    print(f"  RUT:      {config.SII_RUT}")
    print(f"  Empresa:  {config.EMPRESA['razon_social']}")
    print("="*60)

    session = requests.Session()
    session.headers.update(HEADERS)

    rut_partes = config.SII_RUT.replace(".", "").split("-")
    rut_cuerpo = rut_partes[0]
    rut_dv     = rut_partes[1]

    # ── STEP 1: Obtener página de login para cookies ─────────────────────────
    print("\n1. Obteniendo página de login...")
    login_url = "https://zeusr.sii.cl/AUT2000/InicioAutenticacion/IngresarRutClave.html"
    r = session.get(login_url, timeout=15)
    print(f"   HTTP {r.status_code} - Cookies: {dict(session.cookies)}")

    # ── STEP 2: POST de credenciales ─────────────────────────────────────────
    print("\n2. Enviando credenciales...")
    post_url = "https://hercules.sii.cl/cgi_AUT2000/autenticacion/ingreso.html"
    payload = {
        "rutcntr": rut_cuerpo,
        "dv":      rut_dv,
        "clave":   config.SII_CLAVE,
        "referencia": "https://www4.sii.cl",
    }
    r2 = session.post(post_url, data=payload, allow_redirects=True, timeout=15)
    print(f"   HTTP {r2.status_code} | URL final: {r2.url}")
    print(f"   Cookies post-login: {list(session.cookies.keys())}")

    # Detectar si tenemos token de sesión SII
    token_keys = [k for k in session.cookies.keys() if "token" in k.lower() or "sii" in k.lower() or "auth" in k.lower()]
    if token_keys or "JSESSIONID" in session.cookies or len(session.cookies) > 1:
        print("   ✅ LOGIN EXITOSO - Sesión establecida")
        autenticado = True
    else:
        # Revisar contenido de la respuesta
        if "clave incorrecta" in r2.text.lower() or "error" in r2.text.lower()[:500]:
            print("   ❌ LOGIN FALLIDO - Credenciales incorrectas")
            print(f"   Respuesta: {r2.text[:300]}")
            autenticado = False
        else:
            print("   ⚠️  Respuesta recibida, verificando contenido...")
            print(f"   Primeros 400 chars: {r2.text[:400]}")
            autenticado = True

    if not autenticado:
        return False

    # ── STEP 3: Consultar DTE emitidos ───────────────────────────────────────
    print("\n3. Consultando DTE emitidos del último mes...")
    hoy     = date.today()
    desde   = (hoy - timedelta(days=30)).strftime("%d/%m/%Y")
    hasta   = hoy.strftime("%d/%m/%Y")
    rut_num = rut_cuerpo + rut_dv  # sin guión para la query

    dte_url = "https://www4.sii.cl/consdteweb/consultaDteServicio.html"
    params = {
        "option":     "resEmitidos",
        "fechaDesde": desde,
        "fechaHasta": hasta,
        "tipoDte":    "33",
        "RUT":        rut_num,
    }
    r3 = session.get(dte_url, params=params, timeout=15)
    print(f"   HTTP {r3.status_code} | URL: {r3.url}")

    if r3.status_code == 200:
        contenido = r3.text[:600]
        print(f"   Contenido respuesta:\n{contenido}\n")

        if "folio" in r3.text.lower() or "factura" in r3.text.lower() or "<tr" in r3.text.lower():
            print("   ✅ SE ENCONTRARON FACTURAS EN LA RESPUESTA")
        elif "no se encontraron" in r3.text.lower() or "sin documentos" in r3.text.lower():
            print("   ℹ️  Sin facturas en el período consultado")
        else:
            print("   ⚠️  Respuesta recibida (puede requerir sesión renovada)")
    else:
        print(f"   ❌ Error HTTP {r3.status_code}")

    # ── STEP 4: Probar API alternativa de SII ────────────────────────────────
    print("\n4. Probando endpoint de info del contribuyente...")
    info_url = f"https://www4.sii.cl/consdteweb/consultaDteServicio.html"
    r4 = session.get(
        f"https://siichile.cl/cgi_dte/UPL/DTEUpload",
        timeout=10
    )
    print(f"   HTTP {r4.status_code}")

    return True


def test_twilio():
    print("\n" + "="*60)
    print("  PRUEBA TWILIO WHATSAPP")
    print("="*60)
    from twilio.rest import Client
    try:
        client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        account = client.api.accounts(config.TWILIO_ACCOUNT_SID).fetch()
        print(f"   ✅ Cuenta Twilio: {account.friendly_name}")
        print(f"   Estado: {account.status}")
        return True
    except Exception as e:
        print(f"   ❌ Error Twilio: {e}")
        return False


def test_anthropic():
    print("\n" + "="*60)
    print("  PRUEBA ANTHROPIC API")
    print("="*60)
    import anthropic
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": "Di solo: OK"}],
        )
        resp = msg.content[0].text
        print(f"   ✅ Claude responde: {resp}")
        return True
    except Exception as e:
        print(f"   ❌ Error Anthropic: {e}")
        return False


if __name__ == "__main__":
    resultados = {}
    resultados["SII"]       = test_login_sii()
    resultados["Twilio"]    = test_twilio()
    resultados["Anthropic"] = test_anthropic()

    print("\n" + "="*60)
    print("  RESUMEN")
    print("="*60)
    for servicio, ok in resultados.items():
        estado = "✅ OK" if ok else "❌ FALLO"
        print(f"  {servicio:<12} {estado}")
    print("="*60)
