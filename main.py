import os
import sys
from datetime import datetime
from DistribucionMensualCom import procesar_carpeta_planillas, generar_reporte_comisiones_pdf, generar_distribucion_comisiones_pdf
from clientes_vendedor import MAPA_CLIENTES_VENDEDORES

# Diccionario para nombres de meses en español
MESES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre"
}

def ejecutar_proceso(carpeta_path: str):

    if not os.path.exists(carpeta_path):
        raise FileNotFoundError("La carpeta especificada no existe.")

    print("\n🔄 Procesando planillas...\n")

    # Usar la función de DistribucionMensualCom que necesita el mapa de clientes->vendedores
    df_resumen, acumulado_vendedores = procesar_carpeta_planillas(
        carpeta_path,
        MAPA_CLIENTES_VENDEDORES
    )

    if df_resumen is None or df_resumen.empty:
        raise ValueError("No se encontraron planillas válidas.")

    # Obtener el mes actual
    mes_actual = MESES[datetime.now().month]

    # Generar Reporte de Comisiones
    ruta_reporte_comisiones = os.path.join(carpeta_path, f"Reporte Comisiones {mes_actual}.pdf")
    generar_reporte_comisiones_pdf(ruta_reporte_comisiones, df_resumen)

    # Generar Distribución de Comisiones
    ruta_distribucion_comisiones = os.path.join(carpeta_path, f"Distribución Comisiones {mes_actual}.pdf")
    generar_distribucion_comisiones_pdf(ruta_distribucion_comisiones, acumulado_vendedores)

    print("\n✅ Proceso finalizado correctamente.")
    print(f"📄 Reporte de Comisiones generado en:\n{ruta_reporte_comisiones}\n")
    print(f"📄 Distribución de Comisiones generado en:\n{ruta_distribucion_comisiones}\n")


if __name__ == "__main__":

    if len(sys.argv) > 1:
        carpeta = sys.argv[1]
    else:
        carpeta = input("Ingrese la ruta de la carpeta con las planillas: ").strip()

    try:
        ejecutar_proceso(carpeta)
    except Exception as e:
        print(f"\n❌ Error durante el proceso: {e}\n")