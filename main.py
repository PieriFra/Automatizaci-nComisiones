from __future__ import annotations

import os
import sys
import pandas as pd
from datetime import datetime
from clientes_vendedor import MAPA_CLIENTES_DP, MAPA_CLIENTES_FILLS
from DistribucionMensualCom import procesar_carpeta_planillas, generar_reporte_comisiones_pdf, generar_distribucion_comisiones_pdf

MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

# Carpeta donde se guardan por defecto los PDFs generados (Reporte y
# Distribución de Comisiones), separada de la carpeta con las planillas.
CARPETA_SALIDA_DEFAULT = (
    "/Users/pierinafrairealassia/Library/Mobile Documents/com~apple~CloudDocs/"
    "Trabajo/Di Pascualle/COMISIONES"
)


def ejecutar_proceso(carpeta_path: str, carpeta_salida: str | None = None):

    if not os.path.exists(carpeta_path):
        raise FileNotFoundError("La carpeta especificada no existe.")

    carpeta_salida = carpeta_salida or CARPETA_SALIDA_DEFAULT
    if not os.path.exists(carpeta_salida):
        raise FileNotFoundError(f"La carpeta de salida no existe: {carpeta_salida}")

    print("\n🔄 Procesando planillas...\n")

    df_resumen, acumulado_vendedores = procesar_carpeta_planillas(
        carpeta_path,
        MAPA_CLIENTES_DP, MAPA_CLIENTES_FILLS
    )

    if df_resumen is None or df_resumen.empty:
        raise ValueError("No se encontraron planillas válidas.")

    fecha_ref = pd.to_datetime(df_resumen["Fecha"], dayfirst=True).iloc[0]
    mes_reporte = MESES[fecha_ref.month]
    anio_reporte = fecha_ref.year

    ruta_reporte_comisiones = os.path.join(carpeta_salida, f"Reporte Comisiones {mes_reporte} {anio_reporte}.pdf")
    generar_reporte_comisiones_pdf(ruta_reporte_comisiones, df_resumen)

    ruta_distribucion_comisiones = os.path.join(carpeta_salida, f"Distribución Comisiones {mes_reporte} {anio_reporte}.pdf")
    generar_distribucion_comisiones_pdf(ruta_distribucion_comisiones, acumulado_vendedores, df_resumen)

    print("\n✅ Proceso finalizado correctamente.")
    print(f"📄 Reporte de Comisiones generado en:\n{ruta_reporte_comisiones}\n")
    print(f"📄 Distribución de Comisiones generado en:\n{ruta_distribucion_comisiones}\n")


if __name__ == "__main__":

    if len(sys.argv) > 1:
        carpeta = sys.argv[1]
    else:
        carpeta = input("Ingrese la ruta de la carpeta con las planillas: ").strip()

    carpeta_salida_arg = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        ejecutar_proceso(carpeta, carpeta_salida_arg)
    except Exception as e:
        print(f"\n❌ Error durante el proceso: {e}\n")