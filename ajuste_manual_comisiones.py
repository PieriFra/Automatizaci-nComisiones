"""
ajuste_manual_comisiones.py
============================
Ajuste puntual (por única vez) para 6 planillas donde se determinó que
ciertas facturas de ciertos clientes, con fecha de factura desde el
30/05/2026 en adelante, NO deben comisionarse.

Este script es independiente del flujo normal: NO modifica
planilla_parser.py ni DistribucionMensualCom.py. Lee las tablas de los
PDFs afectados por su cuenta, excluye las facturas puntuales, y
recalcula subtotales / total / distribución de comisiones por vendedor
reutilizando la misma función de negocio ya existente
(calcular_comisiones_vendedores) sobre los datos corregidos.

Uso:
    python ajuste_manual_comisiones.py "/ruta/a/PlanillasCobranza"
"""

from __future__ import annotations

import os
import sys
from datetime import date
from collections import defaultdict

import pdfplumber

from planilla_parser import _RX_IMPORTE, _parse_monto, _normalizar, _limpiar_nombre
from DistribucionMensualCom import calcular_comisiones_vendedores
from pdf_reader import detectar_empresa
from clientes_vendedor import MAPA_CLIENTES_DP, MAPA_CLIENTES_FILLS

# ---------------------------------------------------------------------------
# Configuración del ajuste puntual
# ---------------------------------------------------------------------------

PLANILLAS_AJUSTAR = [
    "Planilla de Cobranza N° 08 Fills (1).pdf",
    "Planilla de Cobranza N° 09 Fills (1).pdf",
    "Planilla de Cobranza DP N° 99 (1).pdf",
    "Planilla de Cobranza DP N° 98 (1).pdf",
    "Planilla de Cobranza DP N° 97 (1).pdf",
    "Planilla de Cobranza DP N° 96 (1).pdf",
]

CLIENTES_EXCLUIR = {
    _normalizar(c) for c in [
        "VACA DANIEL JAVIER",
        "GENERO ZUNILDA ISABEL NORMA",
        "SENA JOSE MARIA CONCEPCION",
        "SANTIAGO ZAMPA",
        "PERSOGLIA GONZALO EDUARDO",
        "YACCUZZI DISTRIBUCIONES SRL",
        "AGUILAR CRISTIAN FABIAN Y NOCENTI SERGIO HERNAN",
    ]
}

FECHA_CORTE = date(2026, 5, 30)  # se excluyen facturas con fecha >= a esta

_NO_CLIENTE = {
    "CLIENTE", "SUBTOTAL", "TOTAL",
    "COMISIONES", "COMISION",
    "FLETES", "REPARTO", "RETIRO", "EFECTIVO",
}


# ---------------------------------------------------------------------------
# Extracción de facturas individuales (planillas tipo 1 — tabla pdfplumber)
# ---------------------------------------------------------------------------

def _parsear_fecha(cadena: str) -> date | None:
    cadena = (cadena or "").replace("\n", "").strip()
    partes = cadena.split("-")
    if len(partes) != 3:
        return None
    try:
        d, m, y = partes
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def extraer_facturas(pdf_path: str) -> list[dict]:
    """Devuelve una lista de facturas individuales: cliente, factura, fecha, importe."""
    filas = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for tabla in page.extract_tables():
                filas.extend(tabla)

    facturas = []
    for fila in filas:
        if not fila or not fila[0]:
            continue

        celda0 = _limpiar_nombre(fila[0])
        celda0_up = celda0.upper()
        primera_palabra = celda0_up.split()[0] if celda0_up.split() else ""

        # Descarta encabezados, filas de SUBTOTAL/TOTAL/COMISIONES y demás
        if primera_palabra in _NO_CLIENTE:
            continue

        importe_raw = (fila[8] or "").strip() if len(fila) > 8 else ""
        m = _RX_IMPORTE.search(importe_raw)
        if not m:
            # Filas "basura" (bloques de texto sin estructura de tabla real)
            continue

        factura = _limpiar_nombre(fila[6]) if len(fila) > 6 and fila[6] else ""
        fecha_raw = fila[7] if len(fila) > 7 else ""

        facturas.append({
            "cliente": celda0,
            "factura": factura,
            "fecha": _parsear_fecha(fecha_raw),
            "importe": _parse_monto(m.group(1)),
        })

    return facturas


