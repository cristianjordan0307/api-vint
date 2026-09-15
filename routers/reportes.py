"""
routers/reportes.py — Exportación de reportes de ventas del vendedor (PDF / Excel).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from dependencies import get_current_user
from reportes.data import obtener_datos_reporte
from reportes.excel import generar_excel
from reportes.pdf import generar_pdf

router = APIRouter(prefix="/api/vendedor/reportes", tags=["Reportes"])


def _periodo_o_actual(anio: int | None, mes: int | None) -> tuple[int, int]:
    if anio and mes:
        return anio, mes
    ahora = datetime.utcnow()
    return ahora.year, ahora.month


@router.get("/pdf")
async def descargar_reporte_pdf(
    anio: int | None = Query(None, ge=2000, le=2100),
    mes: int | None = Query(None, ge=1, le=12),
    user=Depends(get_current_user),
):
    """Genera y descarga el reporte de ventas del vendedor autenticado en PDF (2 páginas)."""
    anio_r, mes_r = _periodo_o_actual(anio, mes)
    datos = obtener_datos_reporte(user, anio_r, mes_r)
    buf = generar_pdf(datos)
    nombre_archivo = f"reporte_ventas_{datos.vendedor_codigo}_{anio_r}-{mes_r:02d}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.get("/excel")
async def descargar_reporte_excel(
    anio: int | None = Query(None, ge=2000, le=2100),
    mes: int | None = Query(None, ge=1, le=12),
    user=Depends(get_current_user),
):
    """Genera y descarga el reporte de ventas del vendedor autenticado en Excel (4 hojas)."""
    anio_r, mes_r = _periodo_o_actual(anio, mes)
    datos = obtener_datos_reporte(user, anio_r, mes_r)
    buf = generar_excel(datos)
    nombre_archivo = f"reporte_ventas_{datos.vendedor_codigo}_{anio_r}-{mes_r:02d}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )
