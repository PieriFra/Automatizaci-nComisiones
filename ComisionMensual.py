"""
ComisionMensual.py
==================
Procesa una carpeta de planillas de cobranza y genera un PDF resumen
con el total cobrado y las comisiones de cada planilla.

Compatible con todos los formatos de planilla:
  - ZIP disfrazado de .pdf (nuevo sistema)
  - PDF digital normal
  - PDF escaneado (OCR Tesseract)
"""

import os
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

from pdf_reader import extraer_texto_pdf
from planilla_parser import parsear_planilla


# ---------------------------------------------------------------------------
# Procesar una sola planilla
# ---------------------------------------------------------------------------

def procesar_planilla(pdf_path: str, verbose: bool = False) -> dict:
    """
    Extrae los datos clave de una planilla de cobranza.

    Devuelve un dict con:
        Fecha, Planilla, Total cobrado, Comisión
    """
    texto = extraer_texto_pdf(pdf_path, verbose=verbose)
    datos = parsear_planilla(texto)

    return {
        "Fecha":         datos["fecha"],
        "Planilla":      datos["planilla"],
        "Total cobrado": datos["total"],
        "Comisión":      datos["comisiones"],
    }


# ---------------------------------------------------------------------------
# Procesar una carpeta completa
# ---------------------------------------------------------------------------

def procesar_carpeta_planillas(carpeta: str, verbose: bool = True) -> tuple[pd.DataFrame, float]:
    """
    Procesa todos los PDFs de una carpeta y devuelve:
        - DataFrame con el resumen por planilla
        - Total acumulado de comisiones
    """
    resultados = []

    for archivo in sorted(os.listdir(carpeta)):
        if not archivo.lower().endswith(".pdf"):
            continue

        # Evitar reprocesar PDFs generados por este mismo script
        archivo_low = archivo.lower()
        if "reporte comisiones" in archivo_low or "distribucion comisiones" in archivo_low:
            continue

        ruta_pdf = os.path.join(carpeta, archivo)
        if verbose:
            print(f"Procesando: {archivo}")

        try:
            datos = procesar_planilla(ruta_pdf, verbose=verbose)
            resultados.append(datos)
        except Exception as e:
            print(f"  ⚠️  Error al procesar {archivo}: {e}")

    df = pd.DataFrame(resultados)
    total_a_retirar = df["Comisión"].sum() if not df.empty else 0.0

    return df, total_a_retirar


def generar_resumen(carpeta: str) -> tuple[pd.DataFrame, float]:
    """Alias de procesar_carpeta_planillas para compatibilidad."""
    return procesar_carpeta_planillas(carpeta)


# ---------------------------------------------------------------------------
# Generar PDF resumen
# ---------------------------------------------------------------------------

def generar_pdf_resumen(df: pd.DataFrame, total_retirar: float, output_path: str):
    """Genera un PDF con la tabla de planillas y el total a retirar."""

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=40, leftMargin=40,
        topMargin=40,   bottomMargin=40,
    )

    styles   = getSampleStyleSheet()
    elementos = []

    # Título
    elementos.append(Paragraph("<b>RESUMEN DE PLANILLAS DE COBRANZA</b>", styles["Title"]))
    elementos.append(Spacer(1, 20))

    # Tabla
    data = [["Fecha", "Planilla", "Total cobrado", "Comisión"]]
    for _, row in df.iterrows():
        data.append([
            row["Fecha"],
            row["Planilla"],
            f"$ {row['Total cobrado']:,.2f}",
            f"$ {row['Comisión']:,.2f}",
        ])

    tabla = Table(data, colWidths=[90, 150, 120, 120])
    tabla.setStyle(TableStyle([
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1,  0), colors.lightgrey),
        ("ALIGN",      (2, 1), (-1, -1), "RIGHT"),
        ("FONTNAME",   (0, 0), (-1,  0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
        ("TOPPADDING",    (0, 0), (-1, 0), 10),
    ]))

    elementos.append(tabla)
    elementos.append(Spacer(1, 30))

    # Línea separadora
    elementos.append(Table(
        [[""]],
        colWidths=[480],
        style=[("LINEBELOW", (0, 0), (-1, -1), 1, colors.black)],
    ))
    elementos.append(Spacer(1, 20))

    # Total a retirar
    elementos.append(Paragraph(
        f"<b>TOTAL A RETIRAR:</b> &nbsp;&nbsp;&nbsp; <b>$ {total_retirar:,.2f}</b>",
        styles["Heading2"],
    ))

    doc.build(elementos)


# ---------------------------------------------------------------------------
# Compatibilidad hacia atrás (funciones que DistribucionMensualCom importaba)
# ---------------------------------------------------------------------------

def extraer_texto_pdf_compat(pdf_path: str) -> str:
    """Wrapper de compatibilidad — usa la nueva lógica multi-formato."""
    return extraer_texto_pdf(pdf_path)


def normalizar_texto(texto: str) -> str:
    """Normalización básica (ya no es crítica pero se conserva para compatibilidad)."""
    return texto.upper().replace("\n\n", "\n")


def extraer_planilla_y_fecha(texto: str) -> tuple[str, str]:
    """Wrapper de compatibilidad."""
    datos = parsear_planilla(texto)
    return datos["planilla"], datos["fecha"]


def extraer_total_y_comisiones(texto: str) -> tuple[float, float]:
    """Wrapper de compatibilidad."""
    datos = parsear_planilla(texto)
    return datos["total"], datos["comisiones"]