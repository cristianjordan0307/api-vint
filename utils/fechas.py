"""
utils/fechas.py — Helpers de rangos de fecha para analítica y reportes del vendedor.
"""

from datetime import datetime

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def limites_mes(anio: int, mes: int) -> tuple[str, str]:
    """
    Retorna (inicio, fin) ISO en UTC de un mes calendario, con fin EXCLUSIVO
    (inicio del mes siguiente) para poder usarse directamente como .gte(inicio).lt(fin).
    """
    inicio = datetime(anio, mes, 1)
    anio_sig, mes_sig = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    fin = datetime(anio_sig, mes_sig, 1)
    return inicio.strftime("%Y-%m-%dT00:00:00Z"), fin.strftime("%Y-%m-%dT00:00:00Z")


def mes_anterior(anio: int, mes: int) -> tuple[int, int]:
    """Retorna (año, mes) del mes calendario inmediatamente anterior."""
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def periodo_label(anio: int, mes: int) -> str:
    """Ej: 'agosto 2026'."""
    return f"{MESES_ES[mes - 1]} {anio}"


def variacion_pct(actual: float, anterior: float) -> float | None:
    """
    % de variación de 'actual' respecto a 'anterior'.
    None cuando no hay base de comparación (mes anterior en cero).
    """
    if anterior > 0:
        return round(((actual - anterior) / anterior) * 100, 1)
    if actual > 0:
        return 100.0
    return None
