"""The weekly recap as an email (subject, HTML, plain text). Read-only; the Cloudflare worker in
workers/weekly-recap/ fetches it every Monday and sends it, so nothing here talks to a mail server.

The HTML is a single table with inline styles: mail clients ignore stylesheets and most layout.
"""
from __future__ import annotations

from datetime import date
from html import escape

from app.services.weekly_recap import short_date, usd

INK, MUTED, RULE, ACCENT, GOOD, BAD = "#111827", "#6b7280", "#e5e7eb", "#4f46e5", "#047857", "#b91c1c"


def week_label(start: str, end: str) -> str:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    tail = f"{e.day}" if s.month == e.month else f"{e:%b} {e.day}"
    return f"{s:%b} {s.day} – {tail}, {e.year}"


def _signed(v: float) -> str:
    return ("+" if v >= 0 else "−") + usd(v)


def _row(left: str, right: str, sub: str = "") -> str:
    sub_html = f'<div style="color:{MUTED};font-size:12px">{escape(sub)}</div>' if sub else ""
    return (
        f'<tr><td style="padding:6px 0;border-bottom:1px solid {RULE}">{escape(left)}{sub_html}</td>'
        f'<td style="padding:6px 0;border-bottom:1px solid {RULE};text-align:right;white-space:nowrap">{escape(right)}</td></tr>'
    )


def _section(title: str, rows: list[str]) -> str:
    if not rows:
        return ""
    return (
        f'<h2 style="font-size:14px;margin:24px 0 4px;color:{INK}">{escape(title)}</h2>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;color:{INK}">{"".join(rows)}</table>'
    )


def render(r: dict, base_url: str) -> dict:
    label = week_label(r["week_start"], r["week_end"])
    link = f"{base_url.rstrip('/')}/recap?week={r['week_start']}"
    nw = r["net_worth_change"]
    subject = f"Weekly recap {label}: spent {usd(r['spending'])}" + (f", net worth {_signed(nw)}" if nw is not None else "")

    stats = [
        ("Spent", usd(r["spending"]), f"4-week avg {usd(r['prior_weekly_avg'])}", INK),
        ("Net worth", _signed(nw) if nw is not None else "—",
         f"now {usd(r['net_worth_end'])}" if r["net_worth_end"] is not None else "", GOOD if (nw or 0) >= 0 else BAD),
        ("Income", usd(r["income"]), "paychecks, interest", INK),
    ]
    stat_cells = "".join(
        f'<td width="33%" style="padding:12px;border:1px solid {RULE};border-radius:8px;vertical-align:top">'
        f'<div style="color:{MUTED};font-size:12px">{name}</div>'
        f'<div style="font-size:20px;font-weight:700;color:{color}">{escape(value)}</div>'
        f'<div style="color:{MUTED};font-size:12px">{escape(sub)}</div></td>'
        for name, value, sub, color in stats
    )
    categories = [_row(c["category"], usd(c["total"]), f"4-week avg {usd(c['prior_avg'])}") for c in r["categories"]]
    largest = [_row(t["merchant"], usd(t["amount"]), f"{short_date(t['date'])} · {t['category']}") for t in r["largest"]]
    coming = [_row(b["merchant"], f"~{usd(b['amount'])}", f"{short_date(b['date'])} · {b['category']}") for b in r["upcoming_bills"]]
    coming += [_row(f"RSU vest, {v['shares']} shares", f"~{usd(v['est_value'])}", short_date(v["date"])) for v in r["upcoming_vests"]]

    html = (
        f'<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px;color:{INK}">'
        f'<div style="color:{MUTED};font-size:12px;text-transform:uppercase;letter-spacing:.05em">Tallied · Weekly recap</div>'
        f'<h1 style="font-size:20px;margin:4px 0 12px">{escape(label)}</h1>'
        f'<p style="font-size:15px;line-height:1.5;margin:0 0 16px">{escape(r["headline"])}</p>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="6" style="border-collapse:separate"><tr>{stat_cells}</tr></table>'
        + _section("Where it went", categories)
        + _section("Largest purchases", largest)
        + _section("Coming up", coming)
        + (f'<p style="font-size:13px;color:{MUTED};margin-top:16px">{r["uncategorized"]} purchase(s) this week have no category.</p>' if r["uncategorized"] else "")
        + f'<p style="margin-top:24px"><a href="{escape(link)}" style="color:{ACCENT};font-weight:600">Open the recap in Tallied</a></p>'
        f'<p style="font-size:12px;color:{MUTED}">Sent every Monday from your Tallied data. Spending excludes transfers and card, loan and mortgage payments, net of refunds.</p>'
        "</div>"
    )

    lines = [f"Weekly recap {label}", "", r["headline"], "",
             f"Spent: {usd(r['spending'])} (4-week avg {usd(r['prior_weekly_avg'])})",
             f"Net worth: {_signed(nw) if nw is not None else '—'}", f"Income: {usd(r['income'])}"]
    for title, items in (("Where it went", [(c["category"], usd(c["total"])) for c in r["categories"]]),
                         ("Largest purchases", [(t["merchant"], usd(t["amount"])) for t in r["largest"]]),
                         ("Coming up", [(f"{short_date(b['date'])} {b['merchant']}", f"~{usd(b['amount'])}") for b in r["upcoming_bills"]]
                          + [(f"{short_date(v['date'])} RSU vest, {v['shares']} shares", f"~{usd(v['est_value'])}") for v in r["upcoming_vests"]])):
        if items:
            lines += ["", title] + [f"  {a}: {b}" for a, b in items]
    lines += ["", link]
    return {"subject": subject, "html": html, "text": "\n".join(lines), "week_start": r["week_start"]}
