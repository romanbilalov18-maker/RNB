from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PORTFOLIO_DB = Path("data/virtual_portfolio.sqlite3")
AUDIT_DB = Path("data/decision_audit.sqlite")


def rows(path: Path, query: str, params=()):
    if not path.exists():
        return []
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in db.execute(query, params)]
        except sqlite3.Error:
            return []


def money(value):
    if value is None:
        return "—"
    return f"{value:,.2f}".replace(",", " ")


def build_data():
    portfolio = rows(PORTFOLIO_DB, "SELECT * FROM portfolio WHERE id=1")
    positions = rows(PORTFOLIO_DB, "SELECT ticker, quantity, average_price FROM positions ORDER BY ticker")
    trades = rows(PORTFOLIO_DB, "SELECT timestamp, ticker, side, quantity, price, commission, realized_pnl, reason FROM trades ORDER BY id DESC LIMIT 30")
    equity = rows(PORTFOLIO_DB, "SELECT timestamp, equity FROM equity_history ORDER BY id DESC LIMIT 100")
    decisions = rows(AUDIT_DB, "SELECT recorded_at, ticker, recommendation, reason, score, confidence, virtual_action, virtual_quantity, equity_complete FROM decision_audit ORDER BY id DESC LIMIT 30")
    audit_latest = rows(AUDIT_DB, "SELECT MAX(recorded_at) AS latest, COUNT(*) AS total FROM decision_audit")
    p = portfolio[0] if portfolio else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": p, "positions": positions, "trades": trades,
        "equity": list(reversed(equity)), "decisions": decisions,
        "audit": audit_latest[0] if audit_latest else None,
        "portfolio_db_exists": PORTFOLIO_DB.exists(),
        "audit_db_exists": AUDIT_DB.exists(),
    }


