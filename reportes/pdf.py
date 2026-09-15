"""
reportes/pdf.py — Genera el PDF de 2 páginas del reporte de ventas con reportlab.

A diferencia del mockup (que mostraba solo los últimos 8 pedidos por espacio de
maqueta), aquí se listan TODAS las transacciones del periodo — truncar datos reales
de un reporte financiero sería incorrecto aunque el mockup lo haga por espacio.
Platypus pagina la tabla automáticamente si no cabe en una sola página.
"""

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, Flowable,
)
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.graphics.shapes import Drawing, Rect, String

from reportes.data import ReporteDatos

INK = colors.HexColor("#1E1814")
MUTED = colors.HexColor("#6B5A4D")
ACCENT = colors.HexColor("#8A5A3C")
LINE = colors.HexColor("#D8CBB8")
FAINT_BAR = colors.HexColor("#DDD0BF")

LOGO_PATH = Path(__file__).resolve().parents[2] / "public" / "img" / "logo1.png"

styles = {
    "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=8, textColor=MUTED, leading=10),
    "value": ParagraphStyle("value", fontName="Helvetica-Bold", fontSize=20, textColor=INK, leading=22),
    "trend_up": ParagraphStyle("trend_up", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT),
    "trend_down": ParagraphStyle("trend_down", fontName="Helvetica-Bold", fontSize=9, textColor=MUTED),
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=26, textColor=INK, leading=28, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=14, textColor=INK, leading=16, spaceAfter=4),
    "meta_label": ParagraphStyle("meta_label", fontName="Helvetica-Bold", fontSize=7, textColor=MUTED),
    "meta_value": ParagraphStyle("meta_value", fontName="Helvetica-Bold", fontSize=10, textColor=INK),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#4A3B31"), leading=13),
    "small_muted": ParagraphStyle("small_muted", fontName="Helvetica", fontSize=8, textColor=MUTED),
    "section_sub": ParagraphStyle("section_sub", fontName="Helvetica", fontSize=8.5, textColor=MUTED, spaceAfter=8),
    "kicker": ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=10, textColor=INK, alignment=TA_RIGHT),
}


def money(v: float) -> str:
    return f"${v:,.0f}".replace(",", ".")


def _header(subtitulo: str) -> Table:
    logo_cell = ""
    if LOGO_PATH.exists():
        try:
            logo_cell = Image(str(LOGO_PATH), width=22, height=22)
        except Exception:
            logo_cell = ""
    marca = Paragraph(
        '<font color="#8A5A3C" size="18"><b>VINT</b></font>', styles["body"]
    )
    izquierda = Table([[logo_cell, marca]], colWidths=[24, 60]) if logo_cell else marca
    if logo_cell:
        izquierda.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
    derecha = Paragraph(subtitulo.upper(), styles["kicker"])
    t = Table([[izquierda, derecha]], colWidths=[296, 220])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -1), 2, INK),
    ]))
    return t


def _meta_row(d: ReporteDatos) -> Table:
    campos = [
        ("VENDEDOR", d.vendedor_nombre),
        ("CÓDIGO", f"#{d.vendedor_codigo}"),
        ("PERIODO", d.periodo.capitalize()),
        ("GENERADO", d.generado_en.strftime("%d %b %Y")),
    ]
    data = [[Paragraph(lbl, styles["meta_label"]) for lbl, _ in campos],
            [Paragraph(val, styles["meta_value"]) for _, val in campos]]
    t = Table(data, colWidths=[129] * 4)
    t.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("LINEABOVE", (0, 0), (-1, 0), 2, colors.Color(0.11, 0.09, 0.08, 0.4)),
        ("LINEBELOW", (0, 1), (-1, 1), 2, colors.Color(0.11, 0.09, 0.08, 0.4)),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, LINE),
    ]))
    return t


def _tendencia(var_pct: float | None) -> Paragraph:
    if var_pct is None:
        return Paragraph("Sin datos del mes anterior", styles["trend_down"])
    signo = "+" if var_pct >= 0 else "-"
    estilo = "trend_up" if var_pct >= 0 else "trend_down"
    return Paragraph(f"{signo}{abs(var_pct):.1f}% vs. mes anterior", styles[estilo])


