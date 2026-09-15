"""
reportes/data.py — Agregación de datos reales para los reportes de ventas del vendedor.

Fuente única de verdad: la tabla `pedidos` (schema public), la misma que usa
routers/pedidos.py para "mis-ventas"/"mis-compras". Cada fila de `pedidos` es una
prenda vendida (comprador, vendedor, prenda, precio y estado ya vienen en la misma
fila — no existe una tabla de detalle separada). Se enriquece con `catalogo.prendas`
(categoría, marca, talla, color, condición).

Convención de ingresos (alineada con la vista seguridad.v_dashboard_vendedores que
ya usa routers/vendedor.py — verificado en vivo: ingresos_totales de la vista ==
SUM(precio), no SUM(total)):
- `precio` es el precio de la prenda y es la cifra de ingreso del vendedor.
- `total` = precio + parte proporcional del envío que paga el COMPRADOR — no es
  ingreso del vendedor, por eso no se usa en ningún cálculo de este reporte.

Resolución de nombre de comprador: mismo patrón de dos niveles que
routers/pedidos.py (get_mis_ventas) — primero seguridad.usuarios por
id_auth_supabase, si no hay match se usa direccion_envio.nombre (capturado en el
checkout), y si tampoco hay se muestra "Comprador".

Convención de estados (igual a la ya usada en routers/pedidos.py):
- 'completado'          → cuenta como ingreso real (KPIs, liquidación).
- 'pendiente'/'enviado' → en curso, se listan en el detalle pero NO entran en la
                           liquidación (aún no hay ingreso confirmado).
- 'cancelado'           → cuenta como venta bruta pero se resta para llegar a
                           "ventas válidas"; no genera comisión ni neto.
"""

from dataclasses import dataclass, field
from datetime import datetime
from calendar import monthrange

from config import get_settings
from supabase_client import get_admin_client
from utils.fechas import limites_mes, mes_anterior, periodo_label, variacion_pct


@dataclass
class FilaTransaccion:
    n: int
    id_pedido: str
    fecha: datetime
    id_prenda: int | None
    producto: str
    categoria: str
    marca: str
    talla: str
    color: str
    condicion: str
    comprador: str
    precio: float
    estado: str
    neto: float | None  # None cuando el pedido sigue en curso (pendiente/enviado)


@dataclass
class CategoriaResumen:
    nombre: str
    ingresos: float
    porcentaje: float


@dataclass
class ProductoTop:
    nombre: str
    unidades: int
    ingresos: float
    porcentaje: float


@dataclass
class CompradorRecurrente:
    nombre: str
    pedidos: int
    total_compradores: int
    compradores_recurrentes: int
    porcentaje_recurrencia: float


@dataclass
class ReporteDatos:
    vendedor_id: str
    vendedor_nombre: str
    vendedor_codigo: str
    anio: int
    mes: int
    periodo: str
    generado_en: datetime

    ingresos_validos: float
    ingresos_validos_var_pct: float | None
    pedidos_completados: int
    pedidos_completados_var_pct: float | None
    ticket_promedio: float
    ticket_promedio_var_pct: float | None
    prendas_vendidas: int
    prendas_vendidas_var_pct: float | None
    pedidos_en_curso: int

    ingresos_por_semana: list[tuple[str, float]]
    categorias: list[CategoriaResumen]
    producto_top: ProductoTop | None
    comprador_recurrente: CompradorRecurrente | None

    transacciones: list[FilaTransaccion] = field(default_factory=list)

    ventas_brutas: float = 0.0
    ventas_canceladas: float = 0.0
    ventas_validas: float = 0.0
    comision_pct: float = 0.0
    comision: float = 0.0
    neto_a_recibir: float = 0.0


def _nombre_usuario(user_obj) -> str:
    meta = getattr(user_obj, "user_metadata", None) or {}
    nombre = meta.get("full_name") or meta.get("name")
    if nombre:
        return nombre
    return getattr(user_obj, "email", None) or "Usuario"


def _codigo_vendedor(vendedor_id: str) -> str:
    return f"V-{vendedor_id.replace('-', '')[:4].upper()}"


