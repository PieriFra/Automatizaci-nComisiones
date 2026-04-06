"""
DistribucionMensualCom.py
=========================
Procesa una carpeta de planillas de cobranza, calcula la distribución
de comisiones por vendedor y genera los PDFs de reporte.

Compatible con todos los formatos de planilla:
  - ZIP disfrazado de .pdf (nuevo sistema)
  - PDF digital normal
  - PDF escaneado (OCR Tesseract)

Empresas soportadas: DP (Di Pascuale), Fills.
La empresa se detecta automáticamente desde el nombre del archivo PDF.
"""

import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime

import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4

from clientes_vendedor import MAPA_CLIENTES_DP, MAPA_CLIENTES_FILLS, REGLAS_COMISION
from pdf_reader import extraer_texto_pdf, detectar_empresa
from planilla_parser import parsear_planilla, _normalizar

# ---------------------------------------------------------------------------
# Selección de mapa de clientes según empresa
# ---------------------------------------------------------------------------
 
MAPAS_POR_EMPRESA = {
    "DP":    MAPA_CLIENTES_DP,
    "FILLS": MAPA_CLIENTES_FILLS,
}

# ---------------------------------------------------------------------------
# Helpers de normalización
# ---------------------------------------------------------------------------

def _mapa_normalizado(mapa: dict) -> tuple[dict, list]:
    """
    Devuelve (mapa_norm, claves_norm) donde las claves están normalizadas
    (sin acentos, mayúsculas, espacios colapsados), ordenadas de mayor a
    menor longitud para que el match más específico gane primero.
    """
    m = {_normalizar(k): k for k in mapa}
    claves = sorted(m.keys(), key=len, reverse=True)
    return m, claves


def _match_cliente(nombre_raw: str, mapa_norm: dict, claves_norm: list):
    """
    Dado el nombre de un cliente tal como aparece en el PDF (puede tener
    acentos distintos, capitalización diferente, etc.), devuelve la clave
    original del diccionario MAPA_CLIENTES_VENDEDORES, o None si no se encuentra.
    """
    nombre_up = _normalizar(nombre_raw)
    for clave in claves_norm:
        if clave in nombre_up:
            return mapa_norm[clave]
    return None


# ---------------------------------------------------------------------------
# Cálculo de comisiones por vendedor
# ---------------------------------------------------------------------------

def calcular_comisiones_vendedores(
    subtotales: dict[str, float],
    cliente_vendedor: dict,
    empresa: str,
) -> dict[str, float]:
    """
    Dado un dict {nombre_cliente_raw: monto_subtotal}, calcula las
    comisiones de cada vendedor según las reglas de negocio.

    Reglas DP:
        FRAIRE   → 8% del subtotal
        GIUSTA   → 5% para GIUSTA + 3% para FRAIRE
        ALARCÓN  → 4% para ALARCÓN + 4% para FRAIRE
    
    Reglas Fills:
        FRAIRE   → 6% del subtotal
        GIUSTA   → 4% para GIUSTA + 2% para FRAIRE
        ALARCÓN  → 3% para ALARCÓN + 3% para FRAIRE
    """
    reglas = REGLAS_COMISION[empresa]
    mapa_norm, claves_norm = _mapa_normalizado(cliente_vendedor)
    comisiones = defaultdict(float)

    for nombre_raw, total in subtotales.items():
        clave_original = _match_cliente(nombre_raw, mapa_norm, claves_norm)

        if clave_original is None:
            raise ValueError(
                f"Cliente sin vendedor asignado: '{nombre_raw}' (empresa: {empresa}) \n"
                "Agregalo al diccionario MAPA_CLIENTES_VENDEDORES en clientes_vendedor.py"
            )

        vendedor = cliente_vendedor[clave_original]

        # Normalizar vendedor para lookup en reglas (sin acentos)
        vendedor_norm = _normalizar(vendedor)
        regla = reglas.get(vendedor_norm)
 
        if regla is None:
            raise ValueError(
                f"No hay regla de comisión para el vendedor '{vendedor}' "
                f"en la empresa '{empresa}'. Revisá REGLAS_COMISION en clientes_vendedor.py"
            )
 
        for beneficiario, porcentaje in regla.items():
            comisiones[beneficiario] += total * porcentaje
 
    return dict(comisiones)


# ---------------------------------------------------------------------------
# Procesamiento de carpeta
# ---------------------------------------------------------------------------