def _kpi_cards(d: ReporteDatos) -> Table:
    tarjetas = [
        ("INGRESOS VÁLIDOS", money(d.ingresos_validos), d.ingresos_validos_var_pct),
        ("PEDIDOS COMPLETADOS", str(d.pedidos_completados), d.pedidos_completados_var_pct),
        ("TICKET PROMEDIO", money(d.ticket_promedio), d.ticket_promedio_var_pct),
        ("PRENDAS VENDIDAS", str(d.prendas_vendidas), d.prendas_vendidas_var_pct),
    ]
    fila = []
    for etiqueta, valor, var in tarjetas:
        cell = [
            [Paragraph(etiqueta, styles["label"])],
            [Paragraph(valor, styles["value"])],
            [_tendencia(var)],
        ]
        fila.append(Table(cell, rowHeights=[14, 26, 14]))
    t = Table([fila], colWidths=[129] * 4)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def _barra_categoria(pct: float, ancho=130, alto=9) -> Drawing:
    d = Drawing(ancho, alto)
    d.add(Rect(0, 0, ancho, alto, fillColor=FAINT_BAR, strokeColor=None))
    d.add(Rect(0, 0, max(2, ancho * min(pct, 100) / 100), alto, fillColor=ACCENT, strokeColor=None))
    return d


def _grafico_categorias(d: ReporteDatos) -> Table:
    if not d.categorias:
        return Table([[Paragraph("Sin ventas completadas en este periodo.", styles["small_muted"])]])
    filas = []
    for cat in d.categorias[:8]:
        etiqueta = Paragraph(
            f'{cat.nombre} <font color="#6B5A4D">{money(cat.ingresos)} · {cat.porcentaje:.0f}%</font>',
            ParagraphStyle("catrow", fontName="Helvetica-Bold", fontSize=9, textColor=INK),
        )
        filas.append([etiqueta])
        filas.append([_barra_categoria(cat.porcentaje)])
    t = Table(filas, colWidths=[220])
    t.setStyle(TableStyle([("TOPPADDING", (0, 1), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -2), 4)]))
    return t


def _grafico_semanal(d: ReporteDatos) -> Drawing:
    datos = d.ingresos_por_semana
    ancho, alto = 220, 130
    dr = Drawing(ancho, alto)
    if not datos or all(v == 0 for _, v in datos):
        dr.add(String(0, alto / 2, "Sin ventas completadas en este periodo.", fontSize=8, fillColor=MUTED))
        return dr
    max_v = max(v for _, v in datos) or 1
    n = len(datos)
    gap = 8
    bar_w = (ancho - gap * (n - 1)) / n
    base_y = 22
    max_bar_h = alto - 40
    for i, (etiqueta, valor) in enumerate(datos):
        x = i * (bar_w + gap)
        h = (valor / max_v) * max_bar_h if max_v else 0
        color = ACCENT if valor == max_v else FAINT_BAR
        dr.add(Rect(x, base_y, bar_w, h, fillColor=color, strokeColor=None))
        dr.add(String(x, base_y + h + 4, f"{valor/1000:,.0f}k".replace(",", "."), fontSize=6.5, fillColor=MUTED))
        dr.add(String(x, base_y - 12, etiqueta, fontSize=6.5, fillColor=MUTED))
    dr.add(Rect(0, base_y - 2, ancho, 1.2, fillColor=INK, strokeColor=None))
    return dr


