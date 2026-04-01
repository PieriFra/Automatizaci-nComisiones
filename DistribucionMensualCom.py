import re
import unicodedata
from collections import defaultdict
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4
from datetime import datetime
import os
import pandas as pd
from clientes_vendedor import MAPA_CLIENTES_VENDEDORES
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
def totales_por_cliente(texto_norm, total_general, *, return_audit: bool = False):
    """
    Extrae totales por cliente usando:
    - match del nombre del cliente contra `MAPA_CLIENTES_VENDEDORES`
    - lectura de montos desde líneas que contienen `SUBTOTAL`

    Nota: el OCR suele venir con el encabezado `CLIENTE ... IMPORTE ...` en la misma línea,
    y las filas del cliente mezclan nombre + columnas. Por eso no dependemos de
    igualdad exacta de líneas ni de la alineación por índice.
    """

    def _normalizar_para_match(s: str) -> str:
        s = (s or "").upper()
        s = s.replace("�", "").replace("?", "")
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = re.sub(r"\s+", " ", s).strip()
        return s

    # Regex de importes tolerante a OCR:
    # - acepta espacios extra (ej: "$77.537, 44")
    # - conserva formato miles/decimales esperado
    rx_importe = re.compile(r"\$?\s*(\d{1,3}(?:\.\d{3})*,\s*\d{2})")

    # Precomputar claves normalizadas para identificar el cliente dentro de la fila OCR
    mapa_normalizado = {}
    for nombre in MAPA_CLIENTES_VENDEDORES.keys():
        mapa_normalizado[_normalizar_para_match(nombre)] = nombre
    claves_norm = sorted(mapa_normalizado.keys(), key=len, reverse=True)

    totales = defaultdict(float)
    cliente_actual = None
    audit = {
        "subtotales_sin_cliente": [],  # list[tuple[linea, monto]]
    }

    lineas = [ln.strip() for ln in texto_norm.splitlines()]
    capturar = False
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        if not linea:
            i += 1
            continue

        if not capturar:
            # En OCR suele aparecer como: "CLIENTE PAGO ... IMPORTE ... ESTADO DE PAGO"
            if (("CLIENTE" in linea) and ("IMPORTE" in linea)) or linea.startswith("CLIENTE"):
                capturar = True
            i += 1
            continue

        # Corte al llegar al total general
        if linea.startswith("TOTAL"):
            break

        # Registrar SUBTOTAL
        if "SUBTOTAL" in linea:
            m = rx_importe.search(linea)
            # Si OCR separó "SUBTOTAL" y el monto en la/s línea/s siguiente/s, buscar lookahead corto.
            if not m:
                j = i + 1
                while j < len(lineas) and j <= i + 6:
                    prox = lineas[j]
                    if not prox:
                        j += 1
                        continue
                    if prox.startswith("TOTAL") or prox.startswith("COMISIONES"):
                        break
                    m = rx_importe.search(prox)
                    if m:
                        break
                    j += 1
            # Caso OCR frecuente: aparece "SUBTOTAL" y recién después de líneas TOTAL/COMISIONES
            # queda el importe suelto del subtotal. Tomamos el primer importe cercano que no sea el TOTAL general.
            if not m:
                j = i + 1
                while j < len(lineas) and j <= i + 14:
                    prox = lineas[j]
                    if not prox:
                        j += 1
                        continue
                    m2 = rx_importe.search(prox)
                    if not m2:
                        j += 1
                        continue
                    bruto2 = m2.group(1).replace(" ", "")
                    valor2 = float(bruto2.replace(".", "").replace(",", "."))
                    # Evitar tomar TOTAL general por error de OCR
                    if abs(valor2 - total_general) < 0.01:
                        j += 1
                        continue
                    m = m2
                    break
            if not m:
                i += 1
                continue

            bruto = m.group(1).replace(" ", "")
            valor = float(bruto.replace(".", "").replace(",", "."))
            if cliente_actual is None:
                audit["subtotales_sin_cliente"].append((linea, valor))
                i += 1
                continue
            totales[cliente_actual] += valor
            i += 1
            continue

        # Ignorar líneas que suelen ser encabezados
        if "MÉTODO" in linea or "ESTADO DE PAGO" in linea:
            i += 1
            continue

        # Actualizar el cliente actual si la fila contiene su nombre
        linea_norm = _normalizar_para_match(linea)
        for clave_norm in claves_norm:
            if clave_norm and clave_norm in linea_norm:
                cliente_actual = mapa_normalizado[clave_norm]
                break
        i += 1

    if return_audit:
        return dict(totales), audit
    return dict(totales)

