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
    return zipfile.is_zipfile(pdf_path)


def _tiene_texto_digital(pdf_path: str) -> bool:
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                texto = page.extract_text() or ""
                if len(texto.strip()) > 50:
                    return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Estrategia 1 — ZIP con .txt internos
# ---------------------------------------------------------------------------

def _extraer_texto_zip(pdf_path: str) -> str:
    texto_total = ""
    with zipfile.ZipFile(pdf_path, "r") as z:
        nombres = z.namelist()
        if "manifest.json" in nombres:
            manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            paginas = sorted(manifest.get("pages", []), key=lambda p: p["page_number"])
            archivos_txt = []
            for pag in paginas:
                txt_path = pag.get("text", {}).get("path")
                if txt_path and txt_path in nombres:
                    archivos_txt.append(txt_path)
        else:
            archivos_txt = sorted(n for n in nombres if n.lower().endswith(".txt"))

        for nombre in archivos_txt:
            contenido = z.read(nombre).decode("utf-8", errors="replace")
            texto_total += "\n" + contenido

    return texto_total


# ---------------------------------------------------------------------------
# Estrategia 2 — PDF digital (pdfplumber)
# ---------------------------------------------------------------------------

def _extraer_texto_pdfplumber(pdf_path: str) -> str:
    import pdfplumber
    texto_total = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            texto_total += "\n" + texto
    return texto_total


# ---------------------------------------------------------------------------
# Estrategia 3 — PDF escaneado (Tesseract OCR)
# ---------------------------------------------------------------------------

def _extraer_texto_ocr(pdf_path: str) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_path

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
    if _es_zip(pdf_path):
        return TIPO_ZIP
    if _tiene_texto_digital(pdf_path):
        return TIPO_DIGITAL
    return TIPO_ESCANEADO


def extraer_texto_pdf(pdf_path: str, verbose: bool = False) -> str:
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


# ---------------------------------------------------------------------------
# Detección de tipo de informe desde el nombre del archivo
# ---------------------------------------------------------------------------

def detectar_tipo_informe(pdf_path: str) -> int:
    """
    Detecta el tipo de informe según el número entre paréntesis en el nombre.
    Ej: 'Planilla N° 88 DP (1).pdf' → 1
        'Planilla N° 13 Fills (2).pdf' → 2

    Lanza ValueError si no puede determinarlo.
    """
    nombre = os.path.basename(pdf_path)
    m = re.search(r'\((\d+)\)', nombre)
    if m:
        return int(m.group(1))
    raise ValueError(
        f"No se puede determinar el tipo del archivo '{nombre}'. "
        "El nombre debe contener (1) o (2)."
    )