def _mapa_nombres_compradores(admin_client, ids_usuario: set[str]) -> dict[str, str]:
    """
    Resuelve nombre por id_auth_supabase en seguridad.usuarios (mismo query que
    routers/pedidos.py::get_mis_ventas). Puede no encontrar nada si la cuenta no
    tiene ese vínculo poblado — en ese caso el llamador cae a direccion_envio.nombre.
    """
    if not ids_usuario:
        return {}
    try:
        resp = (
            admin_client.schema("seguridad")
            .from_("usuarios")
            .select("id_auth_supabase, primer_nombre, primer_apellido, correo")
            .in_("id_auth_supabase", list(ids_usuario))
            .execute()
        )
    except Exception:
        return {}

    nombres: dict[str, str] = {}
    for u in (resp.data or []):
        nombre_completo = f"{u.get('primer_nombre') or ''} {u.get('primer_apellido') or ''}".strip()
        nombres[str(u.get("id_auth_supabase"))] = nombre_completo or u.get("correo") or "Comprador"
    return nombres


def _nombre_comprador(fila: dict, mapa_nombres: dict[str, str]) -> str:
    uid = str(fila.get("user_id") or "")
    if uid in mapa_nombres:
        return mapa_nombres[uid]
    direccion = fila.get("direccion_envio") or {}
    if isinstance(direccion, dict) and direccion.get("nombre"):
        return direccion["nombre"]
    return "Comprador"


def _enriquecer_prendas(admin_client, ids_prenda: set[int]) -> dict[int, dict]:
    """Junta catalogo.prendas + categorias + marcas para las prendas vendidas del periodo."""
    if not ids_prenda:
        return {}

    prendas_resp = (
        admin_client.schema("catalogo")
        .from_("prendas")
        .select("id_prenda, id_categoria, id_marca, talla, color, condicion")
        .in_("id_prenda", list(ids_prenda))
        .execute()
    )
    prendas = prendas_resp.data or []

    ids_categoria = {p["id_categoria"] for p in prendas if p.get("id_categoria") is not None}
    ids_marca = {p["id_marca"] for p in prendas if p.get("id_marca") is not None}

    categorias_map: dict[int, str] = {}
    if ids_categoria:
        resp = (
            admin_client.schema("catalogo")
            .from_("categorias")
            .select("id_categoria, nombre")
            .in_("id_categoria", list(ids_categoria))
            .execute()
        )
        categorias_map = {c["id_categoria"]: c["nombre"] for c in (resp.data or [])}

    marcas_map: dict[int, str] = {}
    if ids_marca:
        resp = (
            admin_client.schema("catalogo")
            .from_("marcas")
            .select("id_marca, nombre")
            .in_("id_marca", list(ids_marca))
            .execute()
        )
        marcas_map = {m["id_marca"]: m["nombre"] for m in (resp.data or [])}

    enriquecido: dict[int, dict] = {}
    for p in prendas:
        enriquecido[p["id_prenda"]] = {
            "categoria": categorias_map.get(p.get("id_categoria"), "—"),
            "marca": marcas_map.get(p.get("id_marca"), "—"),
            "talla": p.get("talla") or "—",
            "color": p.get("color") or "—",
            "condicion": p.get("condicion") or "—",
        }
    return enriquecido


def _semanas_del_mes(anio: int, mes: int) -> list[tuple[int, int, str]]:
    """Buckets [(dia_inicio, dia_fin, etiqueta), ...] de ~7 días para el mes dado."""
    _, dias_en_mes = monthrange(anio, mes)
    buckets = []
    inicio = 1
    while inicio <= dias_en_mes:
        fin = min(inicio + 6, dias_en_mes)
        etiqueta = f"{inicio}–{fin}" if inicio != fin else f"{inicio}"
        buckets.append((inicio, fin, etiqueta))
        inicio = fin + 1
    return buckets


def _agregar_kpis(filas_completadas: list[dict]) -> tuple[float, int, float, int]:
    ingresos = sum(float(f.get("precio") or 0) for f in filas_completadas)
    pedidos = len(filas_completadas)
    ticket = ingresos / pedidos if pedidos > 0 else 0.0
    prendas = pedidos  # 1 fila de pedidos == 1 prenda vendida
    return ingresos, pedidos, ticket, prendas


