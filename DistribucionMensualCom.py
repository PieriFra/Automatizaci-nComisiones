"""
DistribucionMensualCom.py
=========================
Procesa una carpeta de planillas de cobranza de múltiples empresas y tipos,
calcula la distribución de comisiones por vendedor y genera los PDFs de reporte.

Empresas soportadas : DP, Fills  (detectado desde el nombre del archivo)
Tipos de informe    : 1, 2       (detectado desde el (1) o (2) del nombre)
"""

import os
import re
from collections import defaultdict
from datetime import datetime

import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4

from clientes_vendedor import (
    MAPA_CLIENTES_DP, MAPA_CLIENTES_FILLS,
    REGLAS_COMISION, REGLAS_ESPECIALES,
)
from pdf_reader import extraer_texto_pdf, detectar_empresa, detectar_tipo_informe
from planilla_parser import parsear_planilla, _normalizar

MAPAS_POR_EMPRESA = {
    "DP":    MAPA_CLIENTES_DP,
    "FILLS": MAPA_CLIENTES_FILLS,
}


# ---------------------------------------------------------------------------
# Helpers de matching
# ---------------------------------------------------------------------------

def _mapa_normalizado(mapa: dict) -> tuple:
    m = {_normalizar(k): k for k in mapa}
    claves = sorted(m.keys(), key=len, reverse=True)
    return m, claves


def _match_cliente(nombre_raw: str, mapa_norm: dict, claves_norm: list):
    nombre_up = _normalizar(nombre_raw)
    for clave in claves_norm:
        if clave in nombre_up:
            return mapa_norm[clave]
    return None


# ---------------------------------------------------------------------------
# Cálculo de comisiones
# ---------------------------------------------------------------------------

def calcular_comisiones_vendedores(
    subtotales: dict,
    cliente_vendedor: dict,
    empresa: str,
    tipo_informe: int = 2,
) -> dict:
    """
    Calcula comisiones aplicando:
      1. Base de cálculo: subtotal / 1.21 para tipo 1, subtotal directo para tipo 2
      2. Reglas especiales por cliente (ej: Rosental al 5%)
      3. Reglas estándar por vendedor según empresa
    """
    reglas_std      = REGLAS_COMISION[empresa]
    reglas_esp      = REGLAS_ESPECIALES.get(empresa, {})
    mapa_norm, claves_norm = _mapa_normalizado(cliente_vendedor)
    reglas_esp_norm = {_normalizar(k): v for k, v in reglas_esp.items()}
    # Tipo 1: comisiones sobre neto sin IVA (subtotal / 1.21)
    divisor = 1.21 if tipo_informe == 1 else 1.0

    comisiones = defaultdict(float)

    for nombre_raw, total in subtotales.items():
        total = total / divisor   # base de cálculo
        nombre_norm = _normalizar(nombre_raw)

        # 1. ¿Tiene regla especial?
        regla = None
        for clave_esp, regla_esp in reglas_esp_norm.items():
            if clave_esp in nombre_norm:
                regla = regla_esp
                break

        # 2. Si no, usar regla estándar del vendedor
        if regla is None:
            clave_original = _match_cliente(nombre_raw, mapa_norm, claves_norm)
            if clave_original is None:
                raise ValueError(
                    f"Cliente sin vendedor asignado: '{nombre_raw}' (empresa: {empresa})\n"
                    "Agregalo al diccionario correspondiente en clientes_vendedor.py"
                )
            vendedor      = cliente_vendedor[clave_original]
            vendedor_norm = _normalizar(vendedor)
            regla = reglas_std.get(vendedor_norm)
            if regla is None:
                raise ValueError(
                    f"No hay regla de comisión para el vendedor '{vendedor}' "
                    f"en la empresa '{empresa}'."
                )

        for beneficiario, porcentaje in regla.items():
            comisiones[beneficiario] += total * porcentaje

    return dict(comisiones)


# ---------------------------------------------------------------------------
# Procesamiento de carpeta
# ---------------------------------------------------------------------------

