"""Демо-сайт для проверки скилла без сайта оператора: вымышленный кабинет игрока с личными данными и кассой.

  python3 server.py 8765      страница на http://127.0.0.1:8765/ (только этот компьютер), остановка Ctrl+C

Все данные на странице вымышлены. На них видно, что размывается (почта, ID, телефон, карта, имя из steps.json)
и что кнопку оплаты рекордер не нажимает (шаг point).
"""
import http.server, sys

PAGE = '''<!doctype html><html lang="uk"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Demo Casino</title>
<style>body{margin:0;font:16px -apple-system,Arial,sans-serif;background:#14161f;color:#eee}
header{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#1d2030}
.btn{background:#2f6bff;color:#fff;border:0;border-radius:10px;padding:12px 18px;font-size:16px}
.card{margin:16px;padding:16px;border-radius:14px;background:#1d2030}.row{margin:10px 0}
input{font-size:18px;padding:10px;border-radius:8px;border:1px solid #444;background:#0e1018;color:#fff;width:140px}
.chips{display:flex;gap:8px;flex-wrap:wrap}.chip{background:#2a2e44;color:#fff;border:0;border-radius:18px;padding:8px 14px;font-size:15px}</style>
<header><b>Demo Casino</b><button class="btn" id="dep">Поповнити</button></header>
<div class="card"><div class="row">Привіт, Eugene</div><div class="row">Пошта: player@example.com</div><div class="row">ID 4815162</div>
<div class="row">Телефон: +380 00 123 45 67</div><div class="row">Картка •••• 4242</div><div class="row">Баланс 1 250,00 ₴</div></div>
<div class="card" id="cash" hidden><div class="row">Спосіб оплати</div><div class="chips"><button class="chip">Картка</button><button class="chip">Переказ</button></div>
<form onsubmit="event.preventDefault()"><div class="row">Сума <input id="amount" inputmode="decimal" value="500"></div>
<button class="btn" type="submit">Поповнити рахунок</button></form></div>
<script>document.getElementById('dep').onclick = () => { document.getElementById('cash').hidden = false; document.getElementById('dep').textContent = 'Каса'; };</script></html>'''

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        body = PAGE.encode()
        self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f'демо-сайт: http://127.0.0.1:{port}/  (Ctrl+C, чтобы остановить)', flush=True)
    http.server.ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
