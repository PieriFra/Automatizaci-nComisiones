"""
reporte_comisiones_ajustado.py
================================
Genera dos PDFs (mismo formato que los que produce main.py) pero con dos
correcciones puntuales aplicadas sobre los datos de Junio 2026:

  1. Ajuste manual de comisiones (ver ajuste_manual_comisiones.py): 6
     planillas donde ciertas facturas de ciertos clientes, con fecha desde
     el 30/05/2026, no debían comisionarse. Se corrige el monto de
     "Comisiones" de esas planillas (el "Total Cobrado" no cambia) y se
     descuenta la diferencia de la distribución por vendedor.

  2. Corrección de "Planilla de Cobranza N° 24 Fills (2).pdf": a diferencia
     del resto de las planillas Fills tipo 2 (que son PDFs digitales), esta
     es la única escaneada. El OCR de Tesseract separa las etiquetas
     (Cliente, SUBTOTAL, TOTAL, Comisiones...) de los montos ($) en dos
     bloques de texto distintos en vez de mantenerlos en la misma línea, y
     el parser de texto plano espera que estén juntos — por eso la planilla
     queda con Total $0. Los valores correctos se reconstruyeron a mano
     leyendo el texto OCR en orden (la suma de subtotales por cliente da
     exacto el TOTAL impreso: $2.206.118,37).

Ambas correcciones se aplican por fuera del flujo normal: este script NO
modifica DistribucionMensualCom.py ni ajuste_manual_comisiones.py, sólo los
importa y reutiliza.

Uso:
    python reporte_comisiones_ajustado.py "/ruta/a/PlanillasCobranza" [prefijo_salida]
"""

from __future__ import annotations

import os
import re
import sys
import copy

import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4

from clientes_vendedor import MAPA_CLIENTES_DP, MAPA_CLIENTES_FILLS
from DistribucionMensualCom import (
    procesar_carpeta_planillas,
    calcular_comisiones_vendedores,
    generar_distribucion_comisiones_pdf,
    _tabla_planillas,
    _mes_anio,
)
from ajuste_manual_comisiones import (
    PLANILLAS_AJUSTAR,
    recalcular_planilla,
)

_ESTILO_DETALLE = [
    ("BACKGROUND",    (0, 0), (-1, 0), colors.Color(0.93, 0.93, 0.93)),
    ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
    ("ALIGN",         (3, 1), (-1, -1), "RIGHT"),
    ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE",      (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("TOPPADDING",    (0, 0), (-1, -1), 4),
]