def _highlights(d: ReporteDatos) -> Table:
    prod = d.producto_top
    comp = d.comprador_recurrente
    prod_txt = (
        f"<b>{prod.nombre}</b><br/><font color='#4A3B31' size=8>{prod.unidades} unidades · {money(prod.ingresos)} · "
        f"{prod.porcentaje:.0f}% de tus ingresos</font>" if prod else "Sin ventas completadas en este periodo."
    )
    comp_txt = (
        f"<b>{comp.compradores_recurrentes} de {comp.total_compradores} compradores</b><br/>"
        f"<font color='#4A3B31' size=8>{comp.porcentaje_recurrencia:.0f}% repitió compra · más frecuente: {comp.nombre} "
        f"({comp.pedidos} pedidos)</font>" if comp else "Sin compradores este periodo."
    )
    t = Table([
        [Paragraph("PRODUCTO MÁS VENDIDO", styles["label"]), Paragraph("COMPRADORES RECURRENTES", styles["label"])],
        [Paragraph(prod_txt, styles["body"]), Paragraph(comp_txt, styles["body"])],
    ], colWidths=[258, 258])
    t.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, 0), 4), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _tabla_transacciones(d: ReporteDatos) -> Table:
    encabezado = ["Fecha", "Pedido", "Producto", "Comprador", "Precio", "Estado", "Neto"]
    filas = [encabezado]
    for t in d.transacciones:
        neto = money(t.neto) if t.neto is not None else "—"
        filas.append([
            t.fecha.strftime("%d %b"), t.id_pedido, t.producto, t.comprador,
            money(t.precio), t.estado, neto,
        ])
    tabla = Table(filas, colWidths=[45, 45, 130, 80, 55, 60, 55], repeatRows=1)
    estilo = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, INK),
        ("LINEABOVE", (0, 0), (-1, 0), 1.2, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
        ("ALIGN", (6, 0), (6, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _tabla_liquidacion(d: ReporteDatos) -> list:
    filas = [
        ["Ventas brutas", money(d.ventas_brutas)],
        ["Ventas canceladas", f"– {money(d.ventas_canceladas)}"],
        ["Ventas válidas", money(d.ventas_validas)],
        [f"Comisión VINT ({d.comision_pct:.0f}%)", f"– {money(d.comision)}"],
    ]
    t = Table(filas, colWidths=[160, 110])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
        ("LINEBELOW", (0, -1), (-1, -1), 1.5, INK),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    total = Table([
        [Paragraph("TOTAL NETO A RECIBIR", styles["label"])],
        [Paragraph(money(d.neto_a_recibir), ParagraphStyle("neto", fontName="Helvetica-Bold", fontSize=22, textColor=ACCENT))],
    ])
    return [t, Spacer(1, 10), total]


class _NumberedCanvas(pdfcanvas.Canvas):
    def __init__(self, *args, **kwargs):
        pdfcanvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_states = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for i, state in enumerate(self._saved_states, start=1):
            self.__dict__.update(state)
            self._draw_footer(i, total)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)

    def _draw_footer(self, pagina: int, total: int):
        self.setStrokeColor(LINE)
        self.setLineWidth(0.5)
        self.line(48, 40, LETTER[0] - 48, 40)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(MUTED)
        self.drawString(48, 28, "VINT · Documento informativo, no es una factura electrónica")
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(INK)
        self.drawRightString(LETTER[0] - 48, 28, f"Página {pagina} / {total}")


def generar_pdf(d: ReporteDatos) -> BytesIO:
    buf = BytesIO()
    doc = BaseDocTemplate(buf, pagesize=LETTER, topMargin=44, bottomMargin=56, leftMargin=48, rightMargin=48)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="pagina", frames=[frame])])

    story: list[Flowable] = []

    # ── Página 1: resumen ────────────────────────────────────────────────────
    story.append(_header("Reporte de ventas"))
    story.append(Spacer(1, 10))
    story.append(_meta_row(d))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Resumen mensual de ventas", styles["h1"]))
    story.append(_kpi_cards(d))
    story.append(Spacer(1, 20))

    graficos = Table([[
        [Paragraph("Tendencia de ingresos", styles["h2"]),
         Paragraph("Por semana del periodo · pesos colombianos", styles["section_sub"]),
         _grafico_semanal(d)],
        [Paragraph("Ventas por categoría", styles["h2"]),
         Paragraph("Participación sobre ingresos válidos", styles["section_sub"]),
         _grafico_categorias(d)],
    ]], colWidths=[258, 258])
    graficos.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (-1, 0), 2, colors.Color(0.11, 0.09, 0.08, 0.4)), ("TOPPADDING", (0, 0), (-1, -1), 10)]))
    story.append(graficos)
    story.append(Spacer(1, 16))
    story.append(_highlights(d))
    story.append(PageBreak())

    # ── Página 2: transacciones + liquidación ────────────────────────────────
    story.append(_header("Transacciones y liquidación"))
    story.append(Spacer(1, 14))
    story.append(Paragraph("Detalle de transacciones", styles["h2"]))
    story.append(Paragraph(f"{len(d.transacciones)} pedido(s) del periodo.", styles["section_sub"]))
    story.append(_tabla_transacciones(d))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f'"Neto" es el valor después de la comisión VINT del {d.comision_pct:.0f}%. '
        "Los pedidos cancelados no generan comisión; los pedidos en curso aún no se liquidan.",
        styles["small_muted"],
    ))
    story.append(Spacer(1, 20))
    story.append(Paragraph("Liquidación del periodo", styles["h2"]))
    story.append(Spacer(1, 6))
    cuerpo = Table([[
        Paragraph(
            "La liquidación toma las ventas brutas del periodo (pedidos completados y cancelados), descuenta los "
            f"pedidos cancelados y aplica la comisión VINT del {d.comision_pct:.0f}% únicamente sobre las ventas válidas. "
            "Los pedidos aún en curso (pendiente/enviado) no se incluyen hasta que se completen.",
            styles["body"],
        ),
        _tabla_liquidacion(d),
    ]], colWidths=[276, 240])
    cuerpo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(cuerpo)

    doc.build(story, canvasmaker=_NumberedCanvas)
    buf.seek(0)
    return buf
