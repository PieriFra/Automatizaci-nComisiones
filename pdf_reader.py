"""
pdf_reader.py
=============
Módulo de extracción de texto de PDFs con detección automática del tipo:

  1. ZIP disfrazado de .pdf  →  lee los .txt internos directamente (sin OCR)
  2. PDF digital normal      →  extrae texto con pdfplumber
  3. PDF escaneado (imagen)  →  fallback con Tesseract OCR (comportamiento original)

Funciones públicas:
    extraer_texto_pdf(pdf_path)  → str
    detectar_empresa(pdf_path)   → "DP" | "FILLS"
"""

import zipfile
import json
import re
import os

# ---------------------------------------------------------------------------
# Detección de empresa desde el nombre del archivo
# ---------------------------------------------------------------------------
 
def detectar_empresa(pdf_path: str) -> str:
    """
    Detecta a qué empresa pertenece la planilla según el nombre del archivo.
 
    Reglas:
      - Si el nombre contiene 'Fills' → "FILLS"
      - Si el nombre contiene 'DP'    → "DP"
 
    Lanza ValueError si no puede determinarlo.
    """
    nombre = os.path.basename(pdf_path).upper()
    if "FILLS" in nombre:
        return "FILLS"
    if "DP" in nombre:
        return "DP"
    raise ValueError(
        f"No se puede determinar la empresa del archivo '{os.path.basename(pdf_path)}'. "
        "El nombre debe contener 'Fills' o 'DP'."
    )

# ---------------------------------------------------------------------------
# Detección del tipo de PDF
# ---------------------------------------------------------------------------

def _es_zip(pdf_path: str) -> bool:
    """Devuelve True si el archivo es en realidad un ZIP (formato especial del sistema)."""
    return zipfile.is_zipfile(pdf_path)


def _tiene_texto_digital(pdf_path: str) -> bool:
    """
    Devuelve True si pdfplumber logra extraer texto real del PDF.
    Un PDF 'escaneado' (imagen pura) devuelve cadenas vacías o casi vacías.
    """
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                texto = page.extract_text() or ""
                if len(texto.strip()) > 50:   # umbral: al menos 50 chars reales
                    return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Estrategia 1 — ZIP con .txt internos
# ---------------------------------------------------------------------------

def _extraer_texto_zip(pdf_path: str) -> str:
    """
    Lee el ZIP y concatena todos los .txt en orden de número de página.
    El manifest.json indica qué archivo de texto corresponde a cada página.
    Si no hay manifest, simplemente ordena los .txt alfabéticamente.
    """
    texto_total = ""

    with zipfile.ZipFile(pdf_path, "r") as z:
        nombres = z.namelist()

        # Intentar leer el manifest para obtener el orden correcto
        if "manifest.json" in nombres:
            manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            paginas = sorted(manifest.get("pages", []), key=lambda p: p["page_number"])
            archivos_txt = []
            for pag in paginas:
                txt_path = pag.get("text", {}).get("path")
                if txt_path and txt_path in nombres:
                    archivos_txt.append(txt_path)
        else:
            # Fallback: todos los .txt ordenados alfabéticamente
            archivos_txt = sorted(n for n in nombres if n.lower().endswith(".txt"))

        for nombre in archivos_txt:
            contenido = z.read(nombre).decode("utf-8", errors="replace")
            texto_total += "\n" + contenido

    return texto_total


# ---------------------------------------------------------------------------
# Estrategia 2 — PDF digital (pdfplumber)
# ---------------------------------------------------------------------------

def _extraer_texto_pdfplumber(pdf_path: str) -> str:
    """Extrae texto de un PDF digital usando pdfplumber."""
    import pdfplumber
    texto_total = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            texto_total += "\n" + texto
    return texto_total


# ---------------------------------------------------------------------------
# Estrategia 3 — PDF escaneado (Tesseract OCR, código original)
# ---------------------------------------------------------------------------

def _extraer_texto_ocr(pdf_path: str) -> str:
    """
    Extrae texto de un PDF escaneado usando Tesseract OCR.
    Requiere que Tesseract y poppler estén instalados en el sistema.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path

        # Rutas para Windows — se ignoran en Linux/Mac donde están en el PATH
        tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        poppler_path  = r"C:\Users\Usuario\Release-25.12.0-0\poppler-25.12.0\Library\bin"

        if os.path.exists(tesseract_cmd):
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        kwargs = {}
        if os.path.exists(poppler_path):
            kwargs["poppler_path"] = poppler_path

        imagenes = convert_from_path(pdf_path, **kwargs)
        texto_total = ""
        for img in imagenes:
            texto = pytesseract.image_to_string(img, lang="spa")
            texto_total += "\n" + texto

        return texto_total

    except ImportError as e:
        raise RuntimeError(
            f"No se pudo usar OCR: {e}. "
            "Instalá pytesseract y pdf2image, o usá un PDF digital."
        )


# ---------------------------------------------------------------------------
# Función pública principal
# ---------------------------------------------------------------------------

TIPO_ZIP       = "zip"
TIPO_DIGITAL   = "digital"
TIPO_ESCANEADO = "escaneado"


def detectar_tipo_pdf(pdf_path: str) -> str:
    """
    Detecta el tipo de archivo PDF y devuelve una constante:
      - TIPO_ZIP       si es un ZIP disfrazado de PDF
      - TIPO_DIGITAL   si es un PDF con texto embebido
      - TIPO_ESCANEADO si es un PDF imagen (requiere OCR)
    """
    if _es_zip(pdf_path):
        return TIPO_ZIP
    if _tiene_texto_digital(pdf_path):
        return TIPO_DIGITAL
    return TIPO_ESCANEADO


def extraer_texto_pdf(pdf_path: str, verbose: bool = False) -> str:
    """
    Extrae todo el texto de un PDF usando la estrategia adecuada
    según el tipo de archivo detectado automáticamente.

    Parámetros
    ----------
    pdf_path : str
        Ruta al archivo (puede ser .pdf real, ZIP disfrazado, o imagen escaneada).
    verbose : bool
        Si es True, imprime el tipo detectado y la estrategia usada.

    Devuelve
    --------
    str
        Texto completo del documento, listo para ser procesado.
    """
    tipo = detectar_tipo_pdf(pdf_path)

    if verbose:
        nombres = {
            TIPO_ZIP:       "ZIP con .txt internos",
            TIPO_DIGITAL:   "PDF digital (pdfplumber)",
            TIPO_ESCANEADO: "PDF escaneado (OCR Tesseract)",
        }
        print(f"  📄 Tipo detectado: {nombres[tipo]}  →  {os.path.basename(pdf_path)}")

    if tipo == TIPO_ZIP:
        return _extraer_texto_zip(pdf_path)
    elif tipo == TIPO_DIGITAL:
        return _extraer_texto_pdfplumber(pdf_path)
    else:
        return _extraer_texto_ocr(pdf_path)