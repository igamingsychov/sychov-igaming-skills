#!/usr/bin/env python3
"""show: запись экрана -> видеоинструкция.

  python3 show.py check                    что установлено (ffmpeg, браузер для подписей)
  python3 show.py prep <video> [--out DIR] разбор записи: где экран менялся, кадры с линейкой для модели, prep.json
  python3 show.py render <DIR> [--lang ru] сборка роликов по DIR/plan.json (его пишет модель по кадрам)

Только стандартная библиотека Python. Видео режет ffmpeg, подписи и рамку рисует установленный браузер (Chrome, Edge или Chromium)
в прозрачные PNG. Все файлы остаются на компьютере пользователя.
"""
import argparse, base64, concurrent.futures, threading, datetime, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
OVERLAY = os.path.join(HERE, 'overlay.html')
FPS = 30
L10N = {  # служебные слова заставок; подписи шагов пишет модель
    'ru': dict(kicker='Инструкция', sub='Шагов: {n} · {s} сек', done='Готово', help='Не получилось? Напиши в поддержку'),
    'uk': dict(kicker='Інструкція', sub='Кроків: {n} · {s} сек', done='Готово', help='Не вийшло? Напиши в підтримку'),
    'en': dict(kicker='Guide', sub='{n} steps · {s} sec', done='Done', help='Something went wrong? Contact support'),
    'es': dict(kicker='Guía', sub='{n} pasos · {s} s', done='Listo', help='Si algo no funciona, escribe a soporte'),
    'pt': dict(kicker='Guia', sub='{n} passos · {s} s', done='Pronto', help='Se algo não funcionar, fale com o suporte'),
    'de': dict(kicker='Anleitung', sub='{n} Schritte · {s} Sek.', done='Fertig', help='Wenn etwas nicht klappt, schreib dem Support'),
    'fr': dict(kicker='Guide', sub='{n} étapes · {s} s', done='Terminé', help='En cas de souci, contacte le support'),
    'pl': dict(kicker='Instrukcja', sub='Kroki: {n} · {s} s', done='Gotowe', help='Jeśli coś nie działa, napisz do wsparcia'),
    'tr': dict(kicker='Rehber', sub='{n} adım · {s} sn', done='Tamam', help='Bir sorun olursa desteğe yaz'),
    'it': dict(kicker='Guida', sub='{n} passi · {s} s', done='Fatto', help='Se qualcosa non funziona, scrivi al supporto'),
}
# обращение на «вы» (brand.json: "you": "vy"); языки без формы «вы» берут обычный вариант
HELP_VY = {'ru': 'Не получилось? Напишите в поддержку', 'uk': 'Не вийшло? Напишіть у підтримку',
           'es': 'Si algo no funciona, escriba a soporte', 'de': 'Wenn etwas nicht klappt, schreiben Sie dem Support',
           'fr': 'En cas de souci, contactez le support', 'pl': 'Jeśli coś nie działa, prosimy o kontakt z pomocą',
           'tr': 'Bir sorun olursa desteğe yazın', 'it': 'Se qualcosa non funziona, scriva al supporto',
}

def die(msg): sys.exit('show: ' + msg)
def even(x): return int(round(x / 2.0)) * 2
def clamp(v, lo, hi): return max(lo, min(hi, v))

def run(cmd, capture=False):
    r = subprocess.run(cmd, stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        die('команда упала: ' + ' '.join(str(c) for c in cmd[:6]) + ' ...\n' + (r.stderr or '')[-1500:])
    return r.stdout if capture else (r.stderr or '')

def probe(path):
    out = run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path], capture=True)
    j = json.loads(out); v = next((s for s in j['streams'] if s['codec_type'] == 'video'), None)
    if not v: die('в файле нет видео: ' + path)
    num, den = (v.get('avg_frame_rate') or '30/1').split('/')
    rot = 0
    for sd in v.get('side_data_list', []): rot = int(sd.get('rotation', rot) or rot)
    w, h = int(v['width']), int(v['height'])
    if abs(rot) in (90, 270): w, h = h, w
    return dict(width=w, height=h, fps=(float(num) / float(den) if float(den) else 30.0), duration=float(j['format']['duration']),
                audio=any(s['codec_type'] == 'audio' for s in j['streams']))

