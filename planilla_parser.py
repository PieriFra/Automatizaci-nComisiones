"""
planilla_parser.py
==================
Parsea planillas de cobranza y devuelve datos estructurados.

Tipo 2: texto plano (columnas básicas)
Tipo 1: tabla pdfplumber (columnas extra: N° Cuenta, N° Operación, Fecha de Pago)
"""

import re
import unicodedata
import pdfplumber


_RX_IMPORTE = re.compile(r'\$\s*([\d.]+,\d{2})')


def _parse_monto(cadena: str) -> float:
    return float(cadena.replace(".", "").replace(",", "."))


def _normalizar(s: str) -> str:
    s = (s or "").upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip()


def _limpiar_nombre(nombre: str) -> str:
    return " ".join(nombre.replace("\n", " ").split())


# ---------------------------------------------------------------------------
# Cabecera — común a ambos tipos
# ---------------------------------------------------------------------------

def _extraer_cabecera(lineas: list) -> tuple:
    planilla = "N/D"
    fecha    = "N/D"

    for i, linea in enumerate(lineas):
        linea_up = linea.upper().strip()

        if re.search(r'PLANILLA\s*(N[°º]?\s*\d+|DE\s+COBRANZA)', linea_up):
            m = re.search(r'N[°º]?\s*(\d+)', linea_up)
            if m:
                planilla = f"PLANILLA N°{m.group(1)}"

        sig = lineas[i + 1].upper().strip() if i + 1 < len(lineas) else ""
        if "PUBLICACI" in sig:
            m = re.search(r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b', linea)
            if m:
                fecha = m.group(1).replace("-", "/")
                continue

        if "PUBLICACI" in linea_up and i + 1 < len(lineas):
            m = re.search(r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b', lineas[i + 1])
            if m:
                fecha = m.group(1).replace("-", "/")

    return planilla, fecha


# ---------------------------------------------------------------------------
# TIPO 2 — texto plano
# ---------------------------------------------------------------------------

def _parsear_tipo2(texto: str) -> dict:
    lineas = texto.splitlines()
    planilla, fecha = _extraer_cabecera(lineas)

    total      = 0.0
    comisiones = 0.0
    subtotales = {}
    cliente_actual = None

    _EXCLUIR = re.compile(
        r'^(SUBTOTAL|TOTAL|CLIENTE|MÉTODO|METODO|ESTADO|IMPORTE|'
        r'INFORME|EMPRESA|PLANILLA|FECHA|COMISIONES?|FLETES?|REPARTO|'
        r'RETIRO|REITRO|EFECTIVO DESPU)',
        re.IGNORECASE
    )
    _RX_METODO = re.compile(
        r'\b(Efectivo|Transferencia|Cheque|Débito|Debito|Crédito|Credito|Otros?|'
        r'E-CHEQ|Ret\.|RET)\b',
        re.IGNORECASE,
    )

    for linea in lineas:
        linea_s = linea.strip()
        if not linea_s:
            continue
        linea_up = linea_s.upper()

        if re.match(r'^TOTAL\b', linea_up) and not linea_up.startswith("SUBTOTAL"):
            m = _RX_IMPORTE.search(linea_s)
            if m:
                total = _parse_monto(m.group(1))
            continue

        if re.match(r'^COMISIONES?\s*\$', linea_up) or re.match(r'^COMISIONES?\s+\$', linea_up):
            m = _RX_IMPORTE.search(linea_s)
            if m:
                comisiones = _parse_monto(m.group(1))
            continue

        if linea_up.startswith("SUBTOTAL"):
            m = _RX_IMPORTE.search(linea_s)
            if m and cliente_actual:
                monto = _parse_monto(m.group(1))
                subtotales[cliente_actual] = subtotales.get(cliente_actual, 0.0) + monto
            continue

        if _EXCLUIR.match(linea_s):
            continue

        m_pago = _RX_METODO.search(linea_s)
        if m_pago:
            nombre = linea_s[:m_pago.start()].strip()
            if nombre:
                cliente_actual = nombre

    return {"planilla": planilla, "fecha": fecha, "total": total,
            "comisiones": comisiones, "subtotales": subtotales}


# ---------------------------------------------------------------------------
# TIPO 1 — tabla pdfplumber
# ---------------------------------------------------------------------------

def _parsear_tipo1(pdf_path: str) -> dict:
    todas_las_filas = []
    texto_completo  = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto_completo += "\n" + (page.extract_text() or "")
            for tabla in page.extract_tables():
                todas_las_filas.extend(tabla)

    planilla, fecha = _extraer_cabecera(texto_completo.splitlines())

    total      = 0.0
    comisiones = 0.0
    subtotales = {}
    cliente_actual = None

    # Regex: línea de comisiones estándar — "Comisiones", "Comisiones (8%)", etc.
    # Excluye: "Comisiones Totales", "Comision Rosental"
    _RX_COMISION_STD = re.compile(
        r'^COMISIONES?\s*(\(\d+%\)|TOTALES?)?\s*$',
        re.IGNORECASE
    )

    # Palabras que identifican filas que NO son clientes
    _NO_CLIENTE = {
        "CLIENTE", "SUBTOTAL", "TOTAL",
        "COMISIONES", "COMISION",
        "FLETES", "REPARTO", "RETIRO", "EFECTIVO",
    }

    for fila in todas_las_filas:
        if not fila:
            continue

        celda0    = _limpiar_nombre(fila[0] or "")
        celda_imp = (fila[8] or "").strip() if len(fila) > 8 else ""
        celda0_up = celda0.upper()

        if not celda0:
            continue

        primera_palabra = celda0_up.split()[0] if celda0_up.split() else ""

        # ── TOTAL ──
        if celda0_up == "TOTAL":
            m = _RX_IMPORTE.search(celda_imp)
            if m:
                total = _parse_monto(m.group(1))
            continue

        # ── COMISIONES estándar ── (antes de chequear _NO_CLIENTE)
        if _RX_COMISION_STD.match(celda0_up):
            m = _RX_IMPORTE.search(celda_imp)
            if m:
                comisiones = _parse_monto(m.group(1))
            continue

        # ── Ignorar encabezados y filas especiales ──
        if primera_palabra in _NO_CLIENTE:
            # Pero SUBTOTAL sí necesita procesarse
            if celda0_up == "SUBTOTAL":
                m = _RX_IMPORTE.search(celda_imp)
                if m and cliente_actual:
                    monto = _parse_monto(m.group(1))
                    subtotales[cliente_actual] = subtotales.get(cliente_actual, 0.0) + monto
            continue

        # ── Fila de cliente ──
        cliente_actual = celda0

    return {"planilla": planilla, "fecha": fecha, "total": total,
            "comisiones": comisiones, "subtotales": subtotales}


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def parsear_planilla(pdf_path: str, tipo_informe: int, texto: str = "") -> dict:
    if tipo_informe == 1:
        return _parsear_tipo1(pdf_path)
    else:
        return _parsear_tipo2(texto)