def render(data):
    p = data["portfolio"] or {}
    positions = data["positions"]
    trades = data["trades"]
    decisions = data["decisions"]
    equity = data["equity"]
    def esc(x): return html.escape(str(x if x is not None else "—"))
    def table(items, cols, empty):
        if not items:
            return f'<tr><td colspan="{len(cols)}" class="muted">{empty}</td></tr>'
        return "".join("<tr>" + "".join(f"<td>{esc(item.get(k))}</td>" for k, _ in cols) + "</tr>" for item in items)
    equity_json = json.dumps(equity, ensure_ascii=False).replace("</", "<\\/")
    status = "База портфеля найдена" if data["portfolio_db_exists"] else "Нет сохранённой базы портфеля"
    last = (data["audit"] or {}).get("latest") or "Нет записей"
    total = p.get("initial_balance")
    cash = p.get("cash")
    pnl = p.get("realized_pnl")
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><title>RNB — дашборд</title>
<style>
:root{{color-scheme:dark;--bg:#0b1020;--panel:#131b2e;--line:#26334c;--text:#edf2ff;--muted:#9ba9c3;--accent:#7c9cff;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,-apple-system,sans-serif}}main{{max-width:1200px;margin:auto;padding:24px}}header,.top,.cards{{display:flex;gap:14px;flex-wrap:wrap;align-items:center;justify-content:space-between}}h1{{margin:0;font-size:28px}}h2{{font-size:17px;margin:0 0 14px}}.muted{{color:var(--muted)}}.pill{{border:1px solid #326b58;color:#8de0bd;border-radius:99px;padding:6px 10px;font-size:12px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));margin:22px 0}}.panel,.metric{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;min-width:0}}.value{{font-size:25px;font-weight:700;margin-top:8px;overflow-wrap:anywhere}}.grid{{display:grid;grid-template-columns:1.2fr 1fr;gap:16px}}.wide{{grid-column:1/-1}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:10px 8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--muted);font-weight:500}}.scroll{{overflow:auto}}canvas{{width:100%;height:220px}}footer{{margin-top:20px;color:var(--muted);font-size:12px}}button{{background:var(--accent);color:#071022;border:0;border-radius:10px;padding:9px 13px;font-weight:700}}@media(max-width:760px){{main{{padding:14px}}.grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}h1{{font-size:23px}}}}
</style></head><body><main>
<header><div><h1>RNB <span class="muted">/ Дашборд</span></h1><div class="muted">Виртуальная торговля · только просмотр</div></div><div class="top"><span class="pill">PAPER MODE</span><button onclick="location.reload()">Обновить</button></div></header>
<div class="cards">
<div class="metric"><div class="muted">Начальный баланс</div><div class="value">{money(total)}</div></div>
<div class="metric"><div class="muted">Свободные деньги</div><div class="value">{money(cash)}</div></div>
<div class="metric"><div class="muted">Реализованный P/L</div><div class="value">{money(pnl)}</div></div>
<div class="metric"><div class="muted">Комиссии всего</div><div class="value">{money(p.get("commissions"))}</div></div>
<div class="metric"><div class="muted">Защищённый резерв</div><div class="value">{money(p.get("protected_cash"))}</div></div>
<div class="metric"><div class="muted">Открытых позиций</div><div class="value">{len(positions)}</div></div>
</div>
<div class="grid">
<section class="panel"><h2>История оценки портфеля</h2><canvas id="chart" aria-label="График истории оценки портфеля"></canvas><div class="muted">Только сохранённые значения из SQLite; пустой график означает отсутствие истории.</div></section>
<section class="panel"><h2>Состояние данных</h2><p>{esc(status)}</p><p class="muted">Последняя запись журнала решений: {esc(last)}</p><p class="muted">Журнал аудита: {"доступен" if data["audit_db_exists"] else "не найден"}</p><p class="muted">HTML создан: {esc(data["generated_at"])}</p><p class="muted">Данные не обновляются в реальном времени: файл отражает состояние на момент создания.</p></section>
<section class="panel wide"><h2>Открытые позиции</h2><div class="scroll"><table><thead><tr><th>Тикер</th><th>Количество</th><th>Средняя цена</th></tr></thead><tbody>{table(positions,[("ticker",""),("quantity",""),("average_price","")],"Нет открытых позиций или база отсутствует")}</tbody></table></div></section>
<section class="panel wide"><h2>Последние решения</h2><div class="scroll"><table><thead><tr><th>Время</th><th>Тикер</th><th>Рекомендация</th><th>Действие</th><th>Кол-во</th><th>Уверенность</th><th>Причина</th></tr></thead><tbody>{table(decisions,[("recorded_at",""),("ticker",""),("recommendation",""),("virtual_action",""),("virtual_quantity",""),("confidence",""),("reason","")],"Записей решений пока нет")}</tbody></table></div></section>
<section class="panel wide"><h2>История виртуальных сделок</h2><div class="scroll"><table><thead><tr><th>Время</th><th>Тикер</th><th>Сторона</th><th>Количество</th><th>Цена</th><th>Комиссия</th><th>Реализованный P/L</th><th>Причина</th></tr></thead><tbody>{table(trades,[("timestamp",""),("ticker",""),("side",""),("quantity",""),("price",""),("commission",""),("realized_pnl",""),("reason","")],"Сделок пока нет")}</tbody></table></div></section>
</div><footer>RNB Dashboard · read-only · реальные ордера отсюда не отправляются. Значения без данных не заменяются демо-цифрами.</footer>
</main><script>
const points={equity_json};const c=document.getElementById('chart'),ctx=c.getContext('2d');function draw(){{const dpr=devicePixelRatio||1;c.width=c.clientWidth*dpr;c.height=220*dpr;ctx.scale(dpr,dpr);const w=c.clientWidth,h=220;ctx.clearRect(0,0,w,h);if(points.length<2){{ctx.fillStyle='#9ba9c3';ctx.fillText('Недостаточно точек для графика',12,30);return}}const vals=points.map(x=>Number(x.equity)).filter(Number.isFinite);if(vals.length<2)return;const lo=Math.min(...vals),hi=Math.max(...vals),span=hi-lo||1;ctx.strokeStyle='#7c9cff';ctx.lineWidth=2;ctx.beginPath();vals.forEach((v,i)=>{{const x=10+i*(w-20)/(vals.length-1),y=h-12-(v-lo)/span*(h-24);i?ctx.lineTo(x,y):ctx.moveTo(x,y)}});ctx.stroke();ctx.fillStyle='#9ba9c3';ctx.fillText(lo.toFixed(2),10,h-2);ctx.fillText(hi.toFixed(2),10,14)}}draw();addEventListener('resize',draw);
</script></body></html>"""


if __name__ == "__main__":
    output = Path("artifacts/dashboard.html")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(build_data()), encoding="utf-8")
    print(f"Dashboard generated: {output}")