def obtener_datos_reporte(user, anio: int, mes: int) -> ReporteDatos:
    """
    Punto de entrada único usado tanto por el generador de PDF como el de Excel.
    `user` es el objeto de usuario autenticado (de Depends(get_current_user)).
    """
    settings = get_settings()
    admin = get_admin_client()
    vendedor_id = str(user.id)

    inicio_mes, fin_mes = limites_mes(anio, mes)
    anio_ant, mes_ant = mes_anterior(anio, mes)
    inicio_mes_ant, fin_mes_ant = limites_mes(anio_ant, mes_ant)

    resp_actual = (
        admin.from_("pedidos")
        .select("id, user_id, id_prenda, titulo_prenda, precio, estado, direccion_envio, created_at")
        .eq("vendedor_id", vendedor_id)
        .gte("created_at", inicio_mes)
        .lt("created_at", fin_mes)
        .order("created_at", desc=True)
        .execute()
    )
    filas_mes = resp_actual.data or []

    resp_anterior = (
        admin.from_("pedidos")
        .select("precio, estado")
        .eq("vendedor_id", vendedor_id)
        .eq("estado", "completado")
        .gte("created_at", inicio_mes_ant)
        .lt("created_at", fin_mes_ant)
        .execute()
    )
    filas_mes_anterior_completadas = resp_anterior.data or []

    completadas = [f for f in filas_mes if f.get("estado") == "completado"]
    canceladas = [f for f in filas_mes if f.get("estado") == "cancelado"]
    en_curso = [f for f in filas_mes if f.get("estado") in ("pendiente", "enviado")]

    # ── Enriquecimiento en lote ──────────────────────────────────────────────
    ids_prenda = {f["id_prenda"] for f in filas_mes if f.get("id_prenda") is not None}
    prendas_info = _enriquecer_prendas(admin, ids_prenda)

    ids_usuario = {f["user_id"] for f in filas_mes if f.get("user_id")}
    mapa_nombres = _mapa_nombres_compradores(admin, ids_usuario)

    # ── KPIs mes actual / anterior ───────────────────────────────────────────
    ingresos_validos, pedidos_completados, ticket_promedio, prendas_vendidas = _agregar_kpis(completadas)
    ingresos_ant, pedidos_ant, ticket_ant, prendas_ant = _agregar_kpis(filas_mes_anterior_completadas)

    # ── Ingresos por semana (solo completados) ───────────────────────────────
    semanas = _semanas_del_mes(anio, mes)
    ingresos_semana = {etiqueta: 0.0 for _, _, etiqueta in semanas}
    for f in completadas:
        creado = f.get("created_at")
        if not creado:
            continue
        dia = datetime.fromisoformat(creado.replace("Z", "+00:00")).day
        for inicio, fin, etiqueta in semanas:
            if inicio <= dia <= fin:
                ingresos_semana[etiqueta] += float(f.get("precio") or 0)
                break
    ingresos_por_semana = [(etq, ingresos_semana[etq]) for _, _, etq in semanas]

    # ── Ventas por categoría (solo completados) ──────────────────────────────
    cat_ingresos: dict[str, float] = {}
    for f in completadas:
        info = prendas_info.get(f.get("id_prenda"), {})
        nombre_cat = info.get("categoria", "—")
        cat_ingresos[nombre_cat] = cat_ingresos.get(nombre_cat, 0.0) + float(f.get("precio") or 0)
    categorias = [
        CategoriaResumen(
            nombre=nombre,
            ingresos=ingresos,
            porcentaje=round((ingresos / ingresos_validos) * 100, 1) if ingresos_validos > 0 else 0.0,
        )
        for nombre, ingresos in sorted(cat_ingresos.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # ── Producto más vendido (solo completados) ──────────────────────────────
    producto_agg: dict[str, dict] = {}
    for f in completadas:
        clave = f.get("titulo_prenda") or "Prenda"
        acc = producto_agg.setdefault(clave, {"unidades": 0, "ingresos": 0.0})
        acc["unidades"] += 1
        acc["ingresos"] += float(f.get("precio") or 0)
    producto_top = None
    if producto_agg:
        nombre, acc = max(producto_agg.items(), key=lambda kv: kv[1]["ingresos"])
        producto_top = ProductoTop(
            nombre=nombre,
            unidades=acc["unidades"],
            ingresos=acc["ingresos"],
            porcentaje=round((acc["ingresos"] / ingresos_validos) * 100, 1) if ingresos_validos > 0 else 0.0,
        )

    # ── Comprador recurrente (solo completados) ──────────────────────────────
    comprador_agg: dict[str, int] = {}
    comprador_fila_ejemplo: dict[str, dict] = {}
    for f in completadas:
        uid = f.get("user_id")
        if uid:
            comprador_agg[uid] = comprador_agg.get(uid, 0) + 1
            comprador_fila_ejemplo.setdefault(uid, f)
    comprador_recurrente = None
    if comprador_agg:
        total_compradores = len(comprador_agg)
        recurrentes = sum(1 for c in comprador_agg.values() if c >= 2)
        uid_top, pedidos_top = max(comprador_agg.items(), key=lambda kv: kv[1])
        comprador_recurrente = CompradorRecurrente(
            nombre=_nombre_comprador(comprador_fila_ejemplo[uid_top], mapa_nombres),
            pedidos=pedidos_top,
            total_compradores=total_compradores,
            compradores_recurrentes=recurrentes,
            porcentaje_recurrencia=round((recurrentes / total_compradores) * 100, 1),
        )

    # ── Detalle de transacciones (todas las filas del periodo) ──────────────
    transacciones: list[FilaTransaccion] = []
    for i, f in enumerate(filas_mes, start=1):
        info = prendas_info.get(f.get("id_prenda"), {})
        estado = f.get("estado") or "—"
        precio = float(f.get("precio") or 0)
        if estado == "completado":
            neto = precio * (1 - settings.VINT_COMISION_PORCENTAJE)
        elif estado == "cancelado":
            neto = 0.0
        else:
            neto = None  # pendiente/enviado: aún no se liquida
        transacciones.append(FilaTransaccion(
            n=i,
            id_pedido=str(f.get("id", ""))[:8],
            fecha=datetime.fromisoformat(f["created_at"].replace("Z", "+00:00")) if f.get("created_at") else datetime.utcnow(),
            id_prenda=f.get("id_prenda"),
            producto=f.get("titulo_prenda") or "Prenda",
            categoria=info.get("categoria", "—"),
            marca=info.get("marca", "—"),
            talla=info.get("talla", "—"),
            color=info.get("color", "—"),
            condicion=info.get("condicion", "—"),
            comprador=_nombre_comprador(f, mapa_nombres),
            precio=precio,
            estado=estado,
            neto=neto,
        ))

    # ── Liquidación (solo estados finalizados: completado + cancelado) ───────
    ventas_brutas = sum(float(f.get("precio") or 0) for f in completadas + canceladas)
    ventas_canceladas = sum(float(f.get("precio") or 0) for f in canceladas)
    ventas_validas = ventas_brutas - ventas_canceladas  # == ingresos_validos
    comision = ventas_validas * settings.VINT_COMISION_PORCENTAJE
    neto_a_recibir = ventas_validas - comision

    return ReporteDatos(
        vendedor_id=vendedor_id,
        vendedor_nombre=_nombre_usuario(user),
        vendedor_codigo=_codigo_vendedor(vendedor_id),
        anio=anio,
        mes=mes,
        periodo=periodo_label(anio, mes),
        generado_en=datetime.utcnow(),
        ingresos_validos=ingresos_validos,
        ingresos_validos_var_pct=variacion_pct(ingresos_validos, ingresos_ant),
        pedidos_completados=pedidos_completados,
        pedidos_completados_var_pct=variacion_pct(pedidos_completados, pedidos_ant),
        ticket_promedio=ticket_promedio,
        ticket_promedio_var_pct=variacion_pct(ticket_promedio, ticket_ant),
        prendas_vendidas=prendas_vendidas,
        prendas_vendidas_var_pct=variacion_pct(prendas_vendidas, prendas_ant),
        pedidos_en_curso=len(en_curso),
        ingresos_por_semana=ingresos_por_semana,
        categorias=categorias,
        producto_top=producto_top,
        comprador_recurrente=comprador_recurrente,
        transacciones=transacciones,
        ventas_brutas=ventas_brutas,
        ventas_canceladas=ventas_canceladas,
        ventas_validas=ventas_validas,
        comision_pct=settings.VINT_COMISION_PORCENTAJE * 100,
        comision=comision,
        neto_a_recibir=neto_a_recibir,
    )
