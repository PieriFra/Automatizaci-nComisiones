import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
from pdf2image import convert_from_path
POPPLER_PATH = r"C:\Users\Usuario\Release-25.12.0-0\poppler-25.12.0\Library\bin"
import re
import os
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from collections import defaultdict


# ---------------------------- ETAPA 1 — EXTRAER TEXTO DE PDF CON OCR ----------------------------
def extraer_texto_pdf(pdf_path):
    """
    Convierte un PDF en imágenes y extrae todo el texto vía OCR
    """
    imagenes = convert_from_path(pdf_path, poppler_path=POPPLER_PATH)

    texto_total = ""
    for img in imagenes:
        texto = pytesseract.image_to_string(img, lang="spa")
        texto_total += "\n" + texto

    return texto_total

# 🧩 PASO 6 — NORMALIZAR TEXTO OCR (OBLIGATORIO)
def normalizar_texto(texto):
    texto = texto.upper()
    texto = texto.replace(" ", " ")  # espacios raros
    texto = texto.replace("\n\n", "\n")
    return texto

# 🧩 PASO 8 — EXTRAER LOS VALORES CLAVE
def extraer_total_y_comisiones(texto):
    # Extraer todos los importes en orden de aparición
    valores = re.findall(r"\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})", texto)

    numeros = []
    for v in valores:
        try:
            numeros.append(float(v.replace(".", "").replace(",", ".")))
        except:
            pass

    if len(numeros) < 2:
        return 0.0, 0.0

    # El TOTAL es el número más grande
    total = max(numeros)

    # La comisión es el número que aparece inmediatamente después del TOTAL
    idx = numeros.index(total)

    if idx + 1 < len(numeros):
        comisiones = numeros[idx + 1]
    else:
        comisiones = 0.0

    return total, comisiones

def extraer_planilla_y_fecha(texto):
    lineas = texto.upper().splitlines()

    linea_planilla = None
    fecha = None

    for i, linea in enumerate(lineas):
        linea = linea.strip()

        # Capturar la línea completa de PLANILLA
        if linea.startswith("PLANILLA"):
            linea_planilla = linea

        # FECHA DE PUBLICACIÓN -> la línea siguiente tiene la fecha
        if linea.startswith("FECHA DE PUBLICACIÓN") and i + 1 < len(lineas):
            posible_fecha = lineas[i + 1].strip()
            m = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", posible_fecha)
            if m:
                fecha = m.group(0)

    return linea_planilla, fecha

# ---------------------------- ETAPA 2 — GENERACIÓN DE RESUMEN PDF ----------------------------
# Función: procesar UNA planilla
def procesar_planilla(pdf_path):
    texto = extraer_texto_pdf(pdf_path)
    texto_norm = normalizar_texto(texto)

    total, comisiones = extraer_total_y_comisiones(texto_norm)
    planilla, fecha = extraer_planilla_y_fecha(texto_norm)

    return {
        "Fecha": fecha if fecha else "N/D",
        "Planilla": planilla if planilla else "N/D",
        "Total cobrado": total,
        "Comisión": comisiones
    }

# Función: procesar TODA una carpeta
def procesar_carpeta_planillas(carpeta):
    resultados = []

    for archivo in os.listdir(carpeta):
        if archivo.lower().endswith(".pdf"):
            ruta_pdf = os.path.join(carpeta, archivo)
            print(f"Procesando: {archivo}")
            datos = procesar_planilla(ruta_pdf)
            resultados.append(datos)

    return resultados

# Mostrar resumen en forma de tabla
def generar_resumen(carpeta):
    datos = procesar_carpeta_planillas(carpeta)
    df = pd.DataFrame(datos)

    total_a_retirar = df["Comisión"].sum()

    return df, total_a_retirar

def generar_pdf_resumen(df, total_retirar, output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    elementos = []

    # Título
    titulo = Paragraph(
        "<b>RESUMEN DE PLANILLAS DE COBRANZA</b>",
        styles["Title"]
    )
    elementos.append(titulo)
    elementos.append(Spacer(1, 20))

    # Tabla
    data = [["Fecha", "Planilla", "Total cobrado", "Comisión"]]

    for _, row in df.iterrows():
        data.append([
            row["Fecha"],
            row["Planilla"],
            f"$ {row['Total cobrado']:,.2f}",
            f"$ {row['Comisión']:,.2f}"
        ])

    tabla = Table(data, colWidths=[90, 150, 120, 120])
    tabla.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0,0), (-1,0), 10),
        ("TOPPADDING", (0,0), (-1,0), 10),
    ]))

    elementos.append(tabla)
    elementos.append(Spacer(1, 30))

    # Línea separadora
    elementos.append(Table(
        [[""]],
        colWidths=[480],
        style=[("LINEBELOW", (0,0), (-1,-1), 1, colors.black)]
    ))
    elementos.append(Spacer(1, 20))

    # Total a retirar
    total_paragraph = Paragraph(
        f"<b>TOTAL A RETIRAR:</b> &nbsp;&nbsp;&nbsp; <b>$ {total_retirar:,.2f}</b>",
        styles["Heading2"]
    )
    elementos.append(total_paragraph)

    doc.build(elementos)