# ---------------------------------------------------------------------------
# Recalculo por planilla
# ---------------------------------------------------------------------------

def recalcular_planilla(pdf_path: str) -> dict:
    facturas = extraer_facturas(pdf_path)
    empresa = detectar_empresa(pdf_path)
    mapa_empresa = MAPA_CLIENTES_DP if empresa == "DP" else MAPA_CLIENTES_FILLS

    subtotales_orig = defaultdict(float)
    subtotales_ajus = defaultdict(float)
    excluidas = []

    for f in facturas:
        subtotales_orig[f["cliente"]] += f["importe"]

        excluir = (
            _normalizar(f["cliente"]) in CLIENTES_EXCLUIR
            and f["fecha"] is not None
            and f["fecha"] >= FECHA_CORTE
        )
        if excluir:
            excluidas.append(f)
        else:
            subtotales_ajus[f["cliente"]] += f["importe"]

    total_orig = sum(subtotales_orig.values())
    total_ajus = sum(subtotales_ajus.values())

    dist_orig = calcular_comisiones_vendedores(dict(subtotales_orig), mapa_empresa, empresa, tipo_informe=1)
    dist_ajus = calcular_comisiones_vendedores(dict(subtotales_ajus), mapa_empresa, empresa, tipo_informe=1)

    return {
        "empresa": empresa,
        "facturas_excluidas": excluidas,
        "subtotales_original": dict(subtotales_orig),
        "subtotales_ajustado": dict(subtotales_ajus),
        "total_original": total_orig,
        "total_ajustado": total_ajus,
        "dist_original": dist_orig,
        "dist_ajustada": dist_ajus,
    }


# ---------------------------------------------------------------------------
# Reporte en consola
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    return f"${v:,.2f}"


def main(carpeta: str) -> None:
    acumulado_diff_vendedores = defaultdict(float)
    diff_total_general = 0.0

    for nombre in PLANILLAS_AJUSTAR:
        pdf_path = os.path.join(carpeta, nombre)
        if not os.path.exists(pdf_path):
            print(f"⚠️  No se encontró: {nombre}")
            continue

        r = recalcular_planilla(pdf_path)

        print(f"\n{'='*78}\n{nombre}  ({r['empresa']})\n{'='*78}")

        print("Facturas excluidas del cálculo de comisión:")
        if not r["facturas_excluidas"]:
            print("  (ninguna)")
        for f in r["facturas_excluidas"]:
            print(f"  - {f['cliente']:48s} Nro {f['factura']:16s} "
                  f"Fecha {f['fecha']}  {_fmt(f['importe'])}")

        print(f"\nTotal original : {_fmt(r['total_original'])}")
        print(f"Total ajustado : {_fmt(r['total_ajustado'])}")
        diff_total = r["total_ajustado"] - r["total_original"]
        diff_total_general += diff_total
        print(f"Diferencia     : {_fmt(diff_total)}")

        print("\nDistribución por vendedor (original → ajustada):")
        vendedores = sorted(set(r["dist_original"]) | set(r["dist_ajustada"]))
        for v in vendedores:
            orig = r["dist_original"].get(v, 0.0)
            ajus = r["dist_ajustada"].get(v, 0.0)
            diff = ajus - orig
            acumulado_diff_vendedores[v] += diff
            print(f"  {v:22s} {_fmt(orig):>18s}  ->  {_fmt(ajus):>18s}   (diff {_fmt(diff)})")

    print(f"\n{'='*78}\nRESUMEN DEL AJUSTE (para aplicar sobre el informe mensual ya generado)\n{'='*78}")
    print(f"Diferencia total en TOTAL cobrado (suma de las 6 planillas): {_fmt(diff_total_general)}")
    print("\nAjuste neto por vendedor (restar de la distribución mensual actual):")
    for v, diff in sorted(acumulado_diff_vendedores.items()):
        print(f"  {v:22s} {_fmt(diff)}")


if __name__ == "__main__":
    carpeta_arg = sys.argv[1] if len(sys.argv) > 1 else input("Ruta de la carpeta con las planillas: ").strip()
    main(carpeta_arg)