def find_browser():
    env = os.environ.get('SHOW_BROWSER')
    cands = [env] if env else []
    if sys.platform == 'darwin':
        cands += ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser']
    elif os.name == 'nt':
        for base in (os.environ.get('PROGRAMFILES', ''), os.environ.get('PROGRAMFILES(X86)', ''), os.environ.get('LOCALAPPDATA', '')):
            cands += [os.path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe'), os.path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe')]
    else:
        cands += [shutil.which(n) for n in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge')]
    return next((c for c in cands if c and os.path.exists(c)), None)

def shot(browser, params, out, w, h):
    """Рисует один слой в PNG с прозрачным фоном. Свой временный профиль, чтобы не трогать открытый браузер пользователя."""
    ud = tempfile.mkdtemp(prefix='show-')
    url = 'file://' + urllib.parse.quote(OVERLAY) + '?d=' + urllib.parse.quote(json.dumps(dict(params, W=w, H=h), ensure_ascii=False))
    try:
        subprocess.run([browser, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
                        '--user-data-dir=' + ud, '--default-background-color=00000000', '--force-device-scale-factor=1',
                        f'--window-size={w},{h}', '--virtual-time-budget=3000', '--screenshot=' + out, url],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    finally:
        shutil.rmtree(ud, ignore_errors=True)
    if not os.path.exists(out): die('браузер не нарисовал слой ' + os.path.basename(out))
    p = probe_image(out)
    if p != (w, h):   # часть сборок браузера отдает окно ниже заказанного: приводим к размеру холста
        tmp = out + '.fix.png'
        run(['ffmpeg', '-y', '-loglevel', 'error', '-i', out, '-vf', f'pad={w}:{h}:0:0:color=0x00000000,crop={w}:{h}:0:0', tmp]); os.replace(tmp, out)

def probe_image(path):
    out = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', path], capture=True)
    w, h = out.strip().split(',')[:2]; return int(w), int(h)

# ---------------------------------------------------------------- prep
def motion_series(src, rate=15):
    """Средняя разница соседних кадров (0-255) на уменьшенной серой копии: по ней видно, где экран менялся и где стоял."""
    err = run(['ffmpeg', '-hide_banner', '-nostats', '-i', src, '-an', '-vf',
               f'fps={rate},scale=160:-2,format=gray,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-',
               '-f', 'null', '-'], capture=True)
    ts, vals, t = [], [], None
    for line in err.splitlines():
        m = re.search(r'pts_time:([0-9.]+)', line)
        if m: t = float(m.group(1)); continue
        m = re.search(r'YAVG=([0-9.eE+-]+)', line)   # значения бывают в виде 7.2e-05
        if m and t is not None: ts.append(t); vals.append(float(m.group(1)))
    return ts, vals

def cmd_prep(a):
    src = os.path.abspath(a.video)
    if not os.path.exists(src): die('нет файла ' + src)
    out = os.path.abspath(a.out or (os.path.splitext(src)[0] + '-show'))
    fr = os.path.join(out, 'frames'); shutil.rmtree(fr, ignore_errors=True); os.makedirs(fr, exist_ok=True)
    info = probe(src); W, H, dur = info['width'], info['height'], info['duration']
    ts, vals = motion_series(src)
    thr = 0.35
    runs, cur = [], None   # участки движения
    for t, v in zip(ts, vals):
        if v > thr:
            if cur and t - cur['end'] <= 0.3: cur['end'] = t; cur['peak'] = max(cur['peak'], v)
            else:
                if cur: runs.append(cur)
                cur = dict(start=t, end=t, peak=v)
    if cur: runs.append(cur)
    for r in runs: r['start'] = round(max(0, r['start'] - 1 / 15), 2); r['end'] = round(min(dur, r['end'] + 1 / 15), 2); r['peak'] = round(r['peak'], 2)
    # кадры для модели: до и после каждого изменения, середина длинных изменений, начало и конец
    want = [(0.15, 'начало')]
    for i, r in enumerate(runs):
        want.append((max(0.0, r['start'] - 0.1), f'перед изменением {i + 1}'))
        if r['end'] - r['start'] > 1.6: want.append(((r['start'] + r['end']) / 2, f'середина изменения {i + 1}'))
        nxt = runs[i + 1]['start'] if i + 1 < len(runs) else dur
        want.append((min(dur - 0.05, r['end'] + min(0.25, max(0.05, (nxt - r['end']) / 2))), f'после изменения {i + 1}'))
    want.append((max(0.0, dur - 0.15), 'конец'))
    want.sort(); picked = []
    for t, why in want:
        if picked and t - picked[-1][0] < 0.28: picked[-1] = (picked[-1][0], picked[-1][1] + '; ' + why); continue
        picked.append((round(t, 2), why))
    if len(picked) > a.max_frames:
        die(f'слишком много изменений на записи ({len(picked)} кадров). Запиши сценарий короче или подними --max-frames')
    # кадр для модели: высота до 1100, поля под линейку
    mh = min(1100, H) if H >= W else int(round(min(1100, W) * H / W)); mw = int(round(W * mh / H)); ml, mt = 50, 24
    tick = 100 if max(W, H) >= 900 else 50
    browser = find_browser(); ruler = os.path.join(out, 'ruler.png')
    if browser: shot(browser, dict(mode='ruler', mw=mw, mh=mh, ml=ml, mt=mt, sw=W, sh=H, tick=tick), ruler, mw + ml, mh + mt)
    frames = []
    for i, (t, why) in enumerate(picked, start=1):
        f = os.path.join(fr, f'k{i:02d}.jpg')
        vf = f'scale={mw}:{mh}:flags=lanczos,pad={mw + ml}:{mh + mt}:{ml}:{mt}:color=0x101218'
        cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{t:.3f}', '-i', src]
        if browser: cmd += ['-i', ruler, '-filter_complex', f'[0:v]{vf}[a];[a][1:v]overlay=0:0', '-frames:v', '1', '-q:v', '3', f]
        else: cmd += ['-vf', vf, '-frames:v', '1', '-q:v', '3', f]
        run(cmd); frames.append(dict(file=os.path.relpath(f, out), t=t, why=why))
    prep = dict(source=src, width=W, height=H, fps=round(info['fps'], 2), duration=round(dur, 2), audio=info['audio'],
                ruler=dict(note='подписи линейки в пикселях исходной записи', left_margin=ml, top_margin=mt, scale=round(mw / W, 4)),
                changes=runs, frames=frames)
    json.dump(prep, open(os.path.join(out, 'prep.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'запись {W}x{H}, {dur:.1f} с, звук: {"есть" if info["audio"] else "нет"}; изменений экрана: {len(runs)}; кадров для просмотра: {len(frames)}')
    for r in runs: print(f'  изменение {r["start"]:6.2f} - {r["end"]:6.2f} с, сила {r["peak"]}')
    print('папка:', out)

# ---------------------------------------------------------------- render
COMPOSE = os.path.join(HERE, 'compose.html')
DEFAULT_BRAND = os.path.join(HERE, '..', 'assets', 'brand-default.json')
STEP_LABEL = {'ru': 'Шаг {n} из {m}', 'uk': 'Крок {n}/{m}', 'en': 'Step {n} of {m}', 'es': 'Paso {n} de {m}', 'pt': 'Passo {n} de {m}', 'de': 'Schritt {n} von {m}',
              'fr': 'Étape {n} sur {m}', 'pl': 'Krok {n} z {m}', 'tr': 'Adım {n} / {m}', 'it': 'Passo {n} di {m}'}
META = {'ru': ('шагов', 'сек'), 'uk': ('кроків', 'сек'), 'en': ('steps', 'sec'), 'es': ('pasos', 's'), 'pt': ('passos', 's'), 'de': ('Schritte', 'Sek.'),
        'fr': ('étapes', 's'), 'pl': ('kroków', 's'), 'tr': ('adım', 'sn'), 'it': ('passi', 's')}

SPAWN = threading.Lock()

class Browser:
    """Браузер без окна, которым Python управляет через канал отладки (stdin/stdout-трубы, без websocket и без Node)."""
    def __init__(self, path):
        with SPAWN:  # запуск строго по одному: fork из нескольких потоков сразу иногда рвал канал
            self._spawn(path)
        tid = self.call('Target.createTarget', {'url': 'about:blank'})['targetId']
        self.sid = self.call('Target.attachToTarget', {'targetId': tid, 'flatten': True})['sessionId']
    def _spawn(self, path):
        a_r, a_w = os.pipe(); b_r, b_w = os.pipe()
        self.ud = tempfile.mkdtemp(prefix='show-')
        def pre():
            x, y = os.dup(a_r), os.dup(b_w); os.dup2(x, 3); os.dup2(y, 4)
        self.p = subprocess.Popen([path, '--headless=new', '--remote-debugging-pipe', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                                   '--no-default-browser-check', '--force-color-profile=srgb', '--allow-file-access-from-files', '--mute-audio',
                                   '--user-data-dir=' + self.ud, 'about:blank'], preexec_fn=pre, close_fds=False,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(a_r); os.close(b_w)
        self.w = os.fdopen(a_w, 'wb', buffering=0); self.r = os.fdopen(b_r, 'rb', buffering=0); self.buf = b''; self.n = 0
    def _msg(self):
        while b'\0' not in self.buf:
            chunk = self.r.read(1 << 20)
            if not chunk: raise RuntimeError('браузер закрылся')
            self.buf += chunk
        m, self.buf = self.buf.split(b'\0', 1); return json.loads(m)
    def call(self, method, params=None, page=False):
        self.n += 1; msg = {'id': self.n, 'method': method, 'params': params or {}}
        if page: msg['sessionId'] = self.sid
        self.w.write(json.dumps(msg).encode() + b'\0')
        while True:
            m = self._msg()
            if m.get('id') == self.n:
                if 'error' in m: raise RuntimeError(f"{method}: {m['error']}")
                return m.get('result', {})
    def js(self, expr):
        r = self.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, page=True)
        if r.get('exceptionDetails'): raise RuntimeError('ошибка в странице: ' + json.dumps(r['exceptionDetails'])[:600])
        return r.get('result', {}).get('value')
    def close(self):
        try: self.p.kill(); self.p.wait(5)
        except Exception: pass
        shutil.rmtree(self.ud, ignore_errors=True)

def load_brand(a, d):
    path = a.brand or (os.path.join(d, 'brand.json') if os.path.exists(os.path.join(d, 'brand.json')) else DEFAULT_BRAND)
    b = json.load(open(path, encoding='utf-8')); base = os.path.dirname(os.path.abspath(path))
    for k in ('logo',):
        if b.get(k) and not re.match(r'^(file|https?|data):', b[k]): b[k] = 'file://' + urllib.parse.quote(os.path.join(base, b[k]))
    for k in ('font', 'font_head'):
        if (b.get(k) or {}).get('file') and not re.match(r'^(file|https?|data):', b[k]['file']):
            b[k]['file'] = 'file://' + urllib.parse.quote(os.path.join(base, b[k]['file']))
    return b, path

def edge_color(src, W, H, y, t=0.5):
    """Средний цвет полосы в 4 px записи (верх или низ): им заливаются поля статус-бара и полоски «домой»."""
    r = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', src, '-frames:v', '1', '-vf', f'scale={W}:{H},crop={W}:4:0:{y},scale=1:1:flags=area', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                       capture_output=True)
    c = r.stdout[:3] if len(r.stdout) >= 3 else b'\x00\x00\x00'
    return '%02X%02X%02X' % tuple(c), (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) < 140

def plain(t):
    """Текст подписи без разметки: [Кнопка] в подписи значит название на экране, в ролике оно выделено цветом."""
    return re.sub(r'\[([^\]]+)\]', r'\1', t or '')

def split_title(t, n=16):
    """Заголовок заставки в 1-3 ровные строки: разрыв там, где самая длинная строка короче всего."""
    w = t.split(); L = lambda ws: len(' '.join(ws))
    if len(t) <= n or len(w) < 2: return [t]
    k = min(range(1, len(w)), key=lambda k: max(L(w[:k]), L(w[k:])))
    if max(L(w[:k]), L(w[k:])) <= n + 3 or len(w) < 3: return [' '.join(w[:k]), ' '.join(w[k:])]
    i, j = min(((i, j) for i in range(1, len(w) - 1) for j in range(i + 1, len(w))), key=lambda p: max(L(w[:p[0]]), L(w[p[0]:p[1]]), L(w[p[1]:])))
    return [' '.join(w[:i]), ' '.join(w[i:j]), ' '.join(w[j:])]

def blur_mask(boxes, W, H, path, feather=10.0):
    """Маска размытия (PGM): скругленные прямоугольники с мягким краем. Полная сила размытия покрывает весь прямоугольник,
    мягкий край выходит за него на feather пикселей, поэтому значение не просвечивает и не видно жестких швов."""
    buf = bytearray(W * H)
    for b in boxes:
        x, y, w, h = [float(v) for v in b[:4]]; r = float(b[4]) if len(b) > 4 else min(h / 2.0, 20.0)
        cx, cy, hx, hy = x + w / 2, y + h / 2, w / 2, h / 2
        for py in range(max(0, int(y - feather - 1)), min(H, int(y + h + feather + 2))):
            qy = abs(py + .5 - cy) - hy + r; row = py * W
            for px in range(max(0, int(x - feather - 1)), min(W, int(x + w + feather + 2))):
                qx = abs(px + .5 - cx) - hx + r
                dd = (max(qx, 0) ** 2 + max(qy, 0) ** 2) ** .5 + min(max(qx, qy), 0) - r   # расстояние до края (внутри меньше нуля)
                v = int(255 * clamp(1 - dd / feather, 0, 1))
                if v > buf[row + px]: buf[row + px] = v
    with open(path, 'wb') as f: f.write(b'P5\n%d %d\n255\n' % (W, H)); f.write(bytes(buf))

def cmd_render(a):
    d = os.path.abspath(a.dir)
    prep = json.load(open(os.path.join(d, 'prep.json'), encoding='utf-8'))
    plan = json.load(open(os.path.join(d, 'plan.json'), encoding='utf-8'))
    src, W, H = prep['source'], even(prep['width']), even(prep['height'])
    if not os.path.exists(src): die('исходная запись пропала: ' + src)
    browser = find_browser()
    if not browser: die('не нашел Chrome, Edge или Chromium: они рисуют ролик. Путь можно задать в SHOW_BROWSER')
    if H < W: die('пока поддержаны вертикальные записи с телефона; запись с компьютера будет в следующей версии')
    brand, bpath = load_brand(a, d)
    langs = [a.lang] if a.lang else plan['languages']; steps = plan['steps']; n = len(steps); fps = a.fps
    # запись из браузера без статус-бара: добавляем поля под статус-бар iPhone (54 pt) и полоску «домой» (34 pt),
    # чтобы сайт стоял в безопасной зоне, как на настоящем телефоне, и углы экрана ничего не срезали
    scr = plan.get('screen') or {}; PT, PB = 0, 0; scr_info = {}
    if scr.get('status_bar'):
        PT, PB = even(W * 54 / 393), even(W * 34 / 393)
        def hint(k):   # цвет, который записал рекордер (фон страницы), важнее одного кадра на 0,5 с
            v = str(scr.get(k) or '').lstrip('#')
            if not re.fullmatch(r'[0-9A-Fa-f]{6}', v): return None
            c = [int(v[i:i + 2], 16) for i in (0, 2, 4)]; return v.upper(), (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) < 140
        (tc, tdark), (bc, bdark) = hint('top_color') or edge_color(src, W, H, 0), hint('bottom_color') or edge_color(src, W, H, H - 4)
        scr_info = dict(top=PT, bottom=PB, topDark=tdark, bottomDark=bdark, topColor=tc, bottomColor=bc)
    H0 = H; H = H0 + PT + PB
    def shifted(v, k=1):   # координаты плана (в пикселях записи) -> координаты кадра с полями
        if not v: return v
        v = list(v); v[k] = float(v[k]) + PT; return v
    geo = [dict(focus=shifted(st.get('focus')), tap=shifted(st.get('tap')), zoom=shifted(st.get('zoom'))) for st in steps]
    if not steps: die('в plan.json нет шагов')
    tmp = os.path.join(d, 'tmp'); shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    INTRO, OUTRO = 2.7, 3.8
    sync = []   # --sync: тексты других планов, чтобы ролики разных брендов шли кадр в кадр
    for o in (a.sync or []):
        try: sync.append(json.load(open(os.path.join(os.path.abspath(o), 'plan.json'), encoding='utf-8'))['steps'])
        except Exception as e: die(f'--sync {o}: {e}')
    mts, mvals = motion_series(src, rate=30)
    def switch_after(tt):   # когда после касания меняется экран: самый сильный скачок кадра за 1,2 с
        best, bt = 0.0, None
        for x, v in zip(mts, mvals):
            if tt + .05 <= x <= tt + 1.2 and v > best: best, bt = v, x
        return bt if best > 0.35 else None
    t, keys, timing = INTRO, [], []
    C = (W / 2.0, H / 2.0); keys.append(dict(t=0, z=1, cx=C[0], cy=C[1]))
    for i, st in enumerate(steps, start=1):
        t0, t1 = float(st['src'][0]), float(st['src'][1]); action = t1 - t0
        if action <= 0.05: die(f'шаг {i}: пустой отрезок записи {st["src"]}')
        texts = [plain(st['text'].get(l, '')) for l in plan['languages']]
        texts += [plain(o[i - 1]['text'].get(l, '')) for o in sync if len(o) >= i for l in plan['languages']]
        read = clamp(1.0 + max(len(x) for x in texts) / 16.0, 2.2, 7.0)
        tap = geo[i - 1]['tap']; focus = geo[i - 1]['focus']
        if st.get('speed'): speed = float(st['speed'])
        elif tap:
            tc0 = float(tap[2]) - t0; speed = min(tc0 / max(read, 1.1), 3.0) if tc0 > max(read, 1.1) * 1.5 else 1.0
        else: speed = min(action / read, 3.0) if action > read * 1.15 else 1.0
        body = action / speed
        if tap:   # запас на чтение ставим ДО касания: после касания шаг заканчивается вместе со сменой экрана
            tap_c = (float(tap[2]) - t0) / speed; post = body - tap_c
            pre = max(tap_c, 1.1, read - post); lead = pre - tap_c; D = pre + post; hold = 0.0
            T = t + pre; sw = switch_after(float(tap[2])); Csw = t + lead + (sw - t0) / speed if sw else T + .3
        else:
            lead, D = 0.0, max(body, read); hold = D - body; T = Csw = None
        zf, F = 1.0, C
        if focus:
            fx, fy, fw, fh = [float(v) for v in focus[:4]]
            # экран всегда целиком, без наезда: приближение только по явной рамке "zoom": [x,y,w,h] (весь ряд вокруг цели)
            ctx = geo[i - 1]['zoom']
            if ctx:
                cx_, cy_, cw_, ch_ = [float(v) for v in ctx[:4]]
                zf = min(1.6, 0.96 * W / max(cw_, 1), 0.7 * H / max(ch_, 1)); F = (cx_ + cw_ / 2, cy_ + ch_ / 2)
            else:
                zf = 1.0
            if zf < 1.03: zf = 1.0
            if zf > 1.0:
                F = (clamp(F[0], W / zf / 2, W - W / zf / 2), clamp(F[1], H / zf / 2, H - H / zf / 2))
                last = keys[-1]['t']
                if tap:   # наезд к касанию, отъезд сразу после него: к смене экрана камера уже почти на месте
                    start = max(t + .1, T - 1.3, last + .05); arrive = max(T - .35, start + .6); stay = T + .08
                    ks = [(start, 1, *C), (arrive, zf, *F), (stay, zf, *F), (max(Csw + .3, stay + .5), 1, *C)] if arrive < T - .05 else []
                else:
                    start = max(t + .2, last + .05); arrive = start + .75; leave = t + D - .9
                    ks = [(start, 1, *C), (arrive, zf, *F), (leave, zf, *F), (leave + .75, 1, *C)] if leave > arrive + .3 else []
                if not ks: zf = 1.0
                for k in ks: keys.append(dict(t=round(k[0], 3), z=k[1], cx=k[2], cy=k[3]))
        timing.append(dict(i=i, t0=t0, action=action, speed=speed, lead=lead, hold=hold, D=D, S=t, E=t + D, T=T, C=Csw, zf=zf,
                           sw_local=((sw - t0) / speed) if tap and sw else None))
        t += D
    if t + .01 > keys[-1]['t'] + .05: keys.append(dict(t=round(t + .01, 3), z=1, cx=C[0], cy=C[1]))
    for i, g in enumerate(geo, start=1):   # рамка и касание должны совпадать с элементом: явные ошибки плана ловим до рендера
        f, tp = g['focus'], g['tap']
        if f:
            fx, fy, fw, fh = [float(v) for v in f[:4]]
            if fw <= 4 or fh <= 4 or fx < -2 or fy < -2 or fx + fw > W + 2 or fy + fh > H + 2: print(f'  внимание: шаг {i}: рамка {f[:4]} вне экрана {W}x{H}', file=sys.stderr)
            if tp and not (fx - 4 <= float(tp[0]) <= fx + fw + 4 and fy - 4 <= float(tp[1]) <= fy + fh + 4):
                print(f'  внимание: шаг {i}: касание ({tp[0]}, {tp[1]}) вне рамки {f[:4]}', file=sys.stderr)
    total = t + OUTRO; N = int(round(total * fps))

    sources = {l: (p if os.path.isabs(p) else os.path.join(d, p)) for l, p in plan.get('sources', {}).items()}
    for l, p in sources.items():
        if not os.path.exists(p): die(f'нет записи для языка {l}: {p}')
        pi = probe(p)
        if (even(pi['width']), even(pi['height'])) != (W, H0): die(f'запись {l} другого размера, чем основная: {p}')
    cuts = {}
    def cut(source):   # кадры шагов из записи: ускорение, паузы и размытие личных данных вшиваются здесь
        if source in cuts: return cuts[source]
        base = os.path.join(tmp, f'src{len(cuts) + 1}'); os.makedirs(base); dirs = []
        for tm, st in zip(timing, steps):
            sd = os.path.join(base, f's{tm["i"]:02d}'); os.makedirs(sd)
            cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{tm["t0"]:.3f}', '-t', f'{tm["action"]:.3f}', '-i', source]
            chain = f'[0:v]setpts=(PTS-STARTPTS)/{tm["speed"]:.4f},fps={fps},scale={W}:{H0}'
            k = tm['i'] - 1; nxt = steps[k + 1].get('blur', []) if k + 1 < len(steps) else []
            layers = [(st.get('blur', []), None)]
            if nxt and tm.get('sw_local') is not None: layers.append((nxt, max(0.0, tm['sw_local'] - 0.05)))   # данные следующего экрана закрыты с момента смены экрана
            inp = 1
            for li, (boxes, after) in enumerate(layers):
                if not boxes: continue
                mask = os.path.join(sd, f'mask{li}.pgm'); blur_mask(boxes, W, H0, mask, feather=6.0)   # маска по записи до полей статус-бара
                sig = clamp(max(float(b[3]) for b in boxes) / 3.2, 10.0, 16.0)
                cmd += ['-framerate', str(fps), '-loop', '1', '-i', mask]
                en = f":enable='gte(t,{after:.3f})'" if after is not None else ''
                chain += f',split[va{li}][vb{li}];[vb{li}]gblur=sigma={sig:.1f}[bl{li}];[{inp}:v]format=gray[mk{li}];[bl{li}][mk{li}]alphamerge[bm{li}];[va{li}][bm{li}]overlay=shortest=1{en}'
                inp += 1
            if PT or PB:
                chain += f',pad={W}:{H}:0:{PT}:color=0x{scr_info["topColor"]},drawbox=x=0:y={PT + H0}:w={W}:h={PB}:color=0x{scr_info["bottomColor"]}:t=fill'
            if tm['lead'] > 0.01 or tm['hold'] > 0.01:
                chain += f',tpad=start_mode=clone:start_duration={tm["lead"]:.3f}:stop_mode=clone:stop_duration={tm["hold"] + 0.3:.3f}'
            chain += '[out]'; nf = int(round(tm['D'] * fps))
            run(cmd + ['-filter_complex', chain, '-map', '[out]', '-frames:v', str(nf), '-q:v', '2', os.path.join(sd, '%05d.jpg')])
            got = len([f for f in os.listdir(sd) if f.endswith('.jpg')])
            if got == 0: die(f'шаг {tm["i"]}: ffmpeg не дал кадров')
            dirs.append((sd, got))
        cuts[source] = dirs; return dirs
    slug = plan.get('slug') or re.sub(r'[^a-z0-9]+', '-', plan.get('title', {}).get('en', 'guide').lower()).strip('-') or 'guide'
    outd = os.path.join(d, 'out'); os.makedirs(outd, exist_ok=True); made = []
    page = 'file://' + urllib.parse.quote(COMPOSE)
    for lang in langs:
        loc = L10N.get(lang, L10N['en']); title = plan['title'].get(lang) or next(iter(plan['title'].values()))
        mt = META.get(lang, META['en']); secs = int(round(total / 5.0) * 5)
        outro = brand.get('outro', {})
        dirs = cut(sources.get(lang, src))
        man_steps = [dict(S=round(tm['S'], 4), E=round(tm['E'], 4), n=got, dir='file://' + urllib.parse.quote(sd), focus=g['focus'], zmax=tm['zf'],
                          tap=[float(g['tap'][0]), float(g['tap'][1]), round(tm['T'], 4), round(tm['C'], 4)] if g['tap'] else None, text=st['text'])
                     for tm, st, g, (sd, got) in zip(timing, steps, geo, dirs)]
        man = dict(W=W, H=H, fps=fps, total=round(total, 4), keys=keys, brand=brand, screen=scr_info, title=title, titleLines=split_title(title),
                   kicker=(plan.get('kicker', {}).get(lang) or brand.get('kicker', {}).get(lang) or loc['kicker']),
                   meta=[f'<b>{n}</b> {mt[0]}', f'<b>{secs}</b> {mt[1]}'], stepLabel=STEP_LABEL.get(lang, STEP_LABEL['en']),
                   done=plan.get('done', {}).get(lang) or outro.get('title', {}).get(lang) or loc['done'],
                   help=plan.get('outro', {}).get(lang) or outro.get('sub', {}).get(lang) or (HELP_VY.get(lang) if brand.get('you') == 'vy' else None) or loc['help'],
                   cta=outro.get('cta', {}).get(lang) or '',
                   steps=[dict(s, text=s['text'].get(lang) or next(iter(s['text'].values()))) for s in man_steps])
        fd = os.path.join(tmp, 'f_' + lang); os.makedirs(fd)
        json.dump(dict(man, brand={}), open(os.path.join(tmp, f'manifest.{lang}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)  # для проверки кадров
        if a.proof:   # лист проверки: заставка, момент перед каждым касанием (рамка видна целиком), результат, финал
            todo = sorted({0} | {int(round((tm['T'] - .3) * fps)) for tm in timing if tm['T']} |
                          {int(round((tm['S'] + min(1.2, tm['D'] / 2)) * fps)) for tm in timing if not tm['T']} | {N - 1})
        else: todo = list(range(N))
        workers = max(1, min(a.workers, len(todo) // 60 or 1)); bounds = [len(todo) * w // workers for w in range(workers + 1)]
        def job(w):
            pos, tries = bounds[w], 0
            while pos < bounds[w + 1]:
                b = Browser(browser)
                try:
                    b.call('Emulation.setDeviceMetricsOverride', {'width': 1080, 'height': 1920, 'deviceScaleFactor': 1, 'mobile': False}, page=True)
                    b.call('Page.enable', page=True); b.call('Page.navigate', {'url': page}, page=True)
                    for _ in range(200):
                        try:
                            if b.js('window.READY===true'): break
                        except RuntimeError: pass
                        time.sleep(0.05)
                    b.js('init(' + json.dumps(man, ensure_ascii=False) + ')')
                    while pos < bounds[w + 1]:
                        fi = todo[pos]
                        b.js(f'render({fi} / {fps})')   # номер кадра, а не округленное время: без повторов и пропусков
                        shot_ = b.call('Page.captureScreenshot', {'format': 'jpeg', 'quality': 93, 'optimizeForSpeed': False}, page=True)
                        open(os.path.join(fd, f'{fi:05d}.jpg'), 'wb').write(base64.b64decode(shot_['data'])); pos += 1
                except (OSError, RuntimeError) as e:
                    if 'ошибка в странице' in str(e): raise  # ошибка в compose.html: повтор не поможет
                    tries += 1
                    if tries > 3: raise
                    print(f'  поток {w}: браузер упал на кадре {todo[pos] if pos < len(todo) else "-"} ({type(e).__name__}), перезапускаю', file=sys.stderr)
                finally:
                    b.close()
        with concurrent.futures.ThreadPoolExecutor(workers) as ex:
            for f in [ex.submit(job, w) for w in range(workers)]: f.result()
        if a.proof:
            pr = os.path.join(outd, f'proof.{lang}.png'); ins = []
            for fi in todo: ins += ['-i', os.path.join(fd, f'{fi:05d}.jpg')]
            run(['ffmpeg', '-y', '-loglevel', 'error', *ins, '-filter_complex', ''.join(f'[{i}]' for i in range(len(todo))) + f'hstack={len(todo)},scale=-2:960' if len(todo) > 1 else 'scale=-2:960',
                 '-frames:v', '1', '-update', '1', pr])
            made.append(pr); print(f'  {lang}: лист проверки, {len(todo)} кадров', flush=True); continue
        out = os.path.join(outd, f'{slug}.{lang}.mp4')
        run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(fps), '-i', os.path.join(fd, '%05d.jpg'), '-f', 'lavfi', '-t', f'{total:.3f}', '-i', 'anullsrc=r=44100:cl=stereo',
             '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p', '-r', str(fps), '-c:a', 'aac', '-b:a', '64k',
             '-shortest', '-movflags', '+faststart', out])
        poster = os.path.join(fd, f'{int(1.4 * fps):05d}.jpg')
        if os.path.exists(poster): shutil.copy(poster, os.path.join(outd, f'{slug}.{lang}.jpg'))
        made.append(out); print(f'  {lang}: {N} кадров', flush=True)
    md = []
    for lang in langs:
        md.append(f"# {plan['title'].get(lang, '')}\n")
        md += [f"{i}. {plain(st['text'].get(lang, ''))}" for i, st in enumerate(steps, start=1)] + ['']
    open(os.path.join(outd, f'{slug}.steps.md'), 'w', encoding='utf-8').write('\n'.join(md))
    card = dict(id=slug, title=plan['title'], languages=langs, steps=[{l: plain(v) for l, v in st['text'].items()} for st in steps], questions=plan.get('questions', {}),
                operator_reply=plan.get('operator_reply', {}), topic=plan.get('topic', ''), recorded=plan.get('recorded') or datetime.date.today().isoformat(),
                source_sha1={l: hashlib.sha1(open(sources.get(l, src), 'rb').read()).hexdigest()[:12] for l in langs}, duration_sec=round(total, 1), brand=os.path.basename(bpath),
                files={l: f'{slug}.{l}.mp4' for l in langs})
    json.dump(card, open(os.path.join(outd, f'{slug}.card.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if not a.keep: shutil.rmtree(tmp, ignore_errors=True)
    print(f'готово: {len(made)} ролик(ов), {total:.1f} с, шагов {n}, {fps} кадров/с, бренд {os.path.basename(bpath)}')
    for m in made: print('  ', m)

def cmd_compare(a):
    """Два ролика рядом (например, один сценарий в двух брендах) с подписями над каждым."""
    vids = [os.path.abspath(v) for v in (a.left, a.right)]
    for v in vids:
        if not os.path.exists(v): die('нет файла ' + v)
    browser = find_browser()
    if not browser: die('нужен Chrome, Edge или Chromium для подписей')
    pw, ph, gap, lh = 720, 1280, 48, 120; Wt = pw * 2 + gap * 3
    labels = (a.labels or ['', ''])[:2]
    fonts = ''.join("@font-face{font-family:M;font-weight:100 900;src:url('%s') format('woff2')}" % ('file://' + urllib.parse.quote(os.path.join(HERE, '..', 'assets', 'fonts', f)))
                    for f in ('Montserrat-cyrillic.woff2', 'Montserrat-latin.woff2', 'Montserrat-cyrillic-ext.woff2', 'Montserrat-latin-ext.woff2'))
    html = ('<!doctype html><meta charset="utf-8"><style>' + fonts + 'html,body{margin:0;width:%dpx;height:%dpx;background:#121318;overflow:hidden}'
            'div{position:absolute;top:0;height:%dpx;display:flex;align-items:center;justify-content:center;width:%dpx;font:700 32px M,-apple-system,Arial,sans-serif;letter-spacing:-.3px;color:#E9EAF2}'
            '</style>' % (Wt, lh, lh, pw)) + ''.join('<div style="left:%dpx">%s</div>' % (gap + i * (pw + gap), l.replace('&', '&amp;').replace('<', '&lt;')) for i, l in enumerate(labels))
    tmp = tempfile.mkdtemp(prefix='show-cmp-'); page = os.path.join(tmp, 'labels.html'); open(page, 'w', encoding='utf-8').write(html)
    strip = os.path.join(tmp, 'labels.png')
    b = Browser(browser)
    try:
        b.call('Emulation.setDeviceMetricsOverride', {'width': Wt, 'height': lh, 'deviceScaleFactor': 1, 'mobile': False}, page=True)
        b.call('Page.enable', page=True); b.call('Page.navigate', {'url': 'file://' + urllib.parse.quote(page)}, page=True); time.sleep(0.6)
        b.js('document.fonts.ready.then(() => 1)')
        open(strip, 'wb').write(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, page=True)['data']))
    finally:
        b.close()
    dur = min(probe(v)['duration'] for v in vids); fps = a.fps
    out = os.path.abspath(a.out)
    corner = os.path.join(tmp, 'corner.pgm'); blur_mask([[0, 0, pw, ph, 30]], pw, ph, corner, feather=1.5)   # скругленные углы панелей
    fc = (f'color=c=#121318:s={Wt}x{ph + lh + gap}:r={fps}:d={dur:.3f}[bg];[3:v]format=gray,split[m1][m2];'
          f'[0:v]fps={fps},scale={pw}:{ph},format=yuva420p[l0];[l0][m1]alphamerge[l];[1:v]fps={fps},scale={pw}:{ph},format=yuva420p[r0];[r0][m2]alphamerge[r];[2:v]format=rgba[s];'
          f'[bg][s]overlay=0:0[b1];[b1][l]overlay={gap}:{lh}:shortest=1[b2];[b2][r]overlay={gap * 2 + pw}:{lh}:shortest=1,format=yuv420p[v]')
    run(['ffmpeg', '-y', '-loglevel', 'error', '-i', vids[0], '-i', vids[1], '-loop', '1', '-i', strip, '-framerate', str(fps), '-loop', '1', '-i', corner, '-filter_complex', fc, '-map', '[v]', '-map', '0:a?',
         '-t', f'{dur:.3f}', '-c:v', 'libx264', '-preset', 'slow', '-crf', '19', '-r', str(fps), '-c:a', 'aac', '-b:a', '64k', '-movflags', '+faststart', out])
    shutil.rmtree(tmp, ignore_errors=True); print('готово:', out)

def cmd_check(a):
    for tool in ('ffmpeg', 'ffprobe'):
        print(f'{tool}: {"есть" if shutil.which(tool) else "НЕТ, поставь ffmpeg"}')
    b = find_browser(); print('браузер для подписей:', b or 'НЕТ (нужен Chrome, Edge или Chromium)')

def main():
    ap = argparse.ArgumentParser(description='show: запись экрана -> видеоинструкция'); sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('prep'); p.add_argument('video'); p.add_argument('--out'); p.add_argument('--max-frames', type=int, default=60); p.set_defaults(fn=cmd_prep)
    r = sub.add_parser('render'); r.add_argument('dir'); r.add_argument('--lang'); r.add_argument('--brand'); r.add_argument('--fps', type=int, default=60)
    r.add_argument('--workers', type=int, default=4); r.add_argument('--keep', action='store_true')
    r.add_argument('--proof', action='store_true', help='не видео, а лист проверки: кадры с рамками перед каждым касанием')
    r.add_argument('--sync', action='append', help='папка другого плана: время шагов берется по самым длинным подписям обоих, ролики идут кадр в кадр'); r.set_defaults(fn=cmd_render)
    m = sub.add_parser('compare'); m.add_argument('left'); m.add_argument('right'); m.add_argument('--labels', nargs=2); m.add_argument('--out', required=True)
    m.add_argument('--fps', type=int, default=60); m.set_defaults(fn=cmd_compare)
    c = sub.add_parser('check'); c.set_defaults(fn=cmd_check)
    a = ap.parse_args(); a.fn(a)

if __name__ == '__main__':
    main()