## ----------------------------- ETAPA 2 — GENERAR PDF DE DISTRIBUCIÓN MENSUAL ----------------------------
def calcular_comisiones_vendedores(totales_clientes, cliente_vendedor):
    comisiones = defaultdict(float)

    for cliente, total in totales_clientes.items():
        vendedor = cliente_vendedor.get(cliente)

        if vendedor is None:
            raise ValueError(f"Cliente sin vendedor asignado: {cliente}")

        if vendedor == "FRAIRE":
            # En las planillas, la línea "COMISIONES" equivale al 8% del TOTAL.
            comisiones["FRAIRE"] += total * 0.08

        elif vendedor == "GIUSTA":
            # Mantener la proporción original (6/10 para GIUSTA y 4/10 para FRAIRE)
            # pero sobre una base total 8%.
            comisiones["GIUSTA"] += total * 0.05
            comisiones["FRAIRE"] += total * 0.03

        elif vendedor == "ALARCÓN":
            comisiones["ALARCÓN"] += total * 0.04
            comisiones["FRAIRE"] += total * 0.04

        else:
            raise ValueError(f"Vendedor desconocido: {vendedor}")

    return dict(comisiones)

def procesar_carpeta_planillas(carpeta_path, mapa_clientes_vendedores):

    resumen_planillas = []
    acumulado_vendedores = defaultdict(float)
    # Tolerancias (por redondeos y OCR)
    tolerancia_pesos = 2.0

    for archivo in os.listdir(carpeta_path):

        if not archivo.lower().endswith(".pdf"):
            continue
        # Evitar re-procesar los PDFs generados por este mismo script.
        # Los nombres suelen variar (con espacios y/o mes), así que usamos "contains" con normalización.
        archivo_norm = unicodedata.normalize("NFKD", archivo).encode("ascii", "ignore").decode("ascii").lower()
        if ("reporte comisiones" in archivo_norm) or ("distribucion comisiones" in archivo_norm):
            continue

        pdf_path = os.path.join(carpeta_path, archivo)

        print(f"Procesando: {archivo}")

        # 1️⃣ OCR + Normalización
        texto = extraer_texto_pdf(pdf_path)
        texto_norm = normalizar_texto(texto)
        # print(texto_norm)

        # 2️⃣ Datos generales
        planilla, fecha = extraer_planilla_y_fecha(texto_norm)
        total, comisiones_total = extraer_total_y_comisiones(texto_norm)

        # 3️⃣ Totales por cliente (+ auditoría de subtotales sin asignar)
        totales_clientes, audit = totales_por_cliente(texto_norm, total, return_audit=True)

        # 4️⃣ Calcular comisiones por vendedor
        comisiones_vendedores = calcular_comisiones_vendedores(
            totales_clientes,
            mapa_clientes_vendedores
        )

        # ✅ Chequeos de consistencia (por planilla)
        suma_totales_clientes = sum(totales_clientes.values())
        diff_total = suma_totales_clientes - total
        if abs(diff_total) > tolerancia_pesos:
            missing_sum = sum(v for _, v in audit["subtotales_sin_cliente"])
            print(
                f"⚠️ Aviso: la suma de SUBTOTALES por cliente no coincide con TOTAL en '{archivo}'. "
                f"Diferencia: {diff_total:,.2f}. "
                f"SUBTOTAL sin cliente asignado: {missing_sum:,.2f}."
            )

        suma_distribuida = sum(comisiones_vendedores.values())
        diff_com = suma_distribuida - comisiones_total
        if abs(diff_com) > tolerancia_pesos:
            missing_sum = sum(v for _, v in audit["subtotales_sin_cliente"])
            print(
                f"⚠️ Aviso: la suma distribuida por vendedor no coincide con COMISIONES en '{archivo}'. "
                f"Diferencia: {diff_com:,.2f}. "
                f"Esto suele pasar si hay clientes/subtotales que no matchean el diccionario. "
                f"SUBTOTAL sin cliente asignado: {missing_sum:,.2f}."
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

    # ✅ Chequeo final: suma de comisiones por planilla vs suma distribuida por vendedores
    if not df.empty and "Comisiones Planilla" in df.columns:
        total_comisiones_planillas = float(df["Comisiones Planilla"].sum())
        total_distribuido = float(sum(acumulado_vendedores.values()))
        diff_final = total_distribuido - total_comisiones_planillas
        if abs(diff_final) > tolerancia_pesos:
            raise ValueError(
                f"Error de consistencia: total distribuido por vendedores ({total_distribuido:,.2f}) "
                f"no coincide con total COMISIONES de planillas ({total_comisiones_planillas:,.2f}). "
                f"Diferencia: {diff_final:,.2f}."
            )

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

# Nueva función para Reporte de Comisiones
def generar_reporte_comisiones_pdf(ruta_salida, df_resumen):

    # --- LIMPIEZA DEL DATAFRAME ---
    df_resumen = df_resumen.dropna(subset=["Planilla"])  # Elimina filas con NaN en Planilla
    df_resumen = df_resumen.drop_duplicates(subset=["Planilla", "Fecha"])  # Elimina duplicados exactos
    df_resumen = df_resumen.reset_index(drop=True)

    # Después de la limpieza del DataFrame, antes del título
    fecha_ref = pd.to_datetime(df_resumen["Fecha"], dayfirst=True).iloc[0]
    meses = {
        1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
        5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
        9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"
    }
    mes_anio = f"{meses[fecha_ref.month]} {fecha_ref.year}"

    doc = SimpleDocTemplate(ruta_salida, pagesize=A4)
    elementos = []
    estilos = getSampleStyleSheet()

    # -----------------------------
    # TÍTULO
    # -----------------------------
    elementos.append(Paragraph(f"<b>REPORTE DE COMISIONES {mes_anio}</b>", estilos["Title"]))
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

    doc.build(elementos)

# Nueva función para Distribución de Comisiones
def generar_distribucion_comisiones_pdf(ruta_salida, acumulado_vendedores, df_resumen):

    # Después de la limpieza del DataFrame, antes del título
    fecha_ref = pd.to_datetime(df_resumen["Fecha"], dayfirst=True).iloc[0]
    meses = {
        1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
        5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
        9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"
    }
    mes_anio = f"{meses[fecha_ref.month]} {fecha_ref.year}"

    doc = SimpleDocTemplate(ruta_salida, pagesize=A4)
    elementos = []
    estilos = getSampleStyleSheet()

    # -----------------------------
    # TÍTULO
    # -----------------------------
    elementos.append(Paragraph(f"<b>DISTRIBUCIÓN DE COMISIONES {mes_anio} </b>", estilos["Title"]))
    elementos.append(Spacer(1, 0.3 * inch))

    fecha_gen = datetime.now().strftime("%d/%m/%Y")
    elementos.append(Paragraph(f"Fecha de generación: {fecha_gen}", estilos["Normal"]))
    elementos.append(Spacer(1, 0.3 * inch))

    # -----------------------------
    # DISTRIBUCIÓN VENDEDORES
    # -----------------------------
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