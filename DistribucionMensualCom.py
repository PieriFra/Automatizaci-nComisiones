import re
from collections import defaultdict
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4
from datetime import datetime
import os
import pandas as pd
from collections import defaultdict
from ComisionMensual import extraer_texto_pdf, normalizar_texto, extraer_planilla_y_fecha, extraer_total_y_comisiones  


# ----------------------------- ETAPA 1 — PROCESAR TEXTO PARA OBTENER DISTRIBUCIÓN MENSUAL ----------------------------
# 1️⃣ Extraer clientes_raw (incluye SUBTOTAL)
def extraer_clientes_raw(texto):
    clientes = []
    capturar = False

    for linea in texto.splitlines():
        linea = linea.strip()

        if linea == "CLIENTE":
            capturar = True
            continue

        # 🔴 corte definitivo al llegar al TOTAL general
        if linea == "TOTAL":
            break

        if linea == "MÉTODO DE PAGO":
            capturar = False
            continue

        if capturar and linea.isupper():
            clientes.append(linea)

    return clientes

# 2️⃣ Extraer importes
def limpiar_importe_ocr(linea):
    linea = linea.strip().replace("$", "")

    # Caso normal correcto
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})*,\d{2}", linea):
        return linea

    # Caso OCR con un dígito extra adelante (ej: 5479.766,81)
    if re.fullmatch(r"\d{4}\.\d{3},\d{2}", linea):
        return linea[1:]  # elimina primer dígito

    return None

def extraer_importes(texto):
    importes = []
    capturar = False

    for linea in texto.splitlines():
        linea = linea.strip()

        if linea == "IMPORTE":
            capturar = True
            continue

        if linea == "ESTADO DE PAGO":
            capturar = False   # 🔴 NO break
            continue

        if not capturar:
            continue

        limpio = limpiar_importe_ocr(linea)
        if not limpio:
            continue

        valor = float(
            limpio.replace(".", "").replace(",", ".")
        )

        importes.append(valor)

    return importes

# 3️⃣ Emparejar usando posiciones de SUBTOTAL (TU IDEA)
def totales_por_cliente(texto_norm, total_general):
    clientes_raw = extraer_clientes_raw(texto_norm)
    importes = extraer_importes(texto_norm)

    # 🔎 buscar dónde aparece el total general (con tolerancia)
    indice_total = None
    for i, imp in enumerate(importes):
        if abs(imp - total_general) < 0.01:
            indice_total = i
            break

    if indice_total is not None:
        # 🔴 quedarnos solo con lo anterior al TOTAL
        importes = importes[:indice_total]

    # Si no se encontró, asumir que importes ya está correcto

    if len(clientes_raw) != len(importes):
        raise ValueError(
            f"Clientes ({len(clientes_raw)}) e importes ({len(importes)}) no coinciden"
        )

    from collections import defaultdict
    totales = defaultdict(float)
    cliente_actual = None

    for i, item in enumerate(clientes_raw):
        if item != "SUBTOTAL":
            cliente_actual = item
        else:
            subtotal = importes[i]
            totales[cliente_actual] += subtotal

    return totales

## ----------------------------- ETAPA 2 — GENERAR PDF DE DISTRIBUCIÓN MENSUAL ----------------------------
def calcular_comisiones_vendedores(totales_clientes, cliente_vendedor):
    comisiones = defaultdict(float)

    for cliente, total in totales_clientes.items():
        vendedor = cliente_vendedor.get(cliente)

        if vendedor is None:
            raise ValueError(f"Cliente sin vendedor asignado: {cliente}")

        if vendedor == "FRAIRE":
            comisiones["FRAIRE"] += total * 0.10

        elif vendedor == "GIUSTA":
            comisiones["GIUSTA"] += total * 0.06
            comisiones["FRAIRE"] += total * 0.04

        else:
            raise ValueError(f"Vendedor desconocido: {vendedor}")

    return dict(comisiones)