def procesar_carpeta_planillas(
    carpeta_path: str,
    mapa_clientes_vendedores: dict,
    verbose: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """
    Procesa todos los PDFs de la carpeta, agrupando por empresa.
    Devuelve:
        - df_resumen           : DataFrame con una fila por planilla
                                 (incluye columna 'Empresa')
        - acumulado_vendedores : dict { empresa: { vendedor: total } }
    """
    TOLERANCIA = 2.0   # diferencia máxima aceptable por redondeos

    resumen_planillas    = []
     # { empresa: { vendedor: total_acumulado } }
    acumulado_por_empresa: dict[str, dict] = defaultdict(lambda: defaultdict(float))

    for archivo in sorted(os.listdir(carpeta_path)):
        if not archivo.lower().endswith(".pdf"):
            continue

        # Evitar reprocesar PDFs generados por este script
        archivo_low = archivo.lower()
        if "reporte comisiones" in archivo_low or "distribucion comisiones" in archivo_low:
            continue

        pdf_path = os.path.join(carpeta_path, archivo)

        if verbose:
            print(f"\nProcesando: {archivo}")

        try:
            # 1. Detectar empresa
            empresa = detectar_empresa(pdf_path)
 
            # 2. Extraer texto
            texto = extraer_texto_pdf(pdf_path, verbose=verbose)
 
            # 3. Parsear
            datos = parsear_planilla(texto)
            planilla    = datos["planilla"]
            fecha       = datos["fecha"]
            total       = datos["total"]
            comis_total = datos["comisiones"]
            subtotales  = datos["subtotales"]
 
            # 4. Seleccionar mapa de clientes según empresa
            mapa_empresa = MAPAS_POR_EMPRESA[empresa]
 
            # 5. Calcular comisiones
            comisiones_vendedores = calcular_comisiones_vendedores(
                subtotales, mapa_empresa, empresa
            )
 
            # 6. Chequeos de consistencia
            suma_sub = sum(subtotales.values())
            if abs(suma_sub - total) > TOLERANCIA:
                print(
                    f"  ⚠️  Suma de subtotales ({suma_sub:,.2f}) "
                    f"≠ TOTAL ({total:,.2f})  |  diff={suma_sub - total:+.2f}"
                )
 
            suma_dist = sum(comisiones_vendedores.values())
            if abs(suma_dist - comis_total) > TOLERANCIA:
                print(
                    f"  ⚠️  Comisiones distribuidas ({suma_dist:,.2f}) "
                    f"≠ Comisiones planilla ({comis_total:,.2f})  |  diff={suma_dist - comis_total:+.2f}"
                )
 
            # 7. Acumular por empresa
            for vendedor, valor in comisiones_vendedores.items():
                acumulado_por_empresa[empresa][vendedor] += valor
 
            # 8. Guardar fila resumen
            fila = {
                "Empresa":             empresa,
                "Planilla":            planilla,
                "Fecha":               fecha,
                "Total":               total,
                "Comisiones Planilla": comis_total,
            }
            for vendedor, valor in comisiones_vendedores.items():
                fila[f"Comision {vendedor}"] = valor
 
            resumen_planillas.append(fila)
 
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ❌  Error al procesar {archivo}: {e}")
 
    df = pd.DataFrame(resumen_planillas)
 
    # Convertir acumulado a dict normal
    acumulado = {emp: dict(vends) for emp, vends in acumulado_por_empresa.items()}
 
    return df, acumulado

# ---------------------------------------------------------------------------
# Helpers para reportes PDF
# ---------------------------------------------------------------------------
 
_MESES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
    5: "MAYO",  6: "JUNIO",   7: "JULIO", 8: "AGOSTO",
    9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
}
 
_ESTILO_TABLA = [
    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
    ("GRID",       (0, 0), (-1,-1), 0.5, colors.grey),
    ("ALIGN",      (2, 1), (-1,-1), "RIGHT"),
    ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ("TOPPADDING",    (0, 0), (-1, 0), 8),
]
 
_ESTILO_VENDEDORES = [
    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
    ("GRID",       (0, 0), (-1,-1), 0.5, colors.grey),
    ("ALIGN",      (1, 1), (-1,-1), "RIGHT"),
    ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ("TOPPADDING",    (0, 0), (-1, 0), 8),
]
 
 
def _mes_anio(df_resumen: pd.DataFrame) -> str:
    fecha_ref = pd.to_datetime(df_resumen["Fecha"], dayfirst=True).iloc[0]
    return f"{_MESES[fecha_ref.month]} {fecha_ref.year}"
 
 
