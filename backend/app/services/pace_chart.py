"""The month-pace chart as a PNG, for the weekly recap email (mail clients run no scripts and drop SVG).

Same picture as the Dashboard's Spending This Month: cumulative spending by day of month, this month
in indigo with a light fill, last month in grey. Drawn at 4x and downsampled to 2x so lines are smooth.
"""
from __future__ import annotations

import io
from datetime import date

from PIL import Image, ImageDraw, ImageFont

W, H, SCALE = 600, 280, 4  # drawn at 4x, sent at 2x for sharp text on phones
LEFT, RIGHT, TOP, BOTTOM = 52, 64, 40, 28
INK, MUTED, GRID, GREY, ACCENT, FILL = "#111827", "#6b7280", "#eef0f3", "#c7ccd4", "#4f46e5", (79, 70, 229, 34)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size * SCALE)


def _nice_max(v: float) -> float:
    if v <= 0:
        return 100.0
    for step in (100, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000):
        if v / step <= 5:
            return step * (int(v // step) + 1)
    return v * 1.1


def _money(v: float) -> str:
    return f"${v:,.0f}" if v < 1000 else f"${v / 1000:.1f}K".replace(".0K", "K")


def _month_name(ym: str) -> str:
    return date.fromisoformat(f"{ym}-01").strftime("%b %Y")


def render_png(pace: dict) -> bytes:
    s = SCALE
    img = Image.new("RGBA", (W * s, H * s), "white")
    fill_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d, f = ImageDraw.Draw(img), _font(11)

    days = pace["days_in_month"]
    this, last = pace["this_month"], pace["last_month_series"]
    top = _nice_max(max([0.0, *this, *last]))
    x0, x1, y0, y1 = LEFT * s, (W - RIGHT) * s, TOP * s, (H - BOTTOM) * s

    def xy(i: int, v: float) -> tuple[float, float]:
        return x0 + (x1 - x0) * (i / max(1, days - 1)), y1 - (y1 - y0) * (v / top)

    for k in range(5):
        v = top * k / 4
        y = xy(0, v)[1]
        d.line([(x0, y), (x1, y)], fill=GRID, width=s)
        d.text((x0 - 8 * s, y), _money(v), fill=MUTED, font=f, anchor="rm")
    for day in sorted({1, 8, 15, 22, 29, days} - ({29} if days - 29 < 2 else set())):
        d.text((xy(day - 1, 0)[0], y1 + 8 * s), str(day), fill=MUTED, font=f, anchor="mt")

    if last:
        d.line([xy(i, v) for i, v in enumerate(last)], fill=GREY, width=3 * s, joint="curve")
    if this:
        pts = [xy(i, v) for i, v in enumerate(this)]
        ImageDraw.Draw(fill_layer).polygon([(pts[0][0], y1), *pts, (pts[-1][0], y1)], fill=FILL)
        img.alpha_composite(fill_layer)
        d = ImageDraw.Draw(img)
        if len(pts) > 1:
            d.line(pts, fill=ACCENT, width=4 * s, joint="curve")
        ex, ey = pts[-1]
        d.ellipse([ex - 4 * s, ey - 4 * s, ex + 4 * s, ey + 4 * s], fill=ACCENT)
        d.text((ex + 8 * s, ey), _money(pace["this_total"]), fill=ACCENT, font=_font(12), anchor="lm")

    # Legend, top left
    lx, ly = x0, 14 * s
    for label, color in ((_month_name(pace["month"]), ACCENT), (_month_name(pace["last_month"]), GREY)):
        d.line([(lx, ly), (lx + 18 * s, ly)], fill=color, width=4 * s)
        d.text((lx + 24 * s, ly), label, fill=INK, font=f, anchor="lm")
        lx += 24 * s + d.textlength(label, font=f) + 20 * s

    out = io.BytesIO()
    img.convert("RGB").resize((W * 2, H * 2), Image.LANCZOS).save(out, "PNG", optimize=True)
    return out.getvalue()