def procesar_carpeta_planillas(carpeta_path, mapa_clientes_vendedores):

    resumen_planillas = []
    acumulado_vendedores = defaultdict(float)

    for archivo in os.listdir(carpeta_path):

        if not archivo.lower().endswith(".pdf"):
            continue

        if archivo == "Reporte_Comisiones.pdf":
            continue

        pdf_path = os.path.join(carpeta_path, archivo)

        print(f"Procesando: {archivo}")

        # 1️⃣ OCR + Normalización
        texto = extraer_texto_pdf(pdf_path)
        texto_norm = normalizar_texto(texto)

        # 2️⃣ Datos generales
        planilla, fecha = extraer_planilla_y_fecha(texto_norm)
        total, comisiones_total = extraer_total_y_comisiones(texto_norm)

        # 3️⃣ Totales por cliente
        totales_clientes = totales_por_cliente(texto_norm, total)

        # 4️⃣ Calcular comisiones por vendedor
        comisiones_vendedores = calcular_comisiones_vendedores(
            totales_clientes,
            mapa_clientes_vendedores
        )

        # 5️⃣ Acumular vendedores
        for vendedor, valor in comisiones_vendedores.items():
            acumulado_vendedores[vendedor] += valor

        # 6️⃣ Guardar fila resumen
        fila = {
            "Planilla": planilla,
            "Fecha": fecha,
            "Total": total,
            "Comisiones Planilla": comisiones_total,
        }

        # Agregar columnas dinámicas por vendedor
        for vendedor, valor in comisiones_vendedores.items():
            fila[f"Comisión {vendedor}"] = valor

        resumen_planillas.append(fila)

    # 📊 DataFrame final
    df = pd.DataFrame(resumen_planillas)

    return df, dict(acumulado_vendedores)

def generar_reporte_mensual_pdf(ruta_salida, df_resumen, acumulado_vendedores):

    doc = SimpleDocTemplate(ruta_salida, pagesize=A4)
    elementos = []
    estilos = getSampleStyleSheet()

    # -----------------------------
    # TÍTULO
    # -----------------------------
    elementos.append(Paragraph("<b>REPORTE MENSUAL DE COBRANZAS</b>", estilos["Title"]))
    elementos.append(Spacer(1, 0.3 * inch))

    fecha_gen = datetime.now().strftime("%d/%m/%Y")
    elementos.append(Paragraph(f"Fecha de generación: {fecha_gen}", estilos["Normal"]))
    elementos.append(Spacer(1, 0.3 * inch))

    # -----------------------------
    # TABLA PLANILLAS
    # -----------------------------
    data_planillas = [["Planilla", "Fecha", "Total Cobrado", "Comisiones"]]

    total_cobrado_mes = df_resumen["Total"].sum()
    total_comisiones_mes = df_resumen["Comisiones Planilla"].sum()

    for _, row in df_resumen.iterrows():
        data_planillas.append([
            row["Planilla"],
            row["Fecha"],
            f"${row['Total']:,.2f}",
            f"${row['Comisiones Planilla']:,.2f}",
        ])

    tabla_planillas = Table(data_planillas, repeatRows=1)
    tabla_planillas.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"),
    ]))

    elementos.append(tabla_planillas)
    elementos.append(Spacer(1, 0.5 * inch))

    # -----------------------------
    # TOTALES GENERALES
    # -----------------------------
    elementos.append(Paragraph("<b>TOTALES MENSUALES</b>", estilos["Heading2"]))
    elementos.append(Spacer(1, 0.2 * inch))

    elementos.append(Paragraph(
        f"Total cobrado del mes: ${total_cobrado_mes:,.2f}",
        estilos["Normal"]
    ))

    elementos.append(Paragraph(
        f"Total comisiones del mes: ${total_comisiones_mes:,.2f}",
        estilos["Normal"]
    ))

    elementos.append(Spacer(1, 0.5 * inch))

    # -----------------------------
    # DISTRIBUCIÓN VENDEDORES
    # -----------------------------
    elementos.append(Paragraph("<b>DISTRIBUCIÓN DE COMISIONES</b>", estilos["Heading2"]))
    elementos.append(Spacer(1, 0.2 * inch))

    data_vendedores = [["Vendedor", "Comisión Total"]]

    for vendedor, total in acumulado_vendedores.items():
        data_vendedores.append([
            vendedor,
            f"${total:,.2f}"
        ])

    tabla_vendedores = Table(data_vendedores, repeatRows=1)
    tabla_vendedores.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
    ]))

    elementos.append(tabla_vendedores)

    doc.build(elementos)