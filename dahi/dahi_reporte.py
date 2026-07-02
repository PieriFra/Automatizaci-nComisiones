"""
dahi_reporte.py
================
Procesa una carpeta de planillas DAHI y genera su propio "Informe DAHI"
en PDF: Informe / Fecha / Total Cobrado / Comisiones / Fletes.

A diferencia del flujo de DP/Fills (DistribucionMensualCom.py):
  - No hay concepto de vendedor ni PDF de "Distribución de Comisiones".
  - No hay distinción de tipo 1/2: cada PDF es una única planilla.
  - Se valida también el monto de Fletes (no solo Comisiones).

Toda la detección (empresa, N° de informe, fecha) se lee del texto del
propio PDF vía dahi_parser.py, no del nombre de archivo — no depende de
ninguna convención de nombres.

Uso:
    python dahi_reporte.py "/ruta/a/carpeta/con/planillas/DAHI" [carpeta_salida]
"""

from __future__ import annotations

import os
import sys

import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4

# DistribucionMensualCom.py (DP/Fills) vive en la raíz del proyecto,
# carpeta hermana de esta; se agrega al path para reutilizar sus
# helpers genéricos (_MESES, _mes_anio) sin duplicarlos ni mover nada
# del flujo de DP/Fills.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dahi_parser import parsear_planilla_dahi
from DistribucionMensualCom import _MESES, _mes_anio

TOLERANCIA = 2.0

_ESTILO_TABLA = [
    ("BACKGROUND",    (0, 0), (-1,  0), colors.lightgrey),
    ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
    ("ALIGN",         (2, 1), (-1, -1), "RIGHT"),
    ("FONTNAME",      (0, 0), (-1,  0), "Helvetica-Bold"),
    ("BOTTOMPADDING", (0, 0), (-1,  0), 8),
    ("TOPPADDING",    (0, 0), (-1,  0), 8),
]


# ---------------------------------------------------------------------------
# Procesamiento de carpeta
# ---------------------------------------------------------------------------

def procesar_carpeta_dahi(carpeta_path: str, verbose: bool = True) -> pd.DataFrame:
    filas = []
    omitidas = []

    for archivo in sorted(os.listdir(carpeta_path)):
        if not archivo.lower().endswith(".pdf"):
            continue
        if "informe dahi" in archivo.lower():
            continue  # PDF de reporte ya generado por este mismo script

        pdf_path = os.path.join(carpeta_path, archivo)

        if verbose:
            print(f"\nProcesando: {archivo}")

        try:
            datos = parsear_planilla_dahi(pdf_path)

            if datos["fecha"] == "N/D" or datos["total"] == 0:
                print(
                    f"  ⚠️  No se pudo leer la planilla (posible PDF escaneado sin "
                    f"tabla digital). Se omite del informe — revisar a mano: {archivo}"
                )
                omitidas.append(archivo)
                continue

            suma_sub = sum(datos["subtotales"].values())
            total = datos["total"]
            if abs(suma_sub - total) > TOLERANCIA:
                print(
                    f"  ⚠️  Suma subtotales ({suma_sub:,.2f}) ≠ TOTAL ({total:,.2f}) "
                    f"| diff={suma_sub - total:+.2f}"
                )

            if datos["pct_comision"] is not None:
                comision_esperada = total * datos["pct_comision"] / 100
                if abs(comision_esperada - datos["comisiones"]) > TOLERANCIA:
                    print(
                        f"  ⚠️  Comisión ({datos['comisiones']:,.2f}) ≠ "
                        f"{datos['pct_comision']:.0f}% del total ({comision_esperada:,.2f})"
                    )

            if datos["pct_fletes"] is not None:
                flete_esperado = total * datos["pct_fletes"] / 100
                if abs(flete_esperado - datos["fletes"]) > TOLERANCIA:
                    print(
                        f"  ⚠️  Fletes ({datos['fletes']:,.2f}) ≠ "
                        f"{datos['pct_fletes']:.0f}% del total ({flete_esperado:,.2f})"
                    )

            filas.append({
                "Informe": datos["informe"],
                "Fecha": datos["fecha"],
                "Total": total,
                "Comisiones": datos["comisiones"],
                "Fletes": datos["fletes"],
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ❌  Error al procesar {archivo}: {e}")
            omitidas.append(archivo)

    if omitidas:
        print(f"\n⚠️  {len(omitidas)} planilla(s) omitida(s) del informe (revisar a mano):")
        for archivo in omitidas:
            print(f"   - {archivo}")

    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Generación del PDF
# ---------------------------------------------------------------------------

def _tabla_informes(df: pd.DataFrame) -> Table:
    data = [["Informe", "Fecha", "Total Cobrado", "Comisiones", "Fletes"]]
    for _, row in df.iterrows():
        data.append([
            str(row["Informe"]),
            str(row["Fecha"]),
            f"${row['Total']:,.2f}",
            f"${row['Comisiones']:,.2f}",
            f"${row['Fletes']:,.2f}",
        ])

    fila_total = len(data)
    data.append([
        "TOTAL", "",
        f"${df['Total'].sum():,.2f}",
        f"${df['Comisiones'].sum():,.2f}",
        f"${df['Fletes'].sum():,.2f}",
    ])

    tabla = Table(data, repeatRows=1)
    estilo = list(_ESTILO_TABLA) + [
        ("FONTNAME",   (0, fila_total), (-1, fila_total), "Helvetica-Bold"),
        ("BACKGROUND", (0, fila_total), (-1, fila_total), colors.Color(0.70, 0.70, 0.70)),
    ]
    tabla.setStyle(TableStyle(estilo))
    return tabla


def generar_reporte_dahi_pdf(ruta_salida: str, df: pd.DataFrame):
    estilos  = getSampleStyleSheet()
    doc      = SimpleDocTemplate(ruta_salida, pagesize=A4)
    elems    = []
    mes_anio = _mes_anio(df)

    elems.append(Paragraph(f"<b>INFORME DAHI {mes_anio}</b>", estilos["Title"]))
    elems.append(Spacer(1, 0.2 * inch))
    elems.append(Paragraph(f"Fecha de generación: {pd.Timestamp.now():%d/%m/%Y}", estilos["Normal"]))
    elems.append(Spacer(1, 0.3 * inch))

    elems.append(_tabla_informes(df))

    doc.build(elems)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(carpeta: str, carpeta_salida: str | None = None):
    print("\n🔄 Procesando planillas DAHI...\n")
    df = procesar_carpeta_dahi(carpeta)

    if df is None or df.empty:
        raise ValueError("No se encontraron planillas válidas.")

    carpeta_salida = carpeta_salida or carpeta

    fechas = pd.to_datetime(df["Fecha"], dayfirst=True)
    df = df.assign(_anio=fechas.dt.year, _mes=fechas.dt.month)

    for (anio, mes), grupo in df.groupby(["_anio", "_mes"]):
        grupo = grupo.drop(columns=["_anio", "_mes"]).reset_index(drop=True)
        mes_anio = f"{_MESES[mes].title()} {anio}"
        ruta_salida = os.path.join(carpeta_salida, f"Informe DAHI {mes_anio}.pdf")
        generar_reporte_dahi_pdf(ruta_salida, grupo)
        print(f"✅ Informe DAHI generado en:\n{ruta_salida}\n")


if __name__ == "__main__":
    carpeta_arg = sys.argv[1] if len(sys.argv) > 1 else input("Ruta de la carpeta con las planillas DAHI: ").strip()
    carpeta_salida_arg = sys.argv[2] if len(sys.argv) > 2 else None
    main(carpeta_arg, carpeta_salida_arg)
