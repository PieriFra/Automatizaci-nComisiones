"""
dahi_parser.py
==============
Parser específico para las planillas de cobranza de la empresa DAHI.

Reutiliza los helpers de bajo nivel de planilla_parser.py (regex de
importe, limpieza de nombres de celda) sin modificar ese archivo — DAHI
tiene su propio formato de encabezado y sus propios campos, así que vive
en un módulo aparte en vez de sumarle ramas a los parsers de DP/Fills.

Diferencias con el formato DP/Fills:
  - No hay distinción de tipo 1/2 por nombre de archivo: toda planilla
    DAHI es una única tabla (pdfplumber), sin variantes.
  - El encabezado dice "Informe de Cobranza N°<numero>" (no "Planilla
    N°<numero>"), y trae "Empresa: DAHI" en el propio texto del PDF.
  - Además de "Comisiones (X%)" hay una línea "Fletes (X%)" que también
    se extrae y valida.
  - El nombre de archivo no sigue un patrón confiable (ni número de tipo
    ni el nombre de la empresa) — todo se lee del contenido del PDF.
"""

import os
import re
import sys

import pdfplumber

# Los parsers de DP/Fills viven en la raíz del proyecto (carpeta hermana);
# se agrega al path para poder reutilizar sus helpers genéricos sin
# duplicar código ni convertir la raíz en un paquete instalable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planilla_parser import _RX_IMPORTE, _parse_monto, _limpiar_nombre

_NO_CLIENTE = {
    "CLIENTE", "SUBTOTAL", "TOTAL",
    "COMISIONES", "COMISION",
    "FLETES", "REPARTO", "RETIRO", "EFECTIVO",
}

_RX_COMISION = re.compile(r'^COMISIONES?\s*\((\d+(?:[.,]\d+)?)\s*%\)\s*$', re.IGNORECASE)
_RX_FLETES   = re.compile(r'^FLETES?\s*\((\d+(?:[.,]\d+)?)\s*%\)\s*$', re.IGNORECASE)
_RX_INFORME  = re.compile(r'INFORME\s+DE\s+COBRANZA\s+N[°º*]?\s*(\d+)', re.IGNORECASE)
_RX_EMPRESA  = re.compile(r'EMPRESA\s*:\s*(.+)', re.IGNORECASE)
_RX_FECHA    = re.compile(r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b')


def _extraer_cabecera_dahi(texto: str) -> tuple:
    """Devuelve (informe, empresa, fecha) leídos del texto del PDF."""
    informe = "N/D"
    empresa = "N/D"
    fecha = "N/D"

    lineas = texto.splitlines()
    for i, linea in enumerate(lineas):
        linea_up = linea.upper().strip()

        m = _RX_INFORME.search(linea_up)
        if m:
            informe = f"INFORME N°{m.group(1)}"

        m = _RX_EMPRESA.search(linea)
        if m:
            empresa = m.group(1).strip()

        if "PUBLICACI" in linea_up and i + 1 < len(lineas):
            m = _RX_FECHA.search(lineas[i + 1])
            if m:
                fecha = m.group(1).replace("-", "/")

    return informe, empresa, fecha


def parsear_planilla_dahi(pdf_path: str) -> dict:
    """
    Devuelve:
      informe, empresa, fecha, total, comisiones, pct_comision,
      fletes, pct_fletes, subtotales (dict cliente -> monto)
    """
    todas_las_filas = []
    texto_completo = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto_completo += "\n" + (page.extract_text() or "")
            for tabla in page.extract_tables():
                todas_las_filas.extend(tabla)

    informe, empresa, fecha = _extraer_cabecera_dahi(texto_completo)

    total = 0.0
    comisiones = 0.0
    pct_comision = None
    fletes = 0.0
    pct_fletes = None
    subtotales: dict = {}
    cliente_actual = None

    for fila in todas_las_filas:
        if not fila:
            continue

        celda0 = _limpiar_nombre(fila[0] or "")
        celda_imp = (fila[8] or "").strip() if len(fila) > 8 else ""
        celda0_up = celda0.upper()

        if not celda0:
            continue

        primera_palabra = celda0_up.split()[0] if celda0_up.split() else ""

        if celda0_up == "TOTAL":
            m = _RX_IMPORTE.search(celda_imp)
            if m:
                total = _parse_monto(m.group(1))
            continue

        m_com = _RX_COMISION.match(celda0_up)
        if m_com:
            pct_comision = float(m_com.group(1).replace(",", "."))
            m = _RX_IMPORTE.search(celda_imp)
            if m:
                comisiones = _parse_monto(m.group(1))
            continue

        m_fle = _RX_FLETES.match(celda0_up)
        if m_fle:
            pct_fletes = float(m_fle.group(1).replace(",", "."))
            m = _RX_IMPORTE.search(celda_imp)
            if m:
                fletes = _parse_monto(m.group(1))
            continue

        if primera_palabra in _NO_CLIENTE:
            if celda0_up == "SUBTOTAL":
                m = _RX_IMPORTE.search(celda_imp)
                if m and cliente_actual:
                    monto = _parse_monto(m.group(1))
                    subtotales[cliente_actual] = subtotales.get(cliente_actual, 0.0) + monto
            continue

        cliente_actual = celda0

    return {
        "informe": informe,
        "empresa": empresa,
        "fecha": fecha,
        "total": total,
        "comisiones": comisiones,
        "pct_comision": pct_comision,
        "fletes": fletes,
        "pct_fletes": pct_fletes,
        "subtotales": subtotales,
    }
