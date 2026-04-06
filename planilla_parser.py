"""
planilla_parser.py
==================
Parsea el texto extraído de una planilla de cobranza (cualquier formato)
y devuelve los datos estructurados necesarios para el cálculo de comisiones.

Diseñado para trabajar con texto limpio (sin ruido de OCR), pero tolera
pequeñas variaciones de formato.

Funciones exportadas
--------------------
    parsear_planilla(texto: str) -> dict
        Devuelve: {
            "planilla":    str,   # ej. "PLANILLA N°127"
            "fecha":       str,   # ej. "31/03/2026"
            "total":       float,
            "comisiones":  float,
            "subtotales":  dict,  # {nombre_cliente_original: monto_float}
        }
"""

import re
import unicodedata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RX_IMPORTE = re.compile(r'\$\s*([\d.]+,\d{2})')


def _parse_monto(cadena: str) -> float:
    """Convierte '1.234.567,89' → 1234567.89"""
    cadena = cadena.replace(".", "").replace(",", ".")
    return float(cadena)


def _normalizar(s: str) -> str:
    """Upper + quita acentos + colapsa espacios."""
    s = (s or "").upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Extracción de campos de cabecera
# ---------------------------------------------------------------------------

def _extraer_cabecera(lineas: list[str]) -> tuple[str, str]:
    """
    Busca la línea de planilla y la fecha en el texto.
    Soporta ambos formatos:
      - ZIP:  "Planilla N°127" / "31/03/2026" / "FECHA DE PUBLICACIÓN"
              (la fecha aparece UNA línea ANTES de la etiqueta)
      - OCR:  "FECHA DE PUBLICACIÓN" / "31/03/2026"
              (la fecha aparece UNA línea DESPUÉS de la etiqueta)
      - Todo en una línea: "PLANILLA N° 127 ... 31/03/2026"
    """
    planilla = "N/D"
    fecha    = "N/D"

    for i, linea in enumerate(lineas):
        linea_up = linea.upper().strip()

        # Detectar línea de planilla
        if re.search(r'PLANILLA\s*(N[°º]?\s*\d+|DE\s+COBRANZA)', linea_up):
            m = re.search(r'N[°º]?\s*(\d+)', linea_up)
            if m:
                planilla = f"PLANILLA N°{m.group(1)}"

        # ── Fecha: formato ZIP (fecha en línea i, etiqueta en línea i+1) ──
        sig = lineas[i + 1].upper().strip() if i + 1 < len(lineas) else ""
        if "PUBLICACI" in sig:
            m = re.search(r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b', linea)
            if m:
                fecha = m.group(1).replace("-", "/")
                continue  # ya encontramos la fecha, seguimos buscando planilla

        # ── Fecha: formato OCR (etiqueta en línea i, fecha en línea i+1) ──
        if "PUBLICACI" in linea_up and i + 1 < len(lineas):
            m = re.search(r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b', lineas[i + 1])
            if m:
                fecha = m.group(1).replace("-", "/")

    return planilla, fecha


# ---------------------------------------------------------------------------
# Extracción de TOTAL y COMISIONES
# ---------------------------------------------------------------------------

def _extraer_totales(lineas: list[str]) -> tuple[float, float]:
    """
    Busca las líneas TOTAL y Comisiones/COMISIONES.
    Soporta:
      - "TOTAL $16.753.734,84"
      - "Comisiones $1.340.298,79"
      - Formato OCR donde los números siguen en líneas separadas
    """
    total      = 0.0
    comisiones = 0.0

    for i, linea in enumerate(lineas):
        linea_s = linea.strip()
        linea_up = linea_s.upper()

        # TOTAL (línea que empieza exactamente con TOTAL, no SUBTOTAL)
        if re.match(r'^TOTAL\b', linea_up) and not linea_up.startswith("SUBTOTAL"):
            m = _RX_IMPORTE.search(linea_s)
            if m:
                total = _parse_monto(m.group(1))

        # COMISIONES
        if re.match(r'^COMISIONES?\b', linea_up):
            m = _RX_IMPORTE.search(linea_s)
            if m:
                comisiones = _parse_monto(m.group(1))

    return total, comisiones


# ---------------------------------------------------------------------------
# Extracción de subtotales por cliente
# ---------------------------------------------------------------------------

def _extraer_subtotales(lineas: list[str]) -> dict[str, float]:
    """
    Recorre el texto línea a línea y empareja cada SUBTOTAL con el
    nombre del cliente que lo precede.

    Soporta dos variantes de formato:
      - ZIP / OCR:     toda la fila en una sola línea
                       "Aversa Facundo Efectivo R 0001-00006160 24-03-2026 $493.857,60 Pagada"
      - PDF digital:   la fila puede partirse en dos líneas cuando el Nro de
                       Factura o la Fecha no caben en la columna:
                       "Gagliano Maria Emilia ... Efectivo R 2222- 25-03- $224.874,14 Pagada"
                       "00000457 2026"   ← línea de continuación (sin método de pago ni $)

    Estrategia:
      - Una línea es "fila de cliente" si contiene un método de pago conocido
        (Efectivo, Transferencia, Cheque, etc.) y no empieza con palabra clave
        de encabezado/metadatos.
      - El nombre del cliente es todo lo anterior al método de pago.
      - La línea siguiente que no sea SUBTOTAL/TOTAL/encabezado y no contenga
        método de pago se trata como continuación de la fila anterior (se ignora
        para nombres, solo importa que el cliente_actual ya está seteado).
      - Cuando se encuentra SUBTOTAL, se asigna al cliente_actual.

    Devuelve un dict {nombre_original_del_cliente: monto_subtotal}
    """
    _EXCLUIR = re.compile(
        r'^(SUBTOTAL|TOTAL|CLIENTE|MÉTODO|METODO|ESTADO|IMPORTE|'
        r'INFORME|EMPRESA|PLANILLA|FECHA|COMISIONES?|FLETES?|REPARTO|'
        r'RETIRO|REITRO|EFECTIVO DESPU)',
        re.IGNORECASE
    )
    _RX_METODO_PAGO = re.compile(
        r'\b(Efectivo|Transferencia|Cheque|Débito|Debito|Crédito|Credito|Otros?)\b',
        re.IGNORECASE,
    )

    subtotales: dict[str, float] = {}
    cliente_actual: str | None = None

    for linea in lineas:
        linea_s = linea.strip()
        if not linea_s:
            continue

        linea_up = linea_s.upper()

        # ── SUBTOTAL: asignar al cliente actual ──
        if linea_up.startswith("SUBTOTAL"):
            m = _RX_IMPORTE.search(linea_s)
            if m and cliente_actual:
                monto = _parse_monto(m.group(1))
                subtotales[cliente_actual] = subtotales.get(cliente_actual, 0.0) + monto
            continue

        # ── Ignorar encabezados y metadatos ──
        if _EXCLUIR.match(linea_s):
            continue

        # ── Fila de cliente: contiene método de pago ──
        m_pago = _RX_METODO_PAGO.search(linea_s)
        if m_pago:
            nombre = linea_s[:m_pago.start()].strip()
            if nombre:
                cliente_actual = nombre
            # Si no hay nombre antes del método de pago (raro), mantener el anterior
            continue

        # ── Línea de continuación (resto de Nro Factura / Fecha partido en 2 líneas) ──
        # No contiene método de pago, no es SUBTOTAL/TOTAL, no es encabezado.
        # Simplemente la ignoramos — cliente_actual ya está seteado por la línea anterior.

    return subtotales


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def parsear_planilla(texto: str) -> dict:
    """
    Parsea el texto de una planilla de cobranza y devuelve un diccionario
    con todos los datos estructurados.

    Parámetros
    ----------
    texto : str
        Texto completo extraído del PDF (por cualquier estrategia).

    Devuelve
    --------
    dict con claves:
        planilla   : str
        fecha      : str
        total      : float
        comisiones : float
        subtotales : dict[str, float]   {nombre_cliente: monto}
    """
    lineas = texto.splitlines()

    planilla, fecha      = _extraer_cabecera(lineas)
    total, comisiones    = _extraer_totales(lineas)
    subtotales           = _extraer_subtotales(lineas)

    return {
        "planilla":   planilla,
        "fecha":      fecha,
        "total":      total,
        "comisiones": comisiones,
        "subtotales": subtotales,
    }