def _tabla_planillas(df_empresa: pd.DataFrame) -> Table:
    data = [["Planilla", "Fecha", "Total Cobrado", "Comisiones"]]
    for _, row in df_empresa.iterrows():
        data.append([
            row["Planilla"],
            row["Fecha"],
            f"${row['Total']:,.2f}",
            f"${row['Comisiones Planilla']:,.2f}",
        ])
    tabla = Table(data, repeatRows=1)
    tabla.setStyle(TableStyle(_ESTILO_TABLA))
    return tabla
 
 
def _tabla_vendedores(acumulado_empresa: dict) -> Table:
    data = [["Vendedor", "Comisión Total"]]
    for vendedor, total in sorted(acumulado_empresa.items()):
        data.append([vendedor, f"${total:,.2f}"])
    tabla = Table(data, repeatRows=1)
    tabla.setStyle(TableStyle(_ESTILO_VENDEDORES))
    return tabla
 
 
# ---------------------------------------------------------------------------
# Generación de PDFs
# ---------------------------------------------------------------------------
 
def generar_reporte_comisiones_pdf(ruta_salida: str, df_resumen: pd.DataFrame):
    """
    PDF de comisiones con una sección por empresa.
    """
    df = df_resumen.dropna(subset=["Planilla"]).drop_duplicates(
        subset=["Planilla", "Fecha", "Empresa"]
    ).reset_index(drop=True)
 
    estilos  = getSampleStyleSheet()
    doc      = SimpleDocTemplate(ruta_salida, pagesize=A4)
    elems    = []
    mes_anio = _mes_anio(df)
 
    elems.append(Paragraph(f"<b>REPORTE DE COMISIONES {mes_anio}</b>", estilos["Title"]))
    elems.append(Spacer(1, 0.2 * inch))
    elems.append(Paragraph(f"Fecha de generación: {datetime.now():%d/%m/%Y}", estilos["Normal"]))
    elems.append(Spacer(1, 0.3 * inch))
 
    for empresa in sorted(df["Empresa"].unique()):
        df_emp = df[df["Empresa"] == empresa]
 
        elems.append(Paragraph(f"<b>Empresa: {empresa}</b>", estilos["Heading2"]))
        elems.append(Spacer(1, 0.15 * inch))
        elems.append(_tabla_planillas(df_emp))
        elems.append(Spacer(1, 0.15 * inch))
 
        total_cobrado   = df_emp["Total"].sum()
        total_comisiones = df_emp["Comisiones Planilla"].sum()
        elems.append(Paragraph(f"Total cobrado: <b>${total_cobrado:,.2f}</b>", estilos["Normal"]))
        elems.append(Paragraph(f"Total comisiones: <b>${total_comisiones:,.2f}</b>", estilos["Normal"]))
        elems.append(Spacer(1, 0.4 * inch))
 
    doc.build(elems)
 
 
def generar_distribucion_comisiones_pdf(
    ruta_salida: str,
    acumulado_vendedores: dict,
    df_resumen: pd.DataFrame,
):
    """
    PDF de distribución con una sección por empresa.
    acumulado_vendedores: { empresa: { vendedor: total } }
    """
    estilos  = getSampleStyleSheet()
    doc      = SimpleDocTemplate(ruta_salida, pagesize=A4)
    elems    = []
    mes_anio = _mes_anio(df_resumen)
 
    elems.append(Paragraph(f"<b>DISTRIBUCIÓN DE COMISIONES {mes_anio}</b>", estilos["Title"]))
    elems.append(Spacer(1, 0.2 * inch))
    elems.append(Paragraph(f"Fecha de generación: {datetime.now():%d/%m/%Y}", estilos["Normal"]))
    elems.append(Spacer(1, 0.3 * inch))
 
    for empresa in sorted(acumulado_vendedores.keys()):
        acumulado_emp = acumulado_vendedores[empresa]
 
        elems.append(Paragraph(f"<b>Empresa: {empresa}</b>", estilos["Heading2"]))
        elems.append(Spacer(1, 0.15 * inch))
        elems.append(_tabla_vendedores(acumulado_emp))
        elems.append(Spacer(1, 0.4 * inch))
 
    doc.build(elems)