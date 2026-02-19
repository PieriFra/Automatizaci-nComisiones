import os
import sys
from DistribucionMensualCom import procesar_carpeta_planillas, generar_reporte_mensual_pdf
from clientes_vendedor import MAPA_CLIENTES_VENDEDORES

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

    ruta_pdf = os.path.join(carpeta_path, "Reporte_Comisiones.pdf")

    generar_reporte_mensual_pdf(ruta_pdf, df_resumen, acumulado_vendedores)

    print("\n✅ Proceso finalizado correctamente.")
    print(f"📄 Reporte generado en:\n{ruta_pdf}\n")


if __name__ == "__main__":

    if len(sys.argv) > 1:
        carpeta = sys.argv[1]
    else:
        carpeta = input("Ingrese la ruta de la carpeta con las planillas: ").strip()

    try:
        ejecutar_proceso(carpeta)
    except Exception as e:
        print(f"\n❌ Error durante el proceso: {e}\n")