def procesar_carpeta_planillas(
    carpeta_path: str,
    mapa_clientes_vendedores: dict,  # mantenido por compatibilidad con main.py
    verbose: bool = True,
) -> tuple:
    """
    Procesa todos los PDFs de la carpeta.

    Devuelve:
        df_resumen           : DataFrame con una fila por planilla
        acumulado_vendedores : { empresa: { vendedor: total } }
    """
    TOLERANCIA = 2.0

    resumen_planillas = []
    acumulado_por_empresa = defaultdict(lambda: defaultdict(float))

    for archivo in sorted(os.listdir(carpeta_path)):
        if not archivo.lower().endswith(".pdf"):
            continue

        archivo_low = archivo.lower()
        if "reporte comisiones" in archivo_low or "distribucion comisiones" in archivo_low:
            continue

        pdf_path = os.path.join(carpeta_path, archivo)

        if verbose:
            print(f"\nProcesando: {archivo}")

        try:
            empresa       = detectar_empresa(pdf_path)
            tipo_informe  = detectar_tipo_informe(pdf_path)
            texto         = extraer_texto_pdf(pdf_path, verbose=verbose)
            datos         = parsear_planilla(pdf_path, tipo_informe, texto)

            planilla    = datos["planilla"]
            fecha       = datos["fecha"]
            total       = datos["total"]
            comis_total = datos["comisiones"]
            subtotales  = datos["subtotales"]

            mapa_empresa = MAPAS_POR_EMPRESA[empresa]
            comisiones_vendedores = calcular_comisiones_vendedores(
                subtotales, mapa_empresa, empresa, tipo_informe
            )

            # Chequeos de consistencia
            suma_sub = sum(subtotales.values())
            if abs(suma_sub - total) > TOLERANCIA:
                print(
                    f"  ⚠️  Suma subtotales ({suma_sub:,.2f}) ≠ TOTAL ({total:,.2f}) "
                    f"| diff={suma_sub - total:+.2f}"
                )

            suma_dist = sum(comisiones_vendedores.values())
            if abs(suma_dist - comis_total) > TOLERANCIA:
                # En planillas con reglas especiales por cliente (ej: Rosental en DP tipo 1)
                # la suma distribuida difiere del total de comisiones de la planilla.
                # Esto es esperado y no indica un error.
                print(
                    f"  ℹ️  Distribución interna ({suma_dist:,.2f}) difiere de "
                    f"Comisiones planilla ({comis_total:,.2f}) "
                    f"| diff={suma_dist - comis_total:+.2f} (puede ser por reglas especiales)"
                )

            for vendedor, valor in comisiones_vendedores.items():
                acumulado_por_empresa[empresa][vendedor] += valor

            fila = {
                "Empresa":             empresa,
                "Tipo":                tipo_informe,
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
    acumulado = {emp: dict(vends) for emp, vends in acumulado_por_empresa.items()}

    return df, acumulado


# ---------------------------------------------------------------------------
# Helpers para PDFs de reporte
# ---------------------------------------------------------------------------

_MESES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
    5: "MAYO",  6: "JUNIO",   7: "JULIO", 8: "AGOSTO",
    9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
}

_ESTILO_TABLA = [
    ("BACKGROUND",    (0, 0), (-1,  0), colors.lightgrey),
    ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
    ("ALIGN",         (2, 1), (-1, -1), "RIGHT"),
    ("FONTNAME",      (0, 0), (-1,  0), "Helvetica-Bold"),
    ("BOTTOMPADDING", (0, 0), (-1,  0), 8),
    ("TOPPADDING",    (0, 0), (-1,  0), 8),
]

_ESTILO_VENDEDORES = [
    ("BACKGROUND",    (0, 0), (-1,  0), colors.lightgrey),
    ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
    ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
    ("FONTNAME",      (0, 0), (-1,  0), "Helvetica-Bold"),
    ("BOTTOMPADDING", (0, 0), (-1,  0), 8),
    ("TOPPADDING",    (0, 0), (-1,  0), 8),
]


def _mes_anio(df: pd.DataFrame) -> str:
    fecha_ref = pd.to_datetime(df["Fecha"], dayfirst=True).iloc[0]
    return f"{_MESES[fecha_ref.month]} {fecha_ref.year}"


def _tabla_planillas(df_empresa: pd.DataFrame) -> Table:
    data = [["Planilla", "Tipo", "Fecha", "Total Cobrado", "Comisiones"]]
    for _, row in df_empresa.iterrows():
        data.append([
            row["Planilla"],
            f"Tipo {int(row['Tipo'])}",
            row["Fecha"],
            f"${row['Total']:,.2f}",
            f"${row['Comisiones Planilla']:,.2f}",
        ])
    # Fila de totales
    data.append([
        "TOTAL", "", "",
        f"${df_empresa['Total'].sum():,.2f}",
        f"${df_empresa['Comisiones Planilla'].sum():,.2f}",
    ])
    tabla = Table(data, repeatRows=1)
    estilo = _ESTILO_TABLA + [
        ("FONTNAME",      (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND",    (0, -1), (-1, -1), colors.lightgrey),
    ]
    tabla.setStyle(TableStyle(estilo))
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
    """PDF de comisiones con una sección por empresa."""
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
        elems.append(Spacer(1, 0.4 * inch))

    doc.build(elems)


def generar_distribucion_comisiones_pdf(
    ruta_salida: str,
    acumulado_vendedores: dict,
    df_resumen: pd.DataFrame,
):
    """PDF de distribución con una sección por empresa."""
    estilos  = getSampleStyleSheet()
    doc      = SimpleDocTemplate(ruta_salida, pagesize=A4)
    elems    = []
    mes_anio = _mes_anio(df_resumen)

    elems.append(Paragraph(f"<b>DISTRIBUCIÓN DE COMISIONES {mes_anio}</b>", estilos["Title"]))
    elems.append(Spacer(1, 0.2 * inch))
    elems.append(Paragraph(f"Fecha de generación: {datetime.now():%d/%m/%Y}", estilos["Normal"]))
    elems.append(Spacer(1, 0.3 * inch))

    for empresa in sorted(acumulado_vendedores.keys()):
        elems.append(Paragraph(f"<b>Empresa: {empresa}</b>", estilos["Heading2"]))
        elems.append(Spacer(1, 0.15 * inch))
        elems.append(_tabla_vendedores(acumulado_vendedores[empresa]))
        elems.append(Spacer(1, 0.4 * inch))

    doc.build(elems)