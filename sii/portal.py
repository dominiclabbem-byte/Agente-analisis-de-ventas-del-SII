"""
Automatización del Portal MIPYME del SII con Playwright.

Flujo:
  1. Autenticación con RUT + Clave Tributaria
  2. Navegación al historial de DTE emitidos
  3. Extracción de facturas por cliente y período
  4. Sincronización con base de datos local
"""
import json
import logging
from datetime import date, datetime
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

import config
from storage.database import upsert_cliente, guardar_factura

logger = logging.getLogger(__name__)

# Tipo de DTE
TIPO_DTE = {
    "33": "Factura Electrónica",
    "34": "Factura No Afecta Electrónica",
    "39": "Boleta Electrónica",
    "41": "Boleta No Afecta Electrónica",
    "56": "Nota de Débito Electrónica",
    "61": "Nota de Crédito Electrónica",
}


class SIIPortal:
    """
    Automatiza el Portal MIPYME del SII para extraer historial de facturas.
    Usar con context manager: `with SIIPortal() as portal:`
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._autenticado = False

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            locale="es-CL",
            timezone_id=config.TIMEZONE,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = self._context.new_page()
        return self

    def __exit__(self, *_):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    # ── Autenticación ─────────────────────────────────────────────────────────

    def autenticar(self) -> bool:
        """Inicia sesión en el SII con RUT y clave tributaria."""
        if self._autenticado:
            return True

        logger.info("Autenticando en SII con RUT %s ...", config.SII_RUT)
        page = self._page

        # Página de login del SII
        page.goto("https://zeusr.sii.cl/AUT2000/InicioAutenticacion/IngresarRutClave.html",
                  wait_until="networkidle", timeout=30_000)

        # Ingresar RUT (sin puntos ni dígito verificador en el campo de RUT base)
        rut_sin_dv, dv = config.SII_RUT.replace(".", "").split("-")
        page.fill("#rutcntr", rut_sin_dv)
        page.fill("#dv", dv)
        page.fill("#clave", config.SII_CLAVE)
        page.click("#bt_ingresar")

        # Esperar redirección post-login
        try:
            page.wait_for_url("**/portal.html", timeout=15_000)
            self._autenticado = True
            logger.info("Autenticación exitosa.")
            return True
        except Exception:
            # Verificar si hay mensaje de error
            error_msg = page.query_selector(".alert-danger, #error_msg")
            if error_msg:
                logger.error("Error login SII: %s", error_msg.inner_text())
            else:
                logger.error("Timeout esperando portal SII post-login.")
            return False

    # ── Extracción de historial ───────────────────────────────────────────────

    def obtener_facturas_emitidas(
        self,
        fecha_desde: date,
        fecha_hasta: date,
        tipo_dte: str = "33",
    ) -> list[dict]:
        """
        Extrae facturas emitidas desde el portal de consulta de DTE del SII.
        Retorna lista de dicts con datos de cada factura.
        """
        if not self._autenticado:
            if not self.autenticar():
                raise RuntimeError("No se pudo autenticar en SII.")

        page = self._page
        resultados = []

        logger.info(
            "Consultando DTE tipo %s entre %s y %s ...",
            tipo_dte, fecha_desde, fecha_hasta,
        )

        # Navegar al portal de consulta de DTE emitidos
        page.goto(
            "https://www4.sii.cl/consdteweb/index.html",
            wait_until="networkidle", timeout=30_000,
        )

        # Seleccionar RUT emisor (ya debería estar pre-llenado)
        page.wait_for_selector("#fechaDesde", timeout=10_000)

        # Limpiar y llenar fechas
        page.fill("#fechaDesde", fecha_desde.strftime("%d/%m/%Y"))
        page.fill("#fechaHasta", fecha_hasta.strftime("%d/%m/%Y"))

        # Seleccionar tipo DTE
        page.select_option("#tipoDte", tipo_dte)

        # Buscar
        page.click("#btnBuscar")
        page.wait_for_load_state("networkidle", timeout=30_000)

        # Extraer tabla de resultados
        filas = page.query_selector_all("table.tabla-dte tbody tr")

        for fila in filas:
            celdas = fila.query_selector_all("td")
            if len(celdas) < 7:
                continue
            try:
                folio = int(celdas[0].inner_text().strip())
                fecha_str = celdas[1].inner_text().strip()
                rut_receptor = celdas[2].inner_text().strip()
                razon_social = celdas[3].inner_text().strip()
                monto_neto = _parse_monto(celdas[4].inner_text())
                monto_iva = _parse_monto(celdas[5].inner_text())
                monto_total = _parse_monto(celdas[6].inner_text())
                estado = celdas[7].inner_text().strip() if len(celdas) > 7 else "EMITIDA"

                # Obtener detalle si está disponible (clic en folio)
                detalle = self._obtener_detalle_factura(page, folio, tipo_dte)

                resultado = {
                    "folio": folio,
                    "tipo_dte": tipo_dte,
                    "fecha_emision": datetime.strptime(fecha_str, "%d/%m/%Y").date(),
                    "rut_receptor": rut_receptor,
                    "razon_social": razon_social,
                    "monto_neto": monto_neto,
                    "monto_iva": monto_iva,
                    "monto_total": monto_total,
                    "estado": estado.upper(),
                    "detalle": detalle,
                }
                resultados.append(resultado)

            except Exception as e:
                logger.warning("Error procesando fila de factura: %s", e)
                continue

        logger.info("Se extrajeron %d facturas.", len(resultados))
        return resultados

    def _obtener_detalle_factura(
        self, page: Page, folio: int, tipo_dte: str
    ) -> list[dict]:
        """Intenta obtener el detalle de items de una factura específica."""
        try:
            enlace = page.query_selector(f"a[href*='{folio}']")
            if not enlace:
                return []

            with page.expect_popup(timeout=8_000) as popup_info:
                enlace.click()
            popup = popup_info.value
            popup.wait_for_load_state("networkidle", timeout=10_000)

            items = []
            filas = popup.query_selector_all("table.detalle-dte tbody tr")
            for fila in filas:
                celdas = fila.query_selector_all("td")
                if len(celdas) >= 4:
                    items.append({
                        "nombre": celdas[0].inner_text().strip(),
                        "cantidad": celdas[1].inner_text().strip(),
                        "precio_unitario": _parse_monto(celdas[2].inner_text()),
                        "monto": _parse_monto(celdas[3].inner_text()),
                    })
            popup.close()
            return items

        except Exception:
            return []

    def sincronizar_con_bd(
        self,
        fecha_desde: date,
        fecha_hasta: date,
        tipos_dte: list[str] = None,
    ) -> int:
        """
        Descarga facturas del SII y las guarda en la base de datos local.
        Retorna cantidad de facturas sincronizadas.
        """
        if tipos_dte is None:
            tipos_dte = ["33", "39"]   # Facturas y boletas

        total = 0
        for tipo in tipos_dte:
            facturas = self.obtener_facturas_emitidas(fecha_desde, fecha_hasta, tipo)
            for f in facturas:
                # Asegurar que el cliente existe en BD
                upsert_cliente(
                    rut=f["rut_receptor"],
                    razon_social=f["razon_social"],
                )
                # Guardar factura
                guardar_factura(
                    folio=f["folio"],
                    tipo_dte=f["tipo_dte"],
                    cliente_rut=f["rut_receptor"],
                    fecha_emision=f["fecha_emision"],
                    monto_neto=f["monto_neto"],
                    monto_iva=f["monto_iva"],
                    monto_total=f["monto_total"],
                    detalle_json=json.dumps(f["detalle"], ensure_ascii=False),
                )
                total += 1

        logger.info("Sincronización completada: %d facturas guardadas.", total)
        return total


# ── Utilidades ────────────────────────────────────────────────────────────────

def _parse_monto(texto: str) -> float:
    """Convierte '$ 1.234.567' → 1234567.0"""
    limpio = texto.replace("$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(limpio)
    except ValueError:
        return 0.0