_ESTILO_RESUMEN = [
    ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
    ("BACKGROUND",    (0, 0), (0, -1), colors.Color(0.93, 0.93, 0.93)),
    ("FONTNAME",      (0, 0), (0, -1), "Helvetica-Bold"),
    ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
    ("FONTSIZE",      (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("TOPPADDING",    (0, 0), (-1, -1), 4),
]


def _fmt(v: float) -> str:
    return f"${v:,.2f}"


def _numero_planilla(nombre_archivo: str) -> str:
    m = re.search(r'N[°º]?\s*0*(\d+)', nombre_archivo)
    if not m:
        raise ValueError(f"No se pudo extraer el número de planilla de '{nombre_archivo}'")
    return m.group(1)


# ---------------------------------------------------------------------------
# 1. Ajuste manual de comisiones (6 planillas)
# ---------------------------------------------------------------------------

def aplicar_ajustes(carpeta: str, df_resumen: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Devuelve:
      df_ajustado  : copia de df_resumen con "Comisiones Planilla" corregida
                      para las planillas del ajuste manual (Total no cambia).
      correcciones : { empresa: [ {planilla_id, archivo, facturas_excluidas,
                                    base_original, base_ajustada,
                                    comision_original, comision_ajustada,
                                    dist_original, dist_ajustada}, ... ] }
    """
    df_ajustado = df_resumen.copy()
    correcciones: dict = {}

    for nombre_archivo in PLANILLAS_AJUSTAR:
        pdf_path = os.path.join(carpeta, nombre_archivo)
        if not os.path.exists(pdf_path):
            print(f"⚠️  No se encontró: {nombre_archivo} (se omite del reporte ajustado)")
            continue

        r = recalcular_planilla(pdf_path)
        empresa = r["empresa"]
        numero = _numero_planilla(nombre_archivo)
        planilla_id = f"PLANILLA N°{numero}"

        mask = (df_ajustado["Empresa"] == empresa) & (df_ajustado["Planilla"] == planilla_id)
        if not mask.any():
            print(f"⚠️  No se encontró en el resumen la fila para {planilla_id} ({empresa}) "
                  f"— {nombre_archivo}. Se omite del reporte ajustado.")
            continue

        comision_original = float(df_ajustado.loc[mask, "Comisiones Planilla"].iloc[0])
        comision_ajustada = sum(r["dist_ajustada"].values())

        df_ajustado.loc[mask, "Comisiones Planilla"] = comision_ajustada

        correcciones.setdefault(empresa, []).append({
            "tipo": "exclusion_facturas",
            "planilla_id": planilla_id,
            "archivo": nombre_archivo,
            "facturas_excluidas": r["facturas_excluidas"],
            "base_original": r["total_original"],
            "base_ajustada": r["total_ajustado"],
            "comision_original": comision_original,
            "comision_ajustada": comision_ajustada,
            "dist_original": r["dist_original"],
            "dist_ajustada": r["dist_ajustada"],
        })

    return df_ajustado, correcciones


# ---------------------------------------------------------------------------
# 2. Corrección OCR — Planilla N°24 Fills
# ---------------------------------------------------------------------------

ARCHIVO_N24 = "Planilla de Cobranza N° 24 Fills (2).pdf"
EMPRESA_N24 = "FILLS"
PLANILLA_ID_N24 = "PLANILLA N°24"
TIPO_INFORME_N24 = 2

# Reconstruidos a mano desde el texto OCR (ver docstring del módulo).
SUBTOTALES_N24 = {
    "Barco Sebastian Fernando": 156692.90,
    "Chiaverano Gorgo Santiago": 536623.38,
    "Gagliano Maria Emilia y Gagliano Nicolas Luis": 705240.43,
    "Manuel Santiago": 261200.16,
    "SFP SA": 319322.15,
    "Varetto Jose Maria": 227039.35,
}


def aplicar_correccion_n24_fills(df_ajustado: pd.DataFrame, correcciones: dict) -> pd.DataFrame:
    """Reemplaza la fila de la Planilla N°24 Fills (Total $0 por fallo de OCR) por los datos correctos."""
    mask = (
        (df_ajustado["Empresa"] == EMPRESA_N24)
        & (df_ajustado["Tipo"] == TIPO_INFORME_N24)
        & (df_ajustado["Planilla"].isin(["N/D", PLANILLA_ID_N24]))
        & (df_ajustado["Total"] == 0)
    )
    if not mask.any():
        print(f"⚠️  No se encontró en el resumen la fila con Total $0 de {ARCHIVO_N24}. "
              "Se omite la corrección OCR (¿ya estaba corregida?).")
        return df_ajustado

    total_correcto = sum(SUBTOTALES_N24.values())
    dist_ajustada = calcular_comisiones_vendedores(
        SUBTOTALES_N24, MAPA_CLIENTES_FILLS, EMPRESA_N24, tipo_informe=TIPO_INFORME_N24
    )
    comision_correcta = sum(dist_ajustada.values())

    df_ajustado.loc[mask, "Planilla"] = PLANILLA_ID_N24
    df_ajustado.loc[mask, "Total"] = total_correcto
    df_ajustado.loc[mask, "Comisiones Planilla"] = comision_correcta

    correcciones.setdefault(EMPRESA_N24, []).append({
        "tipo": "correccion_ocr",
        "planilla_id": PLANILLA_ID_N24,
        "archivo": ARCHIVO_N24,
        "subtotales": SUBTOTALES_N24,
        "base_original": 0.0,
        "base_ajustada": total_correcto,
        "comision_original": 0.0,
        "comision_ajustada": comision_correcta,
        "dist_original": {},
        "dist_ajustada": dist_ajustada,
    })

    return df_ajustado


# ---------------------------------------------------------------------------
# Distribución por vendedor corregida (para el segundo PDF)
# ---------------------------------------------------------------------------

def calcular_acumulado_ajustado(acumulado_vendedores: dict, correcciones: dict) -> dict:
    """Aplica sobre 'acumulado_vendedores' (empresa -> vendedor -> total) la
    diferencia (ajustada - original) de cada corrección registrada."""
    acumulado_ajustado = copy.deepcopy(acumulado_vendedores)

    for empresa, lista in correcciones.items():
        acumulado_ajustado.setdefault(empresa, {})
        for correccion in lista:
            vendedores = set(correccion["dist_original"]) | set(correccion["dist_ajustada"])
            for vendedor in vendedores:
                orig = correccion["dist_original"].get(vendedor, 0.0)
                ajus = correccion["dist_ajustada"].get(vendedor, 0.0)
                diff = ajus - orig
                acumulado_ajustado[empresa][vendedor] = (
                    acumulado_ajustado[empresa].get(vendedor, 0.0) + diff
                )

    return acumulado_ajustado


# ---------------------------------------------------------------------------
# Flowables del detalle de ajustes (Reporte de Comisiones)
# ---------------------------------------------------------------------------

def _detalle_exclusion_facturas(estilos, correccion: dict) -> list:
    elems = []
    elems.append(Paragraph(
        f"Ajuste manual — {correccion['planilla_id']} ({correccion['archivo']})",
        estilos["Heading4"],
    ))

    data = [["Cliente", "N° Factura", "Fecha", "Importe excluido"]]
    for f in correccion["facturas_excluidas"]:
        data.append([
            f["cliente"],
            f["factura"],
            f["fecha"].strftime("%d/%m/%Y") if f["fecha"] else "-",
            _fmt(f["importe"]),
        ])
    tabla_facturas = Table(data, repeatRows=1, colWidths=[2.6 * inch, 1.3 * inch, 0.9 * inch, 1.3 * inch])
    tabla_facturas.setStyle(TableStyle(_ESTILO_DETALLE))
    elems.append(tabla_facturas)
    elems.append(Spacer(1, 0.08 * inch))

    elems.append(_tabla_resumen_ajuste(correccion))
    elems.append(Spacer(1, 0.25 * inch))
    return elems


def _detalle_correccion_ocr(estilos, correccion: dict) -> list:
    elems = []
    elems.append(Paragraph(
        f"Corrección de lectura OCR — {correccion['planilla_id']} ({correccion['archivo']})",
        estilos["Heading4"],
    ))
    elems.append(Paragraph(
        "PDF escaneado: el OCR separó las etiquetas de los montos en bloques de texto "
        "distintos y la planilla quedó con Total $0,00. Subtotales reconstruidos a mano "
        "a partir del texto OCR:",
        estilos["Normal"],
    ))
    elems.append(Spacer(1, 0.05 * inch))

    data = [["Cliente", "Subtotal"]]
    for cliente, monto in correccion["subtotales"].items():
        data.append([cliente, _fmt(monto)])
    tabla_subtotales = Table(data, repeatRows=1, colWidths=[3.9 * inch, 1.4 * inch])
    tabla_subtotales.setStyle(TableStyle(_ESTILO_DETALLE))
    elems.append(tabla_subtotales)
    elems.append(Spacer(1, 0.08 * inch))

    elems.append(_tabla_resumen_ajuste(correccion))
    elems.append(Spacer(1, 0.25 * inch))
    return elems


def _tabla_resumen_ajuste(correccion: dict) -> Table:
    resumen_data = [
        ["Total original de planilla", _fmt(correccion["base_original"])],
        ["Total ajustado de planilla", _fmt(correccion["base_ajustada"])],
        ["Comisión original", _fmt(correccion["comision_original"])],
        ["Comisión ajustada", _fmt(correccion["comision_ajustada"])],
        ["Diferencia", _fmt(correccion["comision_ajustada"] - correccion["comision_original"])],
    ]
    tabla_resumen = Table(resumen_data, colWidths=[2.6 * inch, 1.6 * inch])
    tabla_resumen.setStyle(TableStyle(_ESTILO_RESUMEN))
    return tabla_resumen


def _tabla_total_resignado(total_resignado: float) -> Table:
    data = [["Total de comisiones resignadas", _fmt(total_resignado)]]
    tabla = Table(data, colWidths=[2.6 * inch, 1.6 * inch])
    tabla.setStyle(TableStyle([
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, -1), colors.Color(0.80, 0.80, 0.80)),
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica-Bold"),
        ("ALIGN",      (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
    ]))
    return tabla


_RENDER_DETALLE = {
    "exclusion_facturas": _detalle_exclusion_facturas,
    "correccion_ocr": _detalle_correccion_ocr,
}


# ---------------------------------------------------------------------------
# Generación de PDFs
# ---------------------------------------------------------------------------

def generar_reporte_comisiones_ajustado_pdf(
    ruta_salida: str,
    df_resumen: pd.DataFrame,
    correcciones: dict,
):
    df = df_resumen.dropna(subset=["Planilla"]).drop_duplicates(
        subset=["Planilla", "Fecha", "Empresa"]
    ).reset_index(drop=True)

    estilos  = getSampleStyleSheet()
    doc      = SimpleDocTemplate(ruta_salida, pagesize=A4)
    elems    = []
    mes_anio = _mes_anio(df)

    elems.append(Paragraph(f"<b>REPORTE DE COMISIONES {mes_anio} (AJUSTADO)</b>", estilos["Title"]))
    elems.append(Spacer(1, 0.2 * inch))
    elems.append(Paragraph(
        "Incluye corrección manual de comisiones (facturas excluidas por no "
        "corresponder comisión). Ver detalle debajo de cada tabla.",
        estilos["Normal"],
    ))
    elems.append(Spacer(1, 0.3 * inch))

    for empresa in sorted(df["Empresa"].unique()):
        df_emp: pd.DataFrame = df.loc[df["Empresa"] == empresa]
        elems.append(Paragraph(f"<b>Empresa: {empresa}</b>", estilos["Heading2"]))
        elems.append(Spacer(1, 0.15 * inch))
        elems.append(_tabla_planillas(df_emp, empresa))
        elems.append(Spacer(1, 0.3 * inch))

        # Sólo se muestra el detalle de las correcciones por facturas excluidas;
        # la corrección de lectura OCR (Planilla N°24 Fills) queda aplicada en
        # la tabla de arriba pero no se expone en el detalle del reporte.
        correcciones_visibles = [
            c for c in correcciones.get(empresa, []) if c["tipo"] == "exclusion_facturas"
        ]
        if correcciones_visibles:
            elems.append(Paragraph("<b>Detalle de ajustes manuales</b>", estilos["Heading3"]))
            elems.append(Spacer(1, 0.1 * inch))
            for correccion in correcciones_visibles:
                render = _RENDER_DETALLE[correccion["tipo"]]
                elems.extend(render(estilos, correccion))

            total_resignado = sum(
                c["comision_original"] - c["comision_ajustada"] for c in correcciones_visibles
            )
            elems.append(_tabla_total_resignado(total_resignado))

        elems.append(Spacer(1, 0.2 * inch))

    doc.build(elems)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(carpeta: str, carpeta_salida: str | None = None):
    print("\n🔄 Procesando planillas (parseo original, sin ajustes)...\n")
    df_resumen, acumulado_vendedores = procesar_carpeta_planillas(
        carpeta, MAPA_CLIENTES_DP, MAPA_CLIENTES_FILLS, verbose=False
    )

    if df_resumen is None or df_resumen.empty:
        raise ValueError("No se encontraron planillas válidas.")

    print("🔧 Aplicando ajuste manual de comisiones (6 planillas)...")
    df_ajustado, correcciones = aplicar_ajustes(carpeta, df_resumen)

    print("🔧 Aplicando corrección OCR de la Planilla N°24 Fills...\n")
    df_ajustado = aplicar_correccion_n24_fills(df_ajustado, correcciones)

    acumulado_ajustado = calcular_acumulado_ajustado(acumulado_vendedores, correcciones)

    carpeta_salida = carpeta_salida or carpeta
    mes_anio = _mes_anio(df_ajustado).title()

    ruta_reporte = os.path.join(carpeta_salida, f"Reporte Comisiones {mes_anio} (Ajustado).pdf")
    generar_reporte_comisiones_ajustado_pdf(ruta_reporte, df_ajustado, correcciones)
    print(f"✅ Reporte de Comisiones ajustado generado en:\n{ruta_reporte}\n")

    ruta_distribucion = os.path.join(carpeta_salida, f"Distribución Comisiones {mes_anio} (Ajustado).pdf")
    generar_distribucion_comisiones_pdf(ruta_distribucion, acumulado_ajustado, df_ajustado)
    print(f"✅ Distribución de Comisiones ajustada generada en:\n{ruta_distribucion}\n")


if __name__ == "__main__":
    carpeta_arg = sys.argv[1] if len(sys.argv) > 1 else input("Ruta de la carpeta con las planillas: ").strip()
    carpeta_salida_arg = sys.argv[2] if len(sys.argv) > 2 else None
    main(carpeta_arg, carpeta_salida_arg)
