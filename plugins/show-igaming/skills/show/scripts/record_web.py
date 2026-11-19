#!/usr/bin/env python3
"""record_web: запись сценария на сайте оператора в виде iPhone для show.py.

  python3 record_web.py URL steps.json --out DIR [--lang uk] [--profile DIR] [--keep-banners]
  python3 record_web.py login URL --profile DIR      один раз: окно Chrome, человек сам входит в тестовый аккаунт и закрывает окно

Аккаунт: --profile = отдельная папка профиля Chrome (не основной профиль: Chrome с версии 136 не дает управлять им скриптом).
  login открывает обычное окно Chrome с этим профилем в мобильном виде; пароль и коды вводит человек, скрипт их не видит и не хранит.
  После закрытия окна вход сохраняется в папке, записи с --profile идут уже в аккаунте. Для обычного и VIP-аккаунта две папки.

Экран как у iPhone 15 без статус-бара и полоски «домой»: 393x764 pt, x2 = запись 786x1528, 60 кадров/с.
Шаги ищутся по видимому тексту (точно, без учета регистра, по вхождению), aria-label, alt/title, placeholder.
steps.json:
  {"title": {"uk": "..."}, "slug": "...",
   "steps": [{"tap": "Слоти", "where": "bottom-nav"}, {"tap": "Більше", "near": "Усі провайдери"}, {"tap": "Назва провайдера"},
             {"tap_icon": "search", "where": "header"}, {"type": "Назва гри", "into": "search"},
             {"scroll_to": "Нові ігри"}, {"wait": 1.5}, {"back": true}, {"point": "Поповнити"}],
   "say": {"uk": ["Унизу натисни [Слоти]", "..."]},
   "blur": ["Eugene", "css:.user-id"], "blur_auto": true}
  tap: текст на экране; near: ближайший к ориентиру; where: top, bottom, bottom-nav, header; index: N-й сверху.
  near: ориентир берется только из той же части экрана (подпись в нижнем меню не ориентир для кнопки на странице);
    «рядом» = близко на экране или в одном блоке (раздел, карточка). Если подходит несколько, запись останавливается со списком index.
  Без near: если на экране несколько одинаковых текстов, тоже стоп со списком, а не догадка.
  Если цели нет в загруженной части страницы (разделы грузятся при прокрутке), рекордер листает страницу вниз по 3/4 экрана
    до конца, это шаг ролика «Прокрути до …». Не нашел до конца страницы: стоп и похожие тексты (опечатка) или «такого здесь нет».
  tap_icon: кнопка без текста: search, back, menu, close, home, profile, filter или слово из ее разметки.
  type: печатает в поле (search по умолчанию или часть подписи поля); если поле за лупой, лупа нажимается сама.
  scroll_to: плавная прокрутка до текста отдельным шагом. back: стрелка «назад» сайта, если ее нет, назад браузера.
  point: рамка на кнопке без нажатия, только последним шагом. Для кнопок оплаты, вывода и ставки: их рекордер не нажимает никогда
    (текст про деньги + заполненная сумма или отправка формы = стоп с подсказкой сделать шаг point).
  blur: что размыть на всех кадрах: текст (элемент с этим текстом) или "css:селектор". blur_auto (по умолчанию включено с --profile):
    почта, телефон, номер карты и маска **** 1234, IBAN, ID игрока, поля почты, телефона, пароля. Размытие ставится в странице до отрисовки кадра.
    Формы платежных систем во фреймах другого сайта так не размываются: для них рамки blur в plan.json (пиксели записи).
  say[i] = подпись i-го шага без учета "wait"; лишняя последняя строка = подпись финального экрана.
  Шаги, которые рекордер добавил сам (прокрутка к цели вне экрана, лупа перед вводом), подписываются автоматически.
  У шага можно задать "say": {"uk": "..."} и "expect": "текст, который должен появиться" (на новом месте: то, что стояло там же и до шага, не в счет).
В DIR: recording.<lang>.mp4, truth.json, plan.json (для show.py render), proof.png (рамки поверх кадров), prep.json и frames/.
Касание проверяется: адрес или экран должны смениться за 3 с, иначе повтор кликом скриптом, иначе стоп с ошибкой и снимком fail-stepN.png.
Плашки «скачай приложение» и реклама выезжают с задержкой: рекордер ждет 3,5 с без новых плашек, смотрит еще раз перед записью и перед каждым шагом.
Кадры записи 0,3-0,8 с несут полоски цвета полей статус-бара и «домой» для show.py (ровный край страницы продолжается в поле,
  край по картинкам и тексту = фон страницы); в ролик эти кадры не входят.
Скрипт сам не входит в аккаунт и не регистрируется (вход делает человек в окне login), не вводит личные и платежные данные,
не нажимает оплату, вывод и ставку, не принимает условия, возрастные окна и cookie (только «отклонить»).
"""
import argparse, base64, json, os, re, shutil, struct, subprocess, sys, tempfile, threading, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import show  # noqa: E402

VW, VH, DPR, FPS = 393, 764, 2, 60   # iPhone 15: 393x852 pt минус статус-бар 54 и полоска «домой» 34
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'
AUTO = {   # подписи шагов, которые рекордер добавил сам, и названия иконок без текста
    'uk': dict(scroll='Прокрути до [{t}]', scroll_x='Гортай вбік до [{t}]', search='Натисни на [пошук]', back='Повернись назад', final='Готово, ось результат', tap='Натисни [{t}]',
               type='Введи [{t}] у пошук', icons=dict(search='пошук', back='назад', close='закрити', menu='меню', home='головна', profile='профіль', filter='фільтр')),
    'ru': dict(scroll='Прокрути до [{t}]', scroll_x='Листай вбок до [{t}]', search='Нажми на [поиск]', back='Вернись назад', final='Готово, вот результат', tap='Нажми [{t}]',
               type='Введи [{t}] в поиск', icons=dict(search='поиск', back='назад', close='закрыть', menu='меню', home='главная', profile='профиль', filter='фильтр')),
    'en': dict(scroll='Scroll to [{t}]', scroll_x='Swipe sideways to [{t}]', search='Tap [search]', back='Go back', final='Done, here is the result', tap='Tap [{t}]',
               type='Type [{t}] into search', icons=dict(search='search', back='back', close='close', menu='menu', home='home', profile='profile', filter='filter')),
}

APP_BANNER = re.compile(r'завантаж|скачат|скачай|download|install|встанов|установ|додаток|приложени|app store|google play|\bapp\b', re.I)

def die(msg, code=1):
    print('record_web: ' + msg, file=sys.stderr); sys.exit(code)

class Fail(Exception):
    """Шаг не получился: сообщение для человека и путь к снимку экрана."""

def jpeg_size(data):
    """Ширина и высота JPEG по маркеру SOF, без сторонних библиотек."""
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF: i += 1; continue
        m = data[i + 1]
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack('>HH', data[i + 5:i + 9]); return w, h
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7: i += 2; continue
        i += 2 + struct.unpack('>H', data[i + 2:i + 4])[0]
    return None

class Rec(show.Browser):
    """Тот же канал отладки, что в show.py, но ответы и события читает отдельный поток:
    кадры screencast сохраняются и подтверждаются сразу, пока сценарий ждет или считает."""
    def __init__(self, path, frames_dir, profile=None):
        self.frames_dir, self.frames, self.bad, self.profile = frames_dir, [], [], profile
        self.cv, self.wl, self.res, self.closed = threading.Condition(), threading.Lock(), {}, False
        self.net, self.nav_t, self.targets, self.dialogs = {}, 0.0, [], []
        with show.SPAWN: self._spawn(path)
        threading.Thread(target=self._reader, daemon=True).start()
        tid = self.call('Target.createTarget', {'url': 'about:blank'})['targetId']
        self.sid = self.call('Target.attachToTarget', {'targetId': tid, 'flatten': True})['sessionId']
    def _spawn(self, path):
        # плотность x2 задается самому браузеру: иначе screencast отдает кадры 393x764, а не 786x1528 (эмуляция x2 его не меняет)
        a_r, a_w = os.pipe(); b_r, b_w = os.pipe(); self.ud = self.profile or tempfile.mkdtemp(prefix='record-web-')
        def pre():
            x, y = os.dup(a_r), os.dup(b_w); os.dup2(x, 3); os.dup2(y, 4)
        self.p = subprocess.Popen([path, '--headless=new', '--remote-debugging-pipe', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
                                   '--force-color-profile=srgb', '--mute-audio', f'--force-device-scale-factor={DPR}', f'--window-size={VW},{VH}',
                                   '--user-data-dir=' + self.ud, 'about:blank'], preexec_fn=pre, close_fds=False,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(a_r); os.close(b_w)
        self.w = os.fdopen(a_w, 'wb', buffering=0); self.r = os.fdopen(b_r, 'rb', buffering=0); self.buf = b''; self.n = 0
    def _send(self, msg):
        with self.wl: self.w.write(json.dumps(msg).encode() + b'\0')
    def _reader(self):
        while True:
            try: m = self._msg()
            except Exception:
                with self.cv: self.closed = True; self.cv.notify_all()
                return
            if 'id' in m:
                with self.cv: self.res[m['id']] = m; self.cv.notify_all()
                continue
            meth, p = m.get('method'), m.get('params', {})
            if meth == 'Page.screencastFrame':
                data = base64.b64decode(p['data']); i = len(self.frames)
                path = os.path.join(self.frames_dir, f'{i:06d}.jpg'); open(path, 'wb').write(data)
                md = p['metadata']; size = jpeg_size(data)
                if size != (VW * DPR, VH * DPR) or abs(md.get('pageScaleFactor', 1) - 1) > 1e-3 or md.get('offsetTop', 0):
                    self.bad.append(dict(i=i, size=size, scale=md.get('pageScaleFactor'), offsetTop=md.get('offsetTop')))
                self.frames.append((md['timestamp'], path, time.time()))
                self._send({'id': 10 ** 9 + i, 'method': 'Page.screencastFrameAck', 'params': {'sessionId': p['sessionId']}, 'sessionId': self.sid})
            elif meth == 'Network.requestWillBeSent':
                u = p.get('request', {}).get('url', '')
                # ждем только то, что рисует страницу: документы во фреймах (реклама, счетчики), blob и долгие соединения не считаем
                if p.get('type') not in ('WebSocket', 'EventSource', 'Ping', 'Media', 'Document', 'Other', 'Manifest', 'CSPViolationReport') and not u.startswith(('blob:', 'data:')):
                    self.net[p['requestId']] = (time.time(), p.get('type'), u[:120])
            elif meth in ('Network.loadingFinished', 'Network.loadingFailed'):
                self.net.pop(p.get('requestId'), None)
            elif meth == 'Page.frameNavigated' and not p.get('frame', {}).get('parentId'):
                self.nav_t = time.time()
            elif meth == 'Target.targetCreated' and p.get('targetInfo', {}).get('type') == 'page':
                self.targets.append(p['targetInfo'])
            elif meth == 'Page.javascriptDialogOpening':   # окно alert/confirm держит касания: закрываем «отмена», ничего не подтверждаем
                self.dialogs.append(p.get('message', '')[:100])
                self._send({'id': 2 * 10 ** 9 + len(self.dialogs), 'method': 'Page.handleJavaScriptDialog', 'params': {'accept': False}, 'sessionId': self.sid})
    def call(self, method, params=None, page=False, timeout=60):
        self.n += 1; my = self.n; msg = {'id': my, 'method': method, 'params': params or {}}
        if page: msg['sessionId'] = self.sid
        self._send(msg); end = time.time() + timeout
        with self.cv:
            while my not in self.res:
                if self.closed: raise RuntimeError('браузер закрылся')
                left = end - time.time()
                if left <= 0: raise RuntimeError(f'{method}: браузер не ответил за {timeout} с')
                self.cv.wait(left)
            m = self.res.pop(my)
        if 'error' in m: raise RuntimeError(f"{method}: {m['error']}")
        return m.get('result', {})
    def inflight(self, max_age=6.0):
        """Сколько запросов страницы еще идет (долгие соединения старше max_age не считаются)."""
        now = time.time(); return sum(1 for t, _, _ in list(self.net.values()) if now - t < max_age)
    def screenshot(self, path):
        open(path, 'wb').write(base64.b64decode(self.call('Page.captureScreenshot', {'format': 'png'}, page=True)['data']))
    def close(self):
        if not self.profile: return super().close()
        try: self.call('Browser.close', timeout=5)   # штатное закрытие: куки и вход записываются в профиль
        except Exception: pass
        try: self.p.wait(10)
        except Exception: self.p.kill()

# ---------------------------------------------------------------- код в странице: поиск элементов, рамки, баннеры, признаки смены экрана
LIB = r'''
(() => {
if (window.__rw && window.__rw.v === 5) return;
const W = () => innerWidth, H = () => innerHeight;
const norm = s => (s || '').replace(/[​-‍﻿­]/g, '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim();
const R = e => e.getBoundingClientRect(), cs = e => getComputedStyle(e);
const area = r => Math.max(0, r.width) * Math.max(0, r.height);
const SKIP = /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|HEAD|META|LINK|IFRAME|title|desc|defs|symbol|clipPath|mask)$/;
const INTER = 'a[href],button,input,select,textarea,summary,label[for],[role=button],[role=link],[role=tab],[role=menuitem],[role=option],[role=checkbox],[role=switch],[onclick]';
const SEARCH = /search|пошук|поиск|шука|ищ|find|query|suche|buscar|szukaj|recherche|cerca/i;
const CLOSE = /close|закри|закры|dismiss|cross|скасув|hide-?banner|btn-x|icon-x|ic-x/i;
const BACK = /(^|[^a-z])back|назад|поверн|вернут|return|arrow-?left|chevron-?left|arrowleft|chevronleft|go-?back/i;
const CONSENT = /cookie|кукі|куки|consent|згод|соглас|gdpr|privacy|конфіденц|конфиденц|персональн/i;
const GATE = /(18|21)\s*\+|(18|21)\s*(рок|років|лет|years)|ваш вік|ваш возраст|your age|повнолітн|совершеннолетн|confirm.{0,20}age|підтверд.{0,30}вік|подтверд.{0,30}возраст/i;
const DECLINE = /^(відхилити( все)?|лише необхідні|тільки необхідні|тільки обов.язкові|отклонить( все)?|только необходимые|decline( all)?|reject( all)?|only necessary|necessary only|deny|refuse)$/i;
const PERSONAL = /user|login|email|e-mail|phone|tel|name|card|cvv|pass|iban|amount|sum|промо|promo|код|code|otp/i;
let ids = new WeakMap(), nid = 0;
const idOf = e => { let i = ids.get(e); if (!i) { i = ++nid; ids.set(e, i); } return i; };

function vis(e) {
  const r = R(e); if (r.width < 2 || r.height < 2) return false;
  if (e.checkVisibility && !e.checkVisibility({opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true})) return false;
  return true;
}
function paints(e) {
  const s = cs(e); if (s.backgroundImage && s.backgroundImage !== 'none') return true;
  const bg = s.backgroundColor.match(/[\d.]+/g); if (bg && (bg.length < 4 || parseFloat(bg[3]) > 0.04)) return true;
  if (parseFloat(s.borderTopWidth) > 0 && s.borderTopStyle !== 'none' && !/rgba\(.*,\s*0\)/.test(s.borderTopColor)) return true;
  return s.boxShadow && s.boxShadow !== 'none';
}
function fixedAnc(e) { for (let p = e; p && p !== document.body && p !== document.documentElement; p = p.parentElement) { const s = cs(p).position; if (s === 'fixed' || s === 'sticky') return p; } return null; }
function reachable(e) {   // можно ли увидеть элемент, прокрутив страницу или ленту (а не спрятан под обрезкой)
  const b = R(e), r = {top: b.top, bottom: b.bottom, left: b.left, right: b.right};
  for (let p = e.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
    const s = cs(p);
    if (s.overflowX !== 'visible' || s.overflowY !== 'visible') {
      const q = R(p), outY = r.bottom <= q.top + 2 || r.top >= q.bottom - 2, outX = r.right <= q.left + 2 || r.left >= q.right - 2;
      const sy = /(auto|scroll)/.test(s.overflowY) && p.scrollHeight > p.clientHeight + 1, sx = /(auto|scroll)/.test(s.overflowX) && p.scrollWidth > p.clientWidth + 1;
      if (outY && !sy) return false;
      if (outX && !sx) return false;
      // прокрутка этого контейнера приведет элемент в его окно: дальше проверяем уже окно (вложенные ленты и страница внутри div)
      if (sy) { const h = Math.min(r.bottom - r.top, q.height); r.top = q.top; r.bottom = q.top + h; }
      if (sx) { const w = Math.min(r.right - r.left, q.width); r.left = q.left; r.right = q.left + w; }
    }
    if (s.position === 'fixed') return !(r.bottom <= 0 || r.top >= H() || r.right <= 0 || r.left >= W());
  }
  return !(r.right <= 0 || r.left >= W());
}
function clip(e) {   // видимое окно элемента: экран, урезанный обрезающими предками
  let t = 0, b = H(), l = 0, rr = W();
  for (let p = e.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
    const s = cs(p);
    if (s.overflowX !== 'visible' || s.overflowY !== 'visible') {
      const q = R(p);
      if (s.overflowY !== 'visible') { t = Math.max(t, q.top); b = Math.min(b, q.bottom); }
      if (s.overflowX !== 'visible') { l = Math.max(l, q.left); rr = Math.min(rr, q.right); }
    }
    if (s.position === 'fixed') break;
  }
  return [t, b, l, rr];
}
function isClick(e) {
  if (e.matches(INTER)) return true;
  return cs(e).cursor === 'pointer' && (!e.parentElement || cs(e.parentElement).cursor !== 'pointer');
}
function textCands(t) {
  const tl = t.toLowerCase(), out = [];
  for (const e of document.body.querySelectorAll('*')) {
    if (SKIP.test(e.tagName)) continue;
    const raw = e.textContent; if (!raw || raw.length < tl.length) continue;
    const rawn = norm(raw); if (!rawn.toLowerCase().includes(tl)) continue;
    let deeper = false; for (const c of e.children) if (!SKIP.test(c.tagName) && norm(c.textContent).toLowerCase().includes(tl)) { deeper = true; break; }
    if (deeper || !vis(e)) continue;
    const it = norm(e.innerText || rawn), itl = it.toLowerCase();
    let tier = (it === t || rawn === t) ? 0 : (itl === tl || rawn.toLowerCase() === tl) ? 2 : itl.includes(tl) ? 4 : -1;
    if (tier < 0) continue;
    out.push({el: e, tier, how: 'текст', len: it.length});
  }
  return out;
}
function attrCands(t) {
  const tl = t.toLowerCase(), out = [];
  for (const e of document.body.querySelectorAll('[aria-label],[title],img[alt],[placeholder],input[value]')) {
    if (!vis(e)) continue;
    for (const k of ['aria-label', 'alt', 'title', 'placeholder', 'value']) {
      if (k === 'value' && !/^(submit|button|reset)$/.test(e.type)) continue;
      const v = norm(e.getAttribute(k)); if (!v) continue; const vl = v.toLowerCase();
      const tier = v === t ? 1 : vl === tl ? 3 : vl.includes(tl) ? 5 : -1;
      if (tier >= 0) { out.push({el: e, tier, how: k, len: v.length}); break; }
    }
  }
  return out;
}
function control(m, tlen) {   // элемент, по которому кликают: кнопка, ссылка, плитка целиком, но не весь ряд
  const vA = W() * H(), chain = [m];
  for (let p = m.parentElement, i = 0; p && p !== document.body && i < 8; p = p.parentElement, i++) {
    const q = R(p);
    if (area(q) > 0.45 * vA || q.width > W() + 1 || q.height > 0.6 * H()) break;
    if (norm(p.innerText).length > tlen + Math.max(14, tlen * 0.6)) break;
    const others = [...p.querySelectorAll(INTER)].filter(x => !chain.includes(x) && !m.contains(x) && vis(x));
    if (others.length > 2 || others.some(x => area(R(x)) > 0.2 * area(q))) break;
    chain.push(p);
  }
  let best = null; for (const c of chain) if (isClick(c)) best = c;
  return best || m;
}
function radius(c) {
  const r = R(c), lim = v => Math.min(v, r.height / 2, r.width / 2);
  const px = (e, rr) => { const s = cs(e).borderTopLeftRadius; const q = R(e); return /%/.test(s) ? parseFloat(s) / 100 * Math.min(q.width, q.height) : parseFloat(s) || 0; };
  const own = px(c);
  if (own && paints(c)) return lim(own);
  let best = 0, ba = 0;
  for (const k of c.querySelectorAll('*')) {
    const q = R(k), a = area(q); if (a < area(r) * 0.3 || !vis(k)) continue;
    const rr = px(k); if (rr && (paints(k) || /^(IMG|PICTURE|VIDEO|CANVAS)$/.test(k.tagName)) && a > ba) { ba = a; best = rr; }
  }
  return lim(best || own);
}
function free(except) {   // полоса экрана, не закрытая липкой шапкой и нижним меню
  let top = 0, bot = H();
  for (const e of document.body.querySelectorAll('*')) {
    const p = cs(e).position; if (p !== 'fixed' && p !== 'sticky') continue;
    if (except && (e.contains(except) || except.contains(e)) || !vis(e)) continue;
    const r = R(e); if (r.width < W() * 0.6 || r.height > H() * 0.4 || r.bottom <= 0 || r.top >= H()) continue;
    const yy = Math.min(Math.max((r.top + r.bottom) / 2, 1), H() - 1);   // панель под открытым окном (поиск, меню) экран не закрывает
    if (![0.1, 0.3, 0.5, 0.7, 0.9].some(k => { const h = document.elementFromPoint(r.left + r.width * k, yy); return h && e.contains(h); })) continue;
    if (r.top < H() * 0.3 && r.bottom < H() * 0.45) top = Math.max(top, r.bottom);
    else if (r.bottom >= H() - 2 && r.top > H() * 0.55) bot = Math.min(bot, r.top);
  }
  return [top, bot];
}
function tapPoint(c) {   // центр элемента; у плитки с подписью центр картинки
  const r = R(c), vr = {l: Math.max(r.left, 0), t: Math.max(r.top, 0), r: Math.min(r.right, W()), b: Math.min(r.bottom, H())};
  if (r.width >= 48 && r.height >= 56 && norm(c.innerText)) {
    let best = null, ba = 0;
    for (const k of c.querySelectorAll('img,svg,picture,video,canvas,div,span')) {
      const q = R(k), a = area(q); if (a < area(r) * 0.3 || a > area(r) * 0.9 || !vis(k)) continue;
      if (!paints(k) && !/^(IMG|svg|PICTURE|VIDEO|CANVAS)$/.test(k.tagName)) continue;
      if (norm(k.innerText) && norm(k.innerText) === norm(c.innerText)) continue;   // блок с подписью не картинка
      if (a > ba) { ba = a; best = q; }
    }
    if (best) return [best.x + best.width / 2, best.y + best.height / 2, 'картинка'];
  }
  return [(vr.l + vr.r) / 2, (vr.t + vr.b) / 2, 'центр'];
}
function hitOk(c, x, y) {
  const h = document.elementFromPoint(x, y);
  if (!h) return 'точка вне страницы';
  if (h === c || c.contains(h) || (h.contains(c) && h !== document.body && h !== document.documentElement)) return null;
  const d = h.tagName.toLowerCase() + (h.id ? '#' + h.id : '') + (typeof h.className === 'string' && h.className ? '.' + h.className.trim().split(/\s+/)[0] : '');
  return d + ' «' + norm(h.innerText).slice(0, 40) + '»';
}
function fieldTap(f) { const q = R(f); return [Math.min(Math.max(q.left + q.width / 2, 0), W()), Math.min(Math.max(q.top + q.height / 2, 0), H()), 'поле']; }
function info(c, extra) {
  const f = window.__rw.field, own = f && f.isConnected && c !== f && c.contains(f);   // у поля рамка по всей плашке, касание по самому input
  const r = R(c), [tx, ty, how] = own ? fieldTap(f) : tapPoint(c), [ft, fb] = free(c), fx = fixedAnc(c), [ct, cb, cl, cr] = clip(c);
  const inView = r.left >= Math.max(cl, 0) - 2 && r.right <= Math.min(cr, W()) + 2 && r.top >= Math.max(ft, ct) - 2 && r.bottom <= Math.min(fb, cb) + 2;
  return Object.assign({ok: true, box: [r.x, r.y, r.width, r.height], radius: radius(c), tap: [tx, ty], tapHow: how, inView, fixed: !!fx,
    free: [ft, fb], covered: inView ? hitOk(c, tx, ty) : null, label: norm(c.innerText || c.getAttribute('aria-label') || '').slice(0, 60), tag: c.tagName,
    url: location.href}, extra || {});
}
const WHERE = {
  'bottom-nav': c => { const f = fixedAnc(c); if (!f) return false; const r = R(f); return r.bottom >= H() - 4 && r.top > H() * 0.5; },
  'bottom': c => { const f = fixedAnc(c); return f ? R(f).top > H() * 0.5 : R(c).top > H() * 0.55; },
  'header': c => { if (c.closest('header,[role=banner]')) return true; const f = fixedAnc(c); return !!f && R(f).top < H() * 0.3 && R(c).bottom < H() * 0.45; },
  'top': c => R(c).top < H() * 0.4,
};
function ctxOf(e) {   // где живет элемент: панель поверх страницы (fixed, прилипшая шапка или низ) или сама страница (null)
  for (let p = e; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
    const s = cs(p);
    if (s.position === 'fixed') return p;
    if (s.position === 'sticky') {
      const r = R(p); if (r.width < W() * 0.6 || r.height > H() * 0.4) continue;
      const sc = scroller(p, 'y'), q = sc === document.scrollingElement ? {top: 0, bottom: H()} : R(sc);
      if ((s.top !== 'auto' && sc.scrollTop > 0 && Math.abs(r.top - q.top - parseFloat(s.top)) < 1.5) ||
          (s.bottom !== 'auto' && Math.abs(q.bottom - parseFloat(s.bottom) - r.bottom) < 1.5)) return p;
    }
  }
  return null;
}
function rectFor(e, other) {   // рамка e для сравнения с other: в ленте, которой нет у other, положение внутри ленты не считается
  const b = R(e), r = {top: b.top, bottom: b.bottom, left: b.left, right: b.right};
  for (let p = e.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
    if (p.contains(other)) break;
    const s = cs(p), q = R(p);
    if (/(auto|scroll)/.test(s.overflowX) && p.scrollWidth > p.clientWidth + 1) {
      r.left = Math.max(r.left, q.left); r.right = Math.min(r.right, q.right); if (r.right < r.left) { r.left = q.left; r.right = q.right; } }
    if (/(auto|scroll)/.test(s.overflowY) && p.scrollHeight > p.clientHeight + 1 && p !== document.scrollingElement) {
      r.top = Math.max(r.top, q.top); r.bottom = Math.min(r.bottom, q.bottom); if (r.bottom < r.top) { r.top = q.top; r.bottom = q.bottom; } }
  }
  return r;
}
function lcaH(a, b) {   // высота общего блока двух элементов (вместе с прокручиваемым содержимым)
  let p = a; while (p && !p.contains(b)) p = p.parentElement;
  if (!p || p === document.body || p === document.documentElement) return Infinity;
  return Math.max(R(p).height, p.scrollHeight);
}
function dist(x, a) {   // расстояние до ориентира: тот же ряд ближе всего; ниже ориентира вдвое дороже, выше вчетверо (это уже прошлый раздел)
  const p = rectFor(x, a), q = rectFor(a, x);
  const dx = Math.max(0, p.left - q.right, q.left - p.right), below = Math.max(0, p.top - q.bottom), above = Math.max(0, q.top - p.bottom);
  return Math.hypot(dx, 2 * below + 4 * above);
}
function cands(t) {
  t = norm(t); const raw = textCands(t).concat(attrCands(t)), byC = new Map();
  for (const m of raw) {
    if (!reachable(m.el)) continue;
    const c = control(m.el, m.len), old = byC.get(c);
    if (!old || m.tier < old.tier) byC.set(c, Object.assign({}, m, {c}));
  }
  const all = [...byC.values()], out = [];
  for (const x of all) {   // подпись и картинка внутри одной ссылки = одна кнопка
    const outer = all.find(y => y !== x && y.c !== x.c && y.c.contains(x.c) && isClick(y.c));
    if (outer) { outer.tier = Math.min(outer.tier, x.tier); continue; }
    out.push(x);
  }
  return out;
}
const hidAt = x => x.c.closest('[aria-hidden=true]') ? 1 : 0;
function find(spec) {
  window.__rw.field = null; let list = cands(spec.text); const q = norm(spec.text);
  if (!list.length) return {ok: false, miss: 'text', why: `нет текста «${q}»`};
  const all = list.length;
  if (spec.where) {
    const f = WHERE[spec.where]; if (!f) return {ok: false, miss: 'spec', why: 'неизвестное where: ' + spec.where + ' (есть top, bottom, bottom-nav, header)'};
    list = list.filter(x => f(x.c)); if (!list.length) return {ok: false, miss: 'where', why: `«${q}» есть (${all}), но не в зоне ${spec.where}`};
  }
  let near = false;
  if (spec.near) {   // ориентир считается, только если он в той же части экрана: меню поверх страницы не ориентир для кнопки на странице
    const nq = norm(spec.near), anc = cands(spec.near); if (!anc.length) return {ok: false, miss: 'near', why: `нет ориентира «${nq}»`};
    for (const x of list) { const cx = ctxOf(x.c); x.anc = anc.filter(a => ctxOf(a.c) === cx); }
    const used = anc.filter(a => list.some(x => x.anc.includes(a)));
    if (!used.length) return {ok: false, miss: 'near', why: `ориентир «${nq}» есть только ${anc.some(a => ctxOf(a.c)) ? 'в меню или шапке поверх страницы' : 'на странице'}, а «${q}» в другой части экрана`};
    const at = Math.min(...used.map(a => a.tier));
    list = list.filter(x => x.anc.some(a => a.tier === at));
    for (const x of list) { x.d = Infinity; for (const a of x.anc) if (a.tier === at) { const d = dist(x.c, a.c); if (d < x.d) { x.d = d; x.a = a; } } }
    // «рядом» = близко на экране или в одном небольшом блоке (карточка, раздел); иначе нужный раздел, видимо, ниже и еще не загружен
    const all0 = list.slice(); list = list.filter(x => x.d <= H() * 0.6 || lcaH(x.c, x.a.c) <= H() * 1.2);
    if (!list.length) { const m = all0.reduce((a, b) => a.d < b.d ? a : b);
      return {ok: false, miss: 'near', why: `ориентир «${nq}» есть, но «${q}» рядом с ним нет (ближайший в ${Math.round(m.d)} px)`}; }
    const md = Math.min(...list.map(x => x.d)); list = list.filter(x => x.d <= md * 1.5 + 16); near = true;
  }
  const tier = Math.min(...list.map(x => x.tier)); list = list.filter(x => x.tier === tier);
  const yx = (a, b) => (R(a.c).top - R(b.c).top) || (R(a.c).left - R(b.c).left);
  const order = list.slice().sort(yx);
  if (spec.index) { if (spec.index > order.length) return {ok: false, miss: 'index', why: `index ${spec.index}, а подходит ${order.length}`}; list = [order[spec.index - 1]]; }
  const pre = list.map(x => [x, info(x.c)]);
  pre.sort((a, b) => (b[1].inView - a[1].inView) || ((a[1].covered ? 1 : 0) - (b[1].covered ? 1 : 0)) || (hidAt(a[0]) - hidAt(b[0])) || (a[0].len - b[0].len) || yx(a[0], b[0]));
  const desc = ([x, i]) => ({index: order.indexOf(x) + 1, label: i.label, box: i.box.map(Math.round), inView: i.inView, panel: !!ctxOf(x.c),
    near: x.a ? {label: norm(x.a.c.innerText || '').slice(0, 40), box: (r => [r.x, r.y, r.width, r.height].map(Math.round))(R(x.a.c)), d: Math.round(x.d)} : null});
  if (!spec.index) {   // несколько одинаково подходящих: не угадываем, а просим уточнить
    const amb = near ? pre : pre.filter(([x, i]) => i.inView && !i.covered && !hidAt(x));
    if (amb.length > 1) return {ok: false, miss: 'ambig', why: near ? `рядом с «${norm(spec.near)}» подходит ${amb.length} «${q}»` : `на экране ${amb.length} «${q}»`,
      alts: amb.map(desc).sort((a, b) => a.index - b.index)};
  }
  const [best, bi] = pre[0]; window.__rw.cur = best.c; window.__rw.field = null;
  return Object.assign(bi, {how: best.how, tier: best.tier, n: pre.length, near: desc(pre[0]).near, alts: pre.slice(1, 6).map(desc)});
}
function lev(a, b) {
  if (!a.length || !b.length) return a.length + b.length; let p = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) { const c = [i]; for (let j = 1; j <= b.length; j++) c[j] = Math.min(p[j] + 1, c[j - 1] + 1, p[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)); p = c; }
  return p[b.length];
}
function similar(t) {   // похожие тексты на странице: подсказка при опечатке
  const q = norm(t).toLowerCase(), best = new Map(), lim = Math.max(1, Math.round(q.length * 0.34));
  for (const e of document.body.querySelectorAll('*')) {
    if (SKIP.test(e.tagName)) continue;
    let own = ''; for (const n of e.childNodes) if (n.nodeType === 3) own += n.data;
    for (const v0 of [own, e.getAttribute('aria-label'), e.getAttribute('placeholder'), e.getAttribute('title'), e.tagName === 'IMG' ? e.getAttribute('alt') : '']) {
      const v = norm(v0); if (v.length < 2 || v.length > 60 || Math.abs(v.length - q.length) > lim + 2) continue;
      const vl = v.toLowerCase(), d = lev(q, vl); if (d > lim) continue;
      const on = vis(e) && reachable(e), old = best.get(vl);
      if (!old || d < old.d || (on && !old.on)) best.set(vl, {text: v, d, on});
    }
  }
  return [...best.values()].sort((a, b) => (a.d - b.d) || (b.on - a.on)).slice(0, 5);
}
function spots(t) {   // где на экране сейчас этот текст (для проверки expect: новое место, а не то, что было до шага)
  return cands(t).map(x => { const r = R(x.c); return {box: [r.x, r.y, r.width, r.height].map(Math.round), on: r.bottom > 0 && r.top < H() && r.right > 0 && r.left < W(),
    label: norm(x.c.innerText || x.c.getAttribute('aria-label') || '').slice(0, 40)}; });
}
function mainScroller() {   // что прокрутит палец посреди экрана: страница или ее основной блок
  for (let e = document.elementFromPoint(W() / 2, H() / 2); e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
    const s = cs(e); if (/(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 1 && R(e).height > H() * 0.3) return e;
  }
  const se = document.scrollingElement; return se.scrollHeight > se.clientHeight + 1 ? se : null;
}
async function swipe() {   // один взмах пальцем вниз по странице: на три четверти свободной части экрана
  const sc = mainScroller(); if (!sc) return {ok: false, why: 'страница не прокручивается'};
  let [ft, fb] = free(null); if (sc !== document.scrollingElement) { const q = R(sc); ft = Math.max(ft, q.top); fb = Math.min(fb, q.bottom); }
  const max = sc.scrollHeight - sc.clientHeight, dy = Math.min(Math.round((fb - ft) * 0.75), max - sc.scrollTop);
  if (dy < 2) return {ok: true, moved: 0, end: true, h: sc.scrollHeight};
  const m = await anim(sc, 'scrollTop', dy, 600);
  return {ok: true, moved: Math.abs(m), end: sc.scrollTop >= sc.scrollHeight - sc.clientHeight - 2, h: sc.scrollHeight};
}
function measure() { const c = window.__rw.cur; if (!c || !c.isConnected) return {ok: false, why: 'элемент пропал со страницы'}; return info(c); }
function scroller(e, axis) {
  for (let p = e.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
    const s = cs(p);
    if (axis === 'y' && /(auto|scroll)/.test(s.overflowY) && p.scrollHeight > p.clientHeight + 1) return p;
    if (axis === 'x' && /(auto|scroll)/.test(s.overflowX) && p.scrollWidth > p.clientWidth + 1) return p;
  }
  return axis === 'y' ? document.scrollingElement : null;
}
function anim(el, prop, delta, ms) {
  return new Promise(res => {
    const st = el.style.scrollBehavior, sn = el.style.scrollSnapType, root = document.documentElement.style.scrollBehavior;
    el.style.scrollBehavior = 'auto'; el.style.scrollSnapType = 'none'; document.documentElement.style.scrollBehavior = 'auto';
    const from = el[prop], t0 = performance.now();
    const f = now => { const k = Math.min(1, (now - t0) / ms), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      el[prop] = from + delta * e;
      if (k < 1) requestAnimationFrame(f); else { el.style.scrollBehavior = st; el.style.scrollSnapType = sn; document.documentElement.style.scrollBehavior = root; res(el[prop] - from); } };
    requestAnimationFrame(f);
  });
}
async function scrollCur(place, force) {   // плавно, как пальцем: элемент встает в свободную часть экрана (центр на доле place сверху)
  const c = window.__rw.cur; if (!c || !c.isConnected) return {ok: false, why: 'элемент пропал со страницы'};
  let mx = 0, my = 0, [ft, fb] = free(c), r = R(c); const sc = scroller(c, 'y');
  if (sc !== document.scrollingElement) { const q = R(sc); ft = Math.max(ft, q.top); fb = Math.min(fb, q.bottom); }   // страница прокручивается внутри div
  const band = fb - ft, k = place || 0.45;
  // force: после поиска по странице цель не остается у самого края экрана
  if (force ? (r.top < ft + band * 0.06 || r.bottom > ft + band * 0.8) : (r.top < ft + 4 || r.bottom > fb - 4)) {
    const want = r.height < band - 16 ? ft + band * k - r.height / 2 : ft + 8;
    const max = sc.scrollHeight - sc.clientHeight; let dy = r.top - want; dy = Math.max(-sc.scrollTop, Math.min(max - sc.scrollTop, dy));
    if (Math.abs(dy) > 1) my += Math.abs(await anim(sc, 'scrollTop', dy, Math.min(1600, 450 + Math.abs(dy) * 0.45)));
  }
  r = R(c);
  if (r.left < 0 || r.right > W()) {
    const sc = scroller(c, 'x');
    if (sc) { const q = R(sc); let dx = r.left + r.width / 2 - (q.left + q.width / 2); dx = Math.max(-sc.scrollLeft, Math.min(sc.scrollWidth - sc.clientWidth - sc.scrollLeft, dx));
      if (Math.abs(dx) > 1) mx += Math.abs(await anim(sc, 'scrollLeft', dx, Math.min(1400, 450 + Math.abs(dx) * 0.5))); }
  }
  return {ok: true, moved: mx + my, mx, my};
}
function freeze() {   // перед касанием: карусели и бегущие строки меняются сами, их смена не считается откликом на касание
  const c = window.__rw.field || window.__rw.cur, out = [];
  for (const e of document.body.querySelectorAll('*')) {
    const s = cs(e); if (s.overflowX === 'visible' && s.overflowY === 'visible') continue;
    const q = R(e); if (q.width < W() * 0.6 || q.height > H() * 0.6 || q.height < 24 || q.bottom <= 0 || q.top >= H()) continue;
    if ((c && c.isConnected && e.contains(c)) || fixedAnc(e)) continue;   // лента с целью касания и окна поверх страницы считаются
    out.push(e);
  }
  window.__rw.zones = out; return out.length;
}
function sig() {   // что видно на экране: тексты, картинки, поля с их местом; третий знак = внутри карусели
  const out = [], w = W(), h = H(), z = (window.__rw.zones || []).filter(x => x.isConnected);
  for (const e of document.body.querySelectorAll('*')) {
    if (SKIP.test(e.tagName)) continue;
    let own = ''; for (const n of e.childNodes) if (n.nodeType === 3) own += n.data; own = norm(own);
    const media = /^(IMG|svg|VIDEO|CANVAS|INPUT|TEXTAREA|SELECT)$/.test(e.tagName);
    if (!own && !media) continue;
    const r = R(e); if (r.width < 2 || r.height < 2 || r.bottom <= 0 || r.top >= h || r.right <= 0 || r.left >= w) continue;
    if (e.checkVisibility && !e.checkVisibility({opacityProperty: true, visibilityProperty: true})) continue;
    out.push([idOf(e), e.tagName + '|' + own.slice(0, 40) + '|' + (e.tagName === 'IMG' ? (e.currentSrc || '').slice(-30) : '') + '|' +
      [r.x, r.y, r.width, r.height].map(v => Math.round(v / 6)).join(',') + (e.value !== undefined && /INPUT|TEXTAREA/.test(e.tagName) ? '|' + e.value : ''),
      z.some(x => x.contains(e)) ? 1 : 0]);
  }
  // какой слой сверху в точках сетки 5x8: окно поверх страницы (поиск, меню) меняет почти все точки, даже если страница под ним та же
  const layer = e => { for (let p = e; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
    const s = cs(p); if (s.position === 'fixed' || s.position === 'sticky') return p;
    if (s.position === 'absolute' && area(R(p)) >= 0.3 * w * h) return p; } return null; };
  for (let gy = 0; gy < 8; gy++) for (let gx = 0; gx < 5; gx++) {
    const e = document.elementFromPoint(w * (gx + 0.5) / 5, h * (gy + 0.5) / 8), l = e ? layer(e) : null;
    out.push(['g' + gx + '_' + gy, 'слой|' + (l ? idOf(l) : 'страница'), e && z.some(x => x.contains(e)) && !l ? 1 : 0]);
  }
  return out;
}
function busy() {
  const w = W(), h = H(); let imgs = 0, skel = 0;
  for (const im of document.images) { const r = R(im); if (r.width > 4 && r.bottom > 0 && r.top < h && r.right > 0 && r.left < w && !im.complete) imgs++; }
  for (const e of document.querySelectorAll('[class*=skeleton i],[class*=shimmer i],[class*=spinner i],[class*=loader i],[class*=preload i],[aria-busy=true],[class*=loading i]')) {
    const r = R(e); if (r.width > 16 && r.height > 8 && r.bottom > 0 && r.top < h && vis(e)) skel++; }
  return {ready: document.readyState, imgs, skel, quiet: performance.now() - (window.__rw.lastMut || 0), url: location.href};
}
function warm() {   // картинки каруселей рядом с экраном грузим заранее: иначе при смене слайда в ролике мелькает пустой баннер
  let n = 0;
  for (const im of document.images) { if (im.loading !== 'lazy') continue; const r = R(im); if (r.bottom > -H() && r.top < 2 * H()) { im.loading = 'eager'; n++; } }
  return n;
}
function pageBg() {   // фон страницы: первый непрозрачный фон во всю ширину и почти во весь экран под серединой экрана (или body, html)
  const opq = e => { const m = cs(e).backgroundColor.match(/[\d.]+/g); return m && (m.length < 4 || parseFloat(m[3]) > 0.9) ? m.slice(0, 3).map(Number) : null; };
  const hex = c => c.map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase();
  for (let e = document.elementFromPoint(W() / 2, H() / 2); e; e = e.parentElement) {
    if (fixedAnc(e)) continue;
    const r = R(e), o = opq(e); if (o && r.width >= W() - 1 && (r.height >= H() * 0.9 || e === document.body || e === document.documentElement)) return hex(o);
  }
  const o = opq(document.body) || opq(document.documentElement); return o ? hex(o) : null;
}
function fieldOk(e) {   // только поле поиска: в личные и платежные поля не печатаем
  if (e.tagName === 'INPUT' && !/^(text|search|)$/.test((e.getAttribute('type') || '').toLowerCase())) return false;
  if (e.disabled || e.readOnly || !vis(e)) return false;
  if (/^(username|email|tel|name|given-name|family-name|cc-|current-password|new-password|one-time-code)/.test(e.getAttribute('autocomplete') || '')) return false;
  const f = e.closest('form'); if (f && f.querySelector('input[type=password],input[type=email],input[type=tel]')) return false;
  return true;
}
function fieldText(e) { return [e.name, e.id, typeof e.className === 'string' ? e.className : '', e.placeholder, e.getAttribute('aria-label'), e.title, e.getAttribute('data-testid'), e.getAttribute('enterkeyhint'),
  e.closest('form') ? e.closest('form').getAttribute('action') : '', e.closest('[role=search]') ? 'search' : '', ...(e.labels ? [...e.labels].map(l => l.innerText) : [])].join(' '); }
function findField(into) {
  const isSearch = !into || /^(search|пошук|поиск|шукати|искать)$/i.test(into); const out = [];
  for (const e of document.querySelectorAll('input,textarea,[contenteditable=true],[contenteditable=""]')) {
    if (!fieldOk(e) || !reachable(e)) continue; const hay = fieldText(e); let s = 0;
    if (isSearch) { if (e.type === 'search') s += 3; if (SEARCH.test(hay)) s += 3; if (SEARCH.test(location.pathname + location.hash)) s += 1; if (e === document.activeElement) s += 1; }
    else { if (!norm(hay).toLowerCase().includes(norm(into).toLowerCase())) continue; s += 5; }
    if (PERSONAL.test(hay) && !SEARCH.test(hay)) continue;
    out.push([s, e]);
  }
  out.sort((a, b) => b[0] - a[0]);
  if (!out.length || (isSearch && out[0][0] < 1 && out.length > 1)) return {ok: false, why: 'нет поля поиска на экране'};
  const e = out[0][1], ctl = fieldCtl(e); window.__rw.cur = ctl; window.__rw.field = e;
  return Object.assign(info(ctl), {how: 'поле', score: out[0][0], input: [R(e).x, R(e).y, R(e).width, R(e).height]});
}
function fieldCtl(e) {   // поле целиком, как его видит игрок: плашка с лупой и крестиком, а не только input
  const r0 = R(e); let best = e;
  for (let p = e.parentElement, i = 0; p && p !== document.body && i < 5; p = p.parentElement, i++) {
    const q = R(p);
    if (q.height > Math.max(r0.height * 1.9, r0.height + 28) || q.width > W() + 1 || q.width > r0.width + 140) break;
    if (p.querySelectorAll('input,textarea,select').length > 1) break;
    if ([...p.querySelectorAll(INTER)].some(x => x !== e && vis(x) && R(x).width > 64)) break;   // рядом кнопка «Скасувати»: это уже ряд, не поле
    if (paints(p)) best = p;
  }
  return best;
}
function clickAnc(e, maxW, maxH) { let c = null; for (let p = e, i = 0; p && i < 5; p = p.parentElement, i++) { const q = R(p); if (q.width > maxW || q.height > maxH) break; if (isClick(p)) c = p; } return c; }
function hayOf(e) { const cn = typeof e.className === 'string' ? e.className : (e.className && e.className.baseVal) || '';
  const u = e.querySelector ? e.querySelector('use') : null;
  return [e.getAttribute('href'), e.getAttribute('aria-label'), e.getAttribute('title'), e.getAttribute('data-testid'), e.getAttribute('data-id'), e.id, cn, u ? (u.getAttribute('href') || u.getAttribute('xlink:href')) : ''].join(' '); }
const ICONS = {search: SEARCH, back: BACK, close: CLOSE, menu: /menu|burger|hamburger|меню|nav-?toggle|sidebar|drawer/i,
  home: /home|головн|главн/i, profile: /profile|account|avatar|профіл|профил|кабінет|кабинет/i, filter: /filter|фільтр|фильтр|sort/i};
function findIcon(name, zone) {   // иконка-кнопка без текста по признакам в разметке (поиск, назад, меню, крестик)
  window.__rw.field = null;
  const re = ICONS[name] || new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'), out = [], seen = new Set();
  for (const e of document.body.querySelectorAll('a,button,[role=button],svg,img,span,i,div')) {
    if (!vis(e)) continue; const tx = norm(e.innerText || '');
    if (!re.test(hayOf(e) + ' ' + (tx.length < 16 ? tx : '') + ' ' + (e.tagName === 'IMG' ? e.src + ' ' + e.alt : ''))) continue;
    const c = clickAnc(e, 220, 80) || (e.matches(INTER) ? e : null); if (!c || seen.has(c) || !reachable(c)) continue; seen.add(c);
    const r = R(c); if (r.width > 220 || r.height > 80) continue;
    if (zone === 'top' && r.top > H() * 0.35) continue;
    if (zone && zone !== 'top' && WHERE[zone] && !WHERE[zone](c)) continue;
    out.push(c);
  }
  out.sort((a, b) => (R(a).top - R(b).top) || (R(a).left - R(b).left));
  if (!out.length) return {ok: false, miss: zone === 'any' ? 'text' : 'where', why: 'нет такой иконки'};
  window.__rw.cur = out[0]; window.__rw.field = null; return Object.assign(info(out[0]), {how: 'иконка', n: out.length});
}
function svgIsX(svg) {   // крестик: закрашены диагонали и центр, середины краев пустые
  const geo = [...svg.querySelectorAll('path,line,polyline,polygon,rect,circle,ellipse')]; if (!geo.length || geo.length > 6) return false;
  let bb; try { bb = svg.getBBox(); } catch (e) { return false; } if (bb.width < 1 || bb.height < 1 || bb.width / bb.height < 0.6 || bb.width / bb.height > 1.6) return false;
  const hit = (fx, fy) => { const p = new DOMPoint(bb.x + bb.width * fx, bb.y + bb.height * fy); return geo.some(g => { try { const s = cs(g);
    return (s.fill !== 'none' && g.isPointInFill(p)) || (s.stroke !== 'none' && parseFloat(s.strokeWidth) > 0 && g.isPointInStroke(p)); } catch (e) { return false; } }); };
  return [[.2, .2], [.8, .2], [.2, .8], [.8, .8], [.5, .5]].every(([x, y]) => hit(x, y)) && ![[.5, .06], [.06, .5], [.94, .5], [.5, .94]].some(([x, y]) => hit(x, y));
}
function xLike(e) {
  const t = norm(e.innerText || e.textContent);
  if (/^[×✕✖╳xX]$/.test(t)) return true;
  if (t.length > 2) return false;
  if (CLOSE.test(hayOf(e))) return true;
  const svg = e.tagName === 'svg' ? e : e.querySelector('svg'); if (svg && svgIsX(svg)) return true;
  const img = e.tagName === 'IMG' ? e : e.querySelector('img'); return !!(img && /close|cross|krest/i.test(img.src + ' ' + img.alt));
}
function banners() {   // рекламные и «скачай приложение» плашки с крестиком, окна cookie, возрастные окна
  const res = [], seen = new Set();
  for (const e of document.body.querySelectorAll('button,a,[role=button],svg,img,span,div,i')) {
    const r = R(e); if (r.width > 56 || r.height > 56 || r.width < 8 || r.height < 8 || !vis(e) || !xLike(e)) continue;
    const c = clickAnc(e, 64, 64) || e; if (seen.has(c)) continue; seen.add(c);
    const f = fixedAnc(c), cr = R(c); if (!f && cr.top > H() * 0.3) continue;   // крестики внутри контента не трогаем
    if (cr.bottom <= 0 || cr.top >= H() || cr.right <= 0 || cr.left >= W()) continue;
    let box = c.parentElement; while (box && box !== document.body && R(box).width < W() * 0.7) box = box.parentElement;
    if (!box || box === document.body) continue;
    const br = R(box), txt = norm(box.innerText).slice(0, 400);
    const kind = CONSENT.test(txt) ? 'consent' : (GATE.test(txt) && area(br) > W() * H() * 0.3) ? 'gate' : 'promo';
    if (hitOk(c, cr.x + cr.width / 2, cr.y + cr.height / 2)) continue;
    res.push({kind, x: cr.x + cr.width / 2, y: cr.y + cr.height / 2, text: txt.slice(0, 100), box: [br.x, br.y, br.width, br.height].map(Math.round)});
  }
  for (const e of document.body.querySelectorAll('*')) {
    const p = cs(e).position; if ((p !== 'fixed' && p !== 'sticky') || !vis(e)) continue;
    const r = R(e); if (r.width < W() * 0.7 || r.height < 40 || r.bottom <= 0 || r.top >= H()) continue;
    const txt = norm(e.innerText).slice(0, 1500);
    if (CONSENT.test(txt) && txt.length < 1200 && e.querySelector('button,a,[role=button]')) {
      const d = [...e.querySelectorAll('button,a,[role=button]')].find(b => DECLINE.test(norm(b.innerText)) && vis(b));
      const q = d ? R(d) : null; res.push({kind: 'consent', x: q ? q.x + q.width / 2 : null, y: q ? q.y + q.height / 2 : null, decline: !!d, text: txt.slice(0, 100), box: [r.x, r.y, r.width, r.height].map(Math.round)});
    } else if (GATE.test(txt) && area(r) > W() * H() * 0.3) res.push({kind: 'gate', text: txt.slice(0, 160), box: [r.x, r.y, r.width, r.height].map(Math.round)});
  }
  return res;
}
function appBanner() {   // плашка «скачай приложение» без крестика, которую не удалось закрыть: только предупреждение
  for (const e of document.body.querySelectorAll('*')) {
    const s = cs(e); if (s.position !== 'fixed' && s.position !== 'sticky') continue;
    const r = R(e); if (r.width < W() * 0.7 || r.height < 36 || r.height > 200 || r.top > H() * 0.25 || r.bottom <= 0 || !vis(e)) continue;
    const t = norm(e.innerText).slice(0, 200);
    if (t.length < 160 && /завантаж|скачат|скачай|download|install|встанов|установ|додаток|приложени|app store|google play/i.test(t)) return t.slice(0, 80);
  }
  return null;
}
window.__rw = {v: 5, field: null, zones: [], find, measure, scrollCur, freeze, sig, busy, warm, pageBg, findField, findIcon, banners, appBanner, similar, spots, swipe, mainScroller,
  cur: null, lastMut: performance.now(),
  focus: () => { const c = window.__rw.field || window.__rw.cur; if (c && c.isConnected) c.focus(); return !!c; },
  active: () => { const a = document.activeElement; if (!a || !/INPUT|TEXTAREA/.test(a.tagName) && !a.isContentEditable) return null;
    return {value: a.value !== undefined ? a.value : a.innerText, same: a === window.__rw.field}; },
  click: () => { const c = window.__rw.cur; if (!c || !c.isConnected) return false; c.click(); return true; },
  risky: () => {   // оплата, вывод, ставка: текст про деньги и сумма в поле или отправка формы
    const c = window.__rw.cur; if (!c || !c.isConnected) return null;
    const t = norm(c.innerText || c.value || c.getAttribute('aria-label') || '').slice(0, 60);
    if (!/оплат|сплат|\bpay|депозит|deposit|поповн|пополн|вивест|вывест|вивод|вывод|withdraw|cash ?out|ставк|\bbet\b|підтверд|подтверд|confirm|купит|купуй|придба|\bbuy\b/i.test(t)) return null;
    const vis = i => { const r = R(i); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < H(); };
    const sum = [...document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio])')].some(i => vis(i) && /^[\s\d.,]*\d[\s\d.,]*$/.test(i.value || ''));
    const sub = (c.getAttribute('type') || '').toLowerCase() === 'submit' || (c.tagName === 'BUTTON' && c.form && !c.getAttribute('type'));
    return (sum || sub) ? t : null; }};
new MutationObserver(() => { window.__rw.lastMut = performance.now(); }).observe(document, {childList: true, subtree: true, characterData: true});
document.addEventListener('click', e => { const a = e.target.closest && e.target.closest('a[target]'); if (a && a.target !== '_self') a.target = '_self'; }, true);   // новые вкладки не записать: открываем в этой же
window.open = (u) => { if (u) location.href = u; return window; };
})();
'''

PRIV = r"""
(() => {
if (window.__rwPriv) return;
const CFG = __CFG__;
const EMAIL = /[\w.+-]+@[\w-]+(\.[\w-]+)+/, PHONE = /(\+|\b00)\s?\d[\d\s().-]{7,}\d/, PHONE_LOCAL = /\b0\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b/,
      CARD = /\b(?:\d[ -]?){12,18}\d\b|[*•xX]{2,}[ -]?\d{4}\b/, IBAN = /\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,4})?\b/,
      PID = /\b(ID|айді|ідентифікатор|идентификатор|номер (рахунку|счета|гравця|игрока)|account|player)\s*[:#№]?\s*\d{5,}/i;
const st = document.createElement('style'); st.textContent = '[data-rw-blur]{filter:blur(8px)!important}';
const P = window.__rwPriv = {n: 0, skipped: 0};
function mark(e) { if (!e || e.nodeType !== 1 || e.hasAttribute('data-rw-blur')) return; e.setAttribute('data-rw-blur', ''); P.n++; }
function hit(s) {
  if (!s) return false; s = s.trim(); if (!s || s.length > 400) return false;
  if (CFG.auto && (EMAIL.test(s) || PHONE.test(s) || PHONE_LOCAL.test(s) || CARD.test(s) || IBAN.test(s) || PID.test(s))) return true;
  const l = s.toLowerCase(); return CFG.texts.some(x => l.includes(x));
}
function text(t) {
  if (!hit(t.textContent)) return; const p = t.parentElement;
  if (!p || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|TITLE)$/.test(p.tagName)) return;
  if (p === document.body || p === document.documentElement) { P.skipped++; return; }
  mark(p);
}
function field(i) {
  if (!CFG.auto) return; const t = (i.type || '').toLowerCase(), ac = (i.autocomplete || '').toLowerCase();
  if (/^(email|tel|password)$/.test(t) || /cc-|email|tel|username/.test(ac) || hit(i.value)) mark(i);
}
function scan(root) {
  if (!st.isConnected && document.documentElement) (document.head || document.documentElement).appendChild(st);
  if (!root) return; if (root.nodeType === 3) return text(root);
  if (root.nodeType !== 1 && root.nodeType !== 9) return;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); let t; while ((t = w.nextNode())) text(t);
  if (CFG.css) { if (root.matches && root.matches(CFG.css)) mark(root); root.querySelectorAll(CFG.css).forEach(mark); }
  if (root.matches && root.matches('input,textarea')) field(root); root.querySelectorAll('input,textarea').forEach(field);
}
P.scan = () => { scan(document); return P.n; };
new MutationObserver(ms => { for (const m of ms) {
  if (m.type === 'characterData') text(m.target);
  else if (m.type === 'attributes') { const e = m.target; if (e.matches('input,textarea')) field(e); if (CFG.css && e.matches(CFG.css)) mark(e); }
  else m.addedNodes.forEach(scan);
} }).observe(document, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['value', 'class', 'id']});
document.addEventListener('input', e => { if (e.target.matches && e.target.matches('input,textarea')) field(e.target); }, true);
setInterval(() => document.querySelectorAll('input,textarea').forEach(field), 250);   // значение, которое сайт подставил сам, без события
scan(document); document.addEventListener('DOMContentLoaded', () => scan(document));
})();
"""

def priv_script(cfg):
    css = ','.join(x[4:].strip() for x in cfg['items'] if x.lower().startswith('css:'))
    texts = [x.lower() for x in cfg['items'] if not x.lower().startswith('css:') and x.strip()]
    return PRIV.replace('__CFG__', json.dumps(dict(auto=cfg['auto'], css=css, texts=texts), ensure_ascii=False))

def profile_busy(profile):
    """Профиль занят окном входа или другой записью: Chrome держит ссылку SingletonLock = «хост-pid»."""
    lock = os.path.join(profile, 'SingletonLock')
    if not os.path.lexists(lock): return None
    try: pid = int(os.readlink(lock).rsplit('-', 1)[1]); os.kill(pid, 0); return pid
    except (OSError, ValueError, IndexError): return None

def login(url, profile, timeout=1800):
    """Окно Chrome с отдельным профилем в мобильном виде. Человек сам входит в тестовый аккаунт и закрывает окно; вход остается в профиле."""
    browser = show.find_browser()
    if not browser: die('не нашел Chrome, Edge или Chromium. Путь можно задать в SHOW_BROWSER')
    profile = os.path.abspath(os.path.expanduser(profile)); os.makedirs(profile, exist_ok=True)
    if profile_busy(profile): die(f'профиль {profile} уже открыт в другом окне Chrome: закрой его и запусти снова')
    a_r, a_w = os.pipe(); b_r, b_w = os.pipe()
    def pre():
        x, y = os.dup(a_r), os.dup(b_w); os.dup2(x, 3); os.dup2(y, 4)
    p = subprocess.Popen([browser, '--remote-debugging-pipe', '--no-first-run', '--no-default-browser-check', '--user-data-dir=' + profile,
                          '--user-agent=' + UA, f'--window-size={VW + 40},{852 + 120}', url], preexec_fn=pre, close_fds=False,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(a_r); os.close(b_w)
    w = os.fdopen(a_w, 'wb', buffering=0); r = os.fdopen(b_r, 'rb', buffering=0); buf = b''; n = [0]
    def send(method, params=None):
        n[0] += 1; w.write(json.dumps({'id': n[0], 'method': method, 'params': params or {}}).encode() + b'\0'); return n[0]
    host = urllib.parse.urlparse(url).hostname or ''
    print(f'Открыл окно Chrome с профилем {profile}.\nВойди в тестовый аккаунт сам (пароль и коды видишь только ты) и закрой окно.', flush=True)
    import select
    end, cookies, seen, empty, last_poll, want = time.time() + timeout, None, False, 0, 0.0, {}
    while True:
        now = time.time()
        if now - last_poll >= 1.0:   # вкладки опрашиваем раз в секунду: окно считается закрытым, когда вкладок нет 2 опроса подряд
            want[send('Target.getTargets')] = 'targets'; last_poll = now
        if now > end:
            print('время вышло, закрываю окно'); want[send('Storage.getCookies')] = 'cookies'; end = float('inf')
        if not select.select([r], [], [], 0.3)[0]: continue
        chunk = r.read(1 << 20)
        if not chunk: break
        buf += chunk
        while b'\0' in buf:
            raw, buf = buf.split(b'\0', 1); m = json.loads(raw); kind = want.pop(m.get('id'), None)
            if kind == 'targets':
                tabs = [t for t in m.get('result', {}).get('targetInfos', []) if t.get('type') == 'page' and not t.get('url', '').startswith(('devtools:', 'chrome-extension:'))]
                if tabs: seen, empty = True, 0
                elif seen:
                    empty += 1
                    if empty == 2 and cookies is None: want[send('Storage.getCookies')] = 'cookies'
            elif kind == 'cookies':
                cookies = [c for c in m.get('result', {}).get('cookies', []) if host.endswith(c.get('domain', '').lstrip('.')) or c.get('domain', '').lstrip('.').endswith(host)]
                send('Browser.close')   # штатное закрытие: куки записываются на диск
    try: p.wait(15)
    except subprocess.TimeoutExpired: p.kill()
    if cookies is None: print('окно закрыто')
    else: print(f'окно закрыто, куки сайта {host} в профиле: {len(cookies)}' + ('' if cookies else '. Похоже, вход не сохранился'))
    print(f'дальше: python3 {os.path.abspath(__file__)} {url} steps.json --out DIR --profile {profile}')

# ---------------------------------------------------------------- запись
class Session:
    def __init__(self, url, out, lang, keep_banners, log=print, profile=None, blur=None):
        self.url, self.out, self.lang, self.keep, self.log, self.profile, self.blur = url, out, lang, keep_banners, log, profile, blur
        self.tmp = tempfile.mkdtemp(prefix='record-web-'); fr = os.path.join(self.tmp, 'frames'); os.makedirs(fr)
        browser = show.find_browser()
        if not browser: die('не нашел Chrome, Edge или Chromium. Путь можно задать в SHOW_BROWSER')
        self.b = Rec(browser, fr, profile); self.steps = []; self.last_settle = time.time(); self.sigA = None; self.t_stop = None; self.say_map = {}
        self.pending = None; self.cleans = []; self.cur_n = 0; self.t_ready = None; self.closed = set()

    # --- страница
    def js(self, expr, timeout=40):
        r = self.b.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, page=True, timeout=timeout)
        if r.get('exceptionDetails'):
            raise RuntimeError('ошибка в странице: ' + json.dumps(r['exceptionDetails'], ensure_ascii=False)[:500])
        return r.get('result', {}).get('value')
    def rw(self, call, tries=12):
        for i in range(tries):   # во время перехода страницы контекст пропадает: ждем новый
            try: return self.js(LIB + ';\nwindow.__rw.' + call)
            except RuntimeError as e:
                if i == tries - 1 or not re.search(r'context|destroyed|navigat|Cannot find|uniqueContextId|не ответил', str(e)): raise
                time.sleep(0.25)
    def href(self):
        try: return self.js('location.href')
        except RuntimeError: return None

    def settle(self, min_wait=0.6, max_wait=10.0):
        """Ждет, пока страница догрузится: документ готов, сеть стихла, DOM не меняется, картинки на экране загружены, скелетонов нет."""
        t0 = time.time(); net_ok = None; first = None; warmed = False
        while True:
            el = time.time() - t0
            try:
                if not warmed and self.rw('busy()', tries=2)['ready'] == 'complete': self.rw('warm()', tries=2); warmed = True
                bz = self.rw('busy()', tries=2)
            except (RuntimeError, TypeError): bz = None
            n = self.b.inflight()
            if n <= 1: net_ok = net_ok or time.time()   # как networkidle: одно висящее соединение не держит
            else: net_ok = None
            ok = bz and bz['ready'] == 'complete' and net_ok and time.time() - net_ok >= 0.4 and (bz['quiet'] >= 350 or el > 2.5) \
                and (bz['imgs'] == 0 or el > 5) and (bz['skel'] == 0 or el > 6)
            if ok and first is None: first = time.time()
            if ok and el >= min_wait: break
            if not ok: first = None
            if el > max_wait:
                self.log(f'  страница не успокоилась за {max_wait:.0f} с (запросов {n}, {bz}), иду дальше'); first = time.time(); break
            time.sleep(0.1)
        self.last_settle = first or time.time()
        try: self.sigA = self.rw('sig()', tries=2)
        except RuntimeError: self.sigA = None
        return self.last_settle

    def start(self):
        b = self.b; lang = self.lang
        b.call('Page.enable', page=True); b.call('Network.enable', page=True)
        b.call('Emulation.setUserAgentOverride', {'userAgent': UA, 'platform': 'iPhone', 'acceptLanguage': f'{lang},{lang}-{lang.upper()};q=0.9,en;q=0.5'}, page=True)
        b.call('Emulation.setDeviceMetricsOverride', {'width': VW, 'height': VH, 'deviceScaleFactor': DPR, 'mobile': True, 'screenWidth': VW, 'screenHeight': 852}, page=True)
        b.call('Emulation.setTouchEmulationEnabled', {'enabled': True, 'maxTouchPoints': 5}, page=True)
        b.call('Page.addScriptToEvaluateOnNewDocument', {'source': LIB}, page=True)
        if self.blur and (self.blur['auto'] or self.blur['items']):   # раньше любого скрипта сайта: личные данные не попадают ни в один кадр
            b.call('Page.addScriptToEvaluateOnNewDocument', {'source': priv_script(self.blur)}, page=True)
        self.log('открываю ' + self.url)
        b.call('Page.navigate', {'url': self.url}, page=True); time.sleep(1.0)
        self.settle(min_wait=3.0, max_wait=20)
        bot = self.js(r"""(() => { const t = (document.title + ' ' + (document.body ? document.body.innerText : '')).slice(0, 3000);
            return /just a moment|checking your browser|verify you are human|security check|captcha|проверк\S* безопасности|перевірк\S* безпеки|ви людина|вы человек/i.test(t)
              && t.length < 1500 ? t.slice(0, 120) : null; })()""")
        here = self.href() or ''
        if re.search(r'restrict|blocked|geo-?block|not-?available|unavailable', here, re.I):
            raise Fail(f'сайт перенаправил на {here}: похоже, он закрыт для этой страны или сети. Запусти запись из страны, где сайт открывается')
        if bot: raise Fail(f'сайт показывает проверку на робота: «{' '.join(bot.split())}». Такие проверки я не прохожу; пройди ее сам в окне входа: python3 record_web.py login URL --profile DIR, потом запись с --profile DIR')
        vp = self.js('JSON.stringify([innerWidth, innerHeight, devicePixelRatio, visualViewport ? visualViewport.scale : 1])')
        w, h, dpr, sc = json.loads(vp)
        if (w, h, dpr) != (VW, VH, DPR) or abs(sc - 1) > 1e-3:
            raise Fail(f'сайт не встал в экран iPhone: окно {w}x{h}, плотность {dpr}, масштаб {sc} (нужно {VW}x{VH}, x{DPR}, 1). '
                       'Похоже, у сайта нет мобильной версии')
        if not self.keep: self.close_banners()
        self.js('window.scrollTo(0, 0)'); self.settle(min_wait=1.0)
        if not self.keep: self.close_banners(quiet=0.6, cap=4)   # последний взгляд прямо перед записью
        if self.blur and (self.blur['auto'] or self.blur['items']):
            nb = self.js('window.__rwPriv ? window.__rwPriv.scan() : -1')
            if nb == -1: raise Fail('размытие личных данных не встало в страницу: записывать не буду')
            self.log(f'  размыто элементов с личными данными: {nb}')
        try: self.page_bg = self.rw('pageBg()', tries=2)
        except RuntimeError: self.page_bg = None
        self.log('запись пошла')
        b.call('Page.startScreencast', {'format': 'jpeg', 'quality': 92, 'everyNthFrame': 1, 'maxWidth': VW * DPR, 'maxHeight': VH * DPR}, page=True)
        time.sleep(1.2); self.settle(min_wait=0.3)
        if not self.keep:
            if self.close_banners(quiet=0.3, cap=4): self.settle(min_wait=0.5)   # плашка успела выехать: первый шаг начнется после ее закрытия
            left = self.rw('appBanner()')
            if left: self.log(f'  внимание: на экране осталась плашка приложения без крестика: «{left}». Она будет в ролике')
        self.t_ready = self.last_settle

    def close_banners(self, quiet=3.5, cap=12.0, mid=False):
        """Плашки «скачай приложение» и рекламу закрываем крестиком; cookie только «отклонить»; возрастное окно = стоп.
        Плашки выезжают не сразу (бывает через 3 с после загрузки), поэтому ждем, пока quiet секунд не появится новых.
        mid: посреди сценария закрываем только явные плашки (полоса с текстом про приложение или уже знакомая реклама),
        а окна, которые открыл сам шаг (поиск, меню), не трогаем."""
        t0 = last = time.time(); n = 0; told = set()
        while time.time() - t0 < cap:
            items = self.rw('banners()') or []; page = (self.href() or '').split('#')[0]
            gate = [x for x in items if x['kind'] == 'gate']
            if gate:
                raise Fail('сайт закрыт окном подтверждения (возраст или условия): «' + gate[0]['text'][:120] + '». '
                           'По правилам скилла я такие окна не подтверждаю. Запиши этот сайт вручную или дай ссылку на страницу без окна')
            todo = [x for x in items if (x['kind'] == 'promo' or (x['kind'] == 'consent' and x.get('decline'))) and x.get('x') is not None
                    and (round(x['x']), round(x['y']), x['text'][:30], page) not in self.closed]   # крестик, который не сработал, не жмем по кругу
            if mid: todo = [x for x in todo if x['kind'] == 'consent' or (x['box'][3] <= VH * 0.3 and x['text'].strip()
                            and (APP_BANNER.search(x['text']) or x['text'][:30] in {c[2] for c in self.closed}))]
            for x in items:
                if x['kind'] == 'consent' and not x.get('decline') and x['text'][:30] not in told:
                    told.add(x['text'][:30]); self.log('  окно cookie без кнопки «отклонить»: не трогаю (' + x['text'][:60] + ')')
            if todo:
                x = todo[0]; self.closed.add((round(x['x']), round(x['y']), x['text'][:30], page))
                self.log(('  закрываю плашку: ' if x['kind'] == 'promo' else '  cookie: отклоняю: ') + x['text'][:70])
                self.touch(x['x'], x['y']); n += 1; time.sleep(0.9); last = time.time(); continue
            if time.time() - last >= quiet: break
            time.sleep(0.4)
        return n

    def sweep(self):
        """Перед шагом: плашка, которая выехала во время записи, закрывается; шаг в ролике начнется после этого."""
        if self.keep: return
        if self.close_banners(quiet=0, cap=3, mid=True):
            self.settle(min_wait=0.5); self.cleans.append(self.last_settle)

    def touch(self, x, y):
        """Касание пальцем. Если браузер завис на касании, повтор один раз, потом понятная ошибка вместо минуты ожидания."""
        for k in range(2):
            t = time.time()
            try:
                self.b.call('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y, 'radiusX': 6, 'radiusY': 6, 'force': 1}]}, page=True, timeout=6)
                time.sleep(0.08)
                self.b.call('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []}, page=True, timeout=6)
                return t
            except RuntimeError as e:
                if k or 'не ответил' not in str(e):
                    raise self.snap_fail(self.cur_n, f'браузер не принял касание в точке ({x:.0f}, {y:.0f}): {e}. Запусти запись еще раз')
                self.log('  браузер не ответил на касание за 6 с, повторяю')
                try: self.b.call('Input.dispatchTouchEvent', {'type': 'touchCancel', 'touchPoints': []}, page=True, timeout=3)
                except RuntimeError: pass
                time.sleep(0.5)

    def snap_fail(self, n, msg):
        p = os.path.join(self.out, f'fail-step{n}.png')
        try: self.b.screenshot(p)
        except Exception: p = '(снимок не вышел)'
        return Fail(f'шаг {n}: {msg}\n  снимок экрана: {p}')

    # --- поиск цели
    def locate(self, n, call, what, timeout=2.5, seek=False, suggest=None):
        """Ищет цель. Если ее нет в загруженной части страницы и seek, листает страницу вниз, как пальцем (разделы, которые грузятся при прокрутке).
        suggest: какой текст сверять с похожими на странице при промахе ({вид промаха: текст}), чтобы отличить опечатку."""
        t0 = time.time(); r = None
        while True:
            r = self.rw(call) or {}
            if r.get('ok'): return r
            if r.get('miss') == 'ambig': raise self.snap_fail(n, self.ambig_msg(what, r))
            if time.time() - t0 >= timeout: break
            time.sleep(0.3)
        sought = None
        if seek and r.get('miss') in ('text', 'near'):
            got = self.seek(n, call, what)
            if got.get('ok'): return got
            r, sought = got.get('last') or r, got
        raise self.miss(n, r, what, (suggest or {}).get(r.get('miss')), sought)

    def ambig_msg(self, what, r):
        lines = []
        for a in r.get('alts', [])[:6]:
            where = 'в меню или шапке' if a.get('panel') else ('на экране' if a.get('inView') else 'ниже или в ленте')
            nr = f', до «{a["near"]["label"]}» {a["near"]["d"]} px' if a.get('near') else ''
            lines.append(f'    index {a["index"]}: «{a["label"]}» рамка {a["box"]} ({where}{nr})')
        return (f'{what}: {r.get("why")}. Не угадываю, какой нужен:\n' + '\n'.join(lines) +
                '\n  Уточни шаг: "index": N (номер сверху из списка выше), или "near" с другим ориентиром, или "where"')

    def miss(self, n, r, what, text, sought):
        """Цели нет: отличаем опечатку (есть похожий текст) от «на этой странице такого нет»."""
        msg = f'не нашел {what}: {r.get("why", "?")}'
        if sought and sought['swipes']: msg += f'. Долистал страницу до конца: {sought["swipes"]} взмахов, {sought["moved"]} px'
        elif sought: msg += '. Страница не прокручивается, ниже искать негде'
        sim = []
        if text:
            try: sim = self.rw(f'similar({json.dumps(text, ensure_ascii=False)})') or []
            except RuntimeError: pass
        sim = [x for x in sim if x['text'].lower() != str(text).lower() or not x['on']]
        if sim:
            msg += '. Похожие тексты на странице: ' + ', '.join(f'«{x["text"]}»' + ('' if x['on'] else ' (есть, но скрыт)') for x in sim) + '. Проверь написание в шаге'
        elif r.get('miss') in ('text', 'near'):
            msg += '. Похожих текстов нет: проверь, что предыдущий шаг открыл нужную страницу'
        return self.snap_fail(n, msg)

    def seek(self, n, call, what, max_swipes=45, budget=100.0):
        """Листает основную ленту страницы вниз по 3/4 экрана, после каждого взмаха ищет снова. Путь идет в ролик шагом «Прокрути до …»."""
        self.dwell(0.6); t1 = time.time(); url0 = self.href(); moved = 0; ends = 0; r = {}
        self.log(f'  {what} нет в загруженной части страницы: листаю вниз')
        for i in range(1, max_swipes + 1):
            if time.time() - t1 > budget: break
            sw = self.rw('swipe()') or {}
            if not sw.get('ok'): return dict(ok=False, swipes=i - 1, moved=round(moved), last=r)
            moved += sw.get('moved', 0); t_end = time.time()
            for _ in range(10 if sw.get('end') else 3):   # раздел догружается после прокрутки; в конце страницы ждем подольше
                time.sleep(0.3)
                r = self.rw(call) or {}
                if r.get('ok'):
                    self.settle(min_wait=0.3, max_wait=4); r = self.rw(call) or r
                    if r.get('ok'):
                        self.pending = dict(t=t1, url=url0, moved=moved, t_end=t_end)
                        self.log(f'  нашел после {i} взмахов ({moved:.0f} px)'); return r
                if r.get('miss') == 'ambig': raise self.snap_fail(n, self.ambig_msg(what, r))
            if sw.get('end') and sw.get('moved', 0) < 2:
                ends += 1
                if ends >= 2: return dict(ok=False, swipes=i, moved=round(moved), last=r)
            else: ends = 0
        return dict(ok=False, swipes=max_swipes, moved=round(moved), last=r)

    def visible(self, n, info, call, what, user_scroll=None, place=0.45, xlabel=None):
        """Цель вне экрана или под липкой панелью: плавно прокручиваем, это отдельный шаг ролика (вместе с поиском по странице, если он был)."""
        pend, self.pending = self.pending, None
        if not pend and info['inView'] and not info['covered'] and not user_scroll: return info
        if info['inView'] and info['covered'] and not user_scroll:
            self.log(f'  цель закрыта: {info["covered"]}, пробую прокрутить')
        if pend: t1, url0, moved, mx, t2 = pend['t'], pend['url'], pend['moved'], 0, pend['t_end']
        else:
            self.dwell(0.6)   # экран сначала виден, потом едет
            t1 = time.time(); url0 = self.href(); moved = mx = 0; t2 = t1
        force = bool(pend or user_scroll); place = 0.3 if force else place
        for _ in range(3):
            r = self.rw(f'scrollCur({place}, {"true" if force else "false"})')
            if not r.get('ok'): raise self.snap_fail(n, 'не смог прокрутить: ' + r.get('why', ''))
            moved += r['moved']; mx += r.get('mx', 0)
            if r['moved'] > 1: t2 = time.time()
            self.settle(min_wait=0.35, max_wait=6)
            info = self.rw('measure()')
            if not info.get('ok'): info = self.locate(n, call, what)
            if info['inView'] and not info['covered']: break
            force = False
        if not info['inView']: raise self.snap_fail(n, f'{what} не встает в экран даже после прокрутки')
        if info['covered']: raise self.snap_fail(n, f'{what} закрыт другим элементом: {info["covered"]}. Если это окно или баннер, закрой его шагом сценария')
        if moved > 1 or user_scroll:
            axis = 'x' if mx > moved / 2 else 'y'   # вбок листают до самой цели, вниз до раздела (ориентира)
            self.steps.append(dict(kind='scroll', text=(xlabel or what) if axis == 'x' else what, auto=not user_scroll, say=user_scroll, t=t1, t_end=t2,
                                   t_settle=self.last_settle, url_before=url0, url_after=self.href(), changed=moved > 1, moved=round(moved), axis=axis, box=None,
                                   target=[round(v * DPR) for v in info['box']], sought=bool(pend)))
            self.log(f'  прокрутка на {moved:.0f} px')
        return info

    def stable(self, info, call):
        """Перед касанием элемент не должен ехать (карусель, догрузка): меряем дважды."""
        for _ in range(12):
            time.sleep(0.15); j = self.rw('measure()')
            if not j.get('ok'): j = self.rw(call)
            if j.get('ok') and max(abs(a - b) for a, b in zip(j['box'], info['box'])) <= 1: return j
            info = j if j.get('ok') else info
        return info

    def dwell(self, sec=1.3):
        left = self.last_settle + sec - time.time()
        if left > 0: time.sleep(left)

    # --- признаки того, что касание сработало
    def changed(self, url0, sigA, sigB, t_from, timeout=3.0):
        """Отклик на касание: сменился адрес или заметная часть экрана. Не считаются: то, что менялось само до касания
        (часы, счетчики), и карусели с автопрокруткой, если касание было не в них."""
        d = lambda sg: {x[0]: x[1] for x in sg or []}
        zs = lambda sg: {x[0] for x in sg or [] if len(x) > 2 and x[2]}
        a, base = d(sigA), d(sigB)
        vol = {i for i in set(a) | set(base) if a.get(i) != base.get(i)} if sigA and sigB else set()
        while time.time() - t_from < timeout:
            time.sleep(0.15); u = self.href()
            if u and url0 and u != url0: return 'адрес', time.time()
            try: s = self.rw('sig()', tries=2)
            except RuntimeError: continue
            now = d(s); keys = {i for i in (set(base) | set(now)) - vol - zs(sigB) - zs(s) if not str(i).startswith('g')}
            diff = [i for i in keys if base.get(i) != now.get(i)]
            # сетка слоев: считается только новое окно поверх (или закрытое окно) минимум на 6 точках из 40
            gk = [i for i in base if str(i).startswith('g') and i not in vol]
            bl, nl = {base[i] for i in gk}, {now.get(i) for i in gk}
            over = [i for i in gk if now.get(i) != base[i] and (now.get(i) not in bl or base[i] not in nl)]
            if len(over) >= 6:
                self.log(f'    поверх страницы открылось или закрылось окно: слой сменился в {len(over)} точках из 40')
                return f'окно поверх ({len(over)} точек из 40)', time.time()
            if len(diff) >= 4 or len(diff) >= 0.1 * max(1, len(keys)):
                self.log('    изменилось: ' + '; '.join((now.get(i) or base.get(i) or '').split('|')[1][:24] or (now.get(i) or base.get(i) or '').split('|')[0] for i in diff[:6]))
                return f'экран ({len(diff)} из {len(keys)})', time.time()
        return None, None

    def spots(self, expect):
        return self.rw(f'spots({json.dumps(expect, ensure_ascii=False)})') or [] if expect else None

    def check_expect(self, n, what, expect, before):
        """expect засчитывается, только если текст появился там, где его не было до шага: нижнее меню и шапка с тем же словом не в счет."""
        if not expect: return
        same = lambda a, b: max(abs(x - y) for x, y in zip(a['box'], b['box'])) <= 6
        t0 = time.time(); now = []
        while True:
            now = self.spots(expect)
            new = [a for a in now if not any(same(a, b) for b in before)]
            if new:
                new.sort(key=lambda a: not a['on']); self.log(f'  проверка: «{expect}» появилось: «{new[0]["label"]}» {new[0]["box"]}'); return
            if time.time() - t0 > 3: break
            time.sleep(0.3)
        if now: raise self.snap_fail(n, f'после «{what}» текст «{expect}» есть, но он был на том же месте и до шага («{now[0]["label"]}» {now[0]["box"]}), '
                                        'это не проверка. Возьми для expect текст, которого до шага на экране не было')
        raise self.snap_fail(n, f'после «{what}» не появилось «{expect}»')

    def tap_target(self, n, info, call, what, kind='tap', say=None, auto=False, expect=None):
        self.dwell(); info = self.stable(info, call)
        if info['covered']: raise self.snap_fail(n, f'{what} закрыт другим элементом: {info["covered"]}')
        money = self.rw('risky()')
        if money: raise self.snap_fail(n, f'«{money}» похоже на оплату, вывод или ставку: такие кнопки рекордер не нажимает. '
                                          f'Сделай этот шаг последним как {{"point": "{what}"}}: ролик закончится рамкой на кнопке без нажатия')
        before = self.spots(expect)
        self.rw('freeze()'); sigB = self.rw('sig()'); url0 = self.href()
        x, y = info['tap']; t = self.touch(x, y)
        how, tc = self.changed(url0, self.sigA, sigB, t)
        retried = False
        if not how:   # цель закрыло новое окно = касание сработало; клик скриптом тут закрыл бы это окно обратно
            m = self.rw('measure()') or {}
            if m.get('ok') and m.get('covered') and not info.get('covered'): how, tc = f'поверх открылось окно ({m["covered"][:40]})', time.time()
        if not how:
            self.log(f'  касание по «{what}» ничего не поменяло, пробую клик скриптом')
            self.rw('click()'); retried = True; t = time.time(); how, tc = self.changed(url0, self.sigA, sigB, t)
            if not how: raise self.snap_fail(n, f'касание по «{what}» не сработало: ни адрес, ни экран не поменялись за 3 с (и после клика скриптом). '
                                                 'Проверь текст шага или добавь near/where/index')
        self.settle(min_wait=0.8)
        self.check_expect(n, what, expect, before)
        st = dict(kind=kind, text=what, auto=auto, say=say, t=t, x=x, y=y, box=info['box'], radius=info['radius'], tap_how=info['tapHow'], how=info.get('how'),
                  url_before=url0, url_after=self.href(), changed=True, change=how, t_change=tc, t_settle=self.last_settle, retried_js_click=retried,
                  label=info.get('label'), alts=info.get('n', 1))
        self.steps.append(st); self.log(f'  касание «{what}» -> {how}; {st["url_after"]}')
        return st

    # --- шаги сценария
    def do(self, n, s):
        say = s.get('say'); self.cur_n = n
        if 'wait' in s:
            time.sleep(float(s['wait'])); self.settle(min_wait=0.2); return
        self.sweep()
        if 'tap' in s or 'scroll_to' in s:
            key = 'tap' if 'tap' in s else 'scroll_to'
            spec = {k: s[k] for k in ('near', 'where', 'index') if k in s}; spec['text'] = s[key]
            call = f'find({json.dumps(spec, ensure_ascii=False)})'; what = f'«{s[key]}»' + (f' рядом с «{s["near"]}»' if s.get('near') else '')
            # листаем страницу в поисках, только если цель может быть ниже: у where цель в панели или в заданной зоне экрана
            info = self.locate(n, call, what, seek=not s.get('where'), suggest={'near': s.get('near'), 'text': s[key], 'where': s[key], 'index': s[key]})
            if info.get('near'): self.log(f'  ориентир «{info["near"]["label"]}» {info["near"]["box"]}, до цели {info["near"]["d"]} px')
            if key == 'scroll_to':
                self.visible(n, info, call, s['scroll_to'], user_scroll=say or True); return
            # прокрутка к цели подписывается по ориентиру: «Прокрути до [Live Казино]», а не до [Більше]
            info = self.visible(n, info, call, s.get('near') or s['tap'], xlabel=s['tap'])
            return self.tap_target(n, info, call, s['tap'], say=say, expect=s.get('expect'))
        if 'point' in s:   # рамка без нажатия: последний шаг (кнопка оплаты, вывода, ставки)
            spec = {k: s[k] for k in ('near', 'where', 'index') if k in s}; spec['text'] = s['point']
            call = f'find({json.dumps(spec, ensure_ascii=False)})'; what = f'«{s["point"]}»' + (f' рядом с «{s["near"]}»' if s.get('near') else '')
            info = self.locate(n, call, what, seek=not s.get('where'), suggest={'near': s.get('near'), 'text': s['point'], 'where': s['point'], 'index': s['point']})
            info = self.visible(n, info, call, s.get('near') or s['point'], xlabel=s['point'])
            self.dwell(); info = self.stable(info, call)
            if info['covered']: raise self.snap_fail(n, f'{what} закрыт другим элементом: {info["covered"]}')
            st = dict(kind='point', text=s['point'], auto=False, say=say, t=time.time(), x=None, y=None, box=info['box'], radius=info['radius'],
                      url_before=self.href(), url_after=self.href(), changed=False, change=None, t_change=None, t_settle=self.last_settle, how=info.get('how'))
            self.steps.append(st); self.log(f'  рамка на «{s["point"]}» без нажатия {[round(v) for v in info["box"]]}'); return st
        if 'tap_icon' in s:   # кнопка без текста: лупа, бургер, стрелка назад, крестик
            name = str(s['tap_icon']); zone = s.get('where', 'any')
            call = f'findIcon({json.dumps(name, ensure_ascii=False)}, {json.dumps(zone)})'
            label = AUTO.get(self.lang, AUTO['en'])['icons'].get(name, name)
            info = self.locate(n, call, f'иконку «{name}»', seek=zone == 'any')
            if info.get('n', 1) > 1: self.log(f'  иконок «{name}» {info["n"]}, беру верхнюю левую {[round(v) for v in info["box"]]}')
            info = self.visible(n, info, call, label)
            return self.tap_target(n, info, call, label, say=say, expect=s.get('expect'))
        if 'type' in s:
            into = s.get('into', 'search'); call = f'findField({json.dumps(into, ensure_ascii=False)})'
            info = self.rw(call)
            if not info.get('ok'):   # поле пряталось за иконкой поиска: сначала открываем
                op = self.rw('findIcon("search", "top")')
                if not op.get('ok'): op = self.rw(f'find({json.dumps(dict(text=into), ensure_ascii=False)})')
                if not op.get('ok'): raise self.snap_fail(n, f'не нашел ни поля «{into}», ни кнопки, которая его открывает')
                lab = AUTO.get(self.lang, AUTO['en'])['icons']['search']
                op = self.visible(n, op, 'findIcon("search", "top")', lab)
                self.tap_target(n, op, 'findIcon("search", "top")', lab, auto=True)['icon'] = 'search'
                info = self.locate(n, call, f'поле «{into}»')
            info = self.visible(n, info, call, f'поле {into}')
            self.dwell(); info = self.stable(info, call)
            before = self.spots(s.get('expect'))
            self.rw('freeze()'); sigB = self.rw('sig()'); url0 = self.href(); x, y = info['tap']; t = self.touch(x, y); time.sleep(0.35)
            act = self.rw('active()')
            if not act:
                self.rw('focus()'); time.sleep(0.2); act = self.rw('active()')
                if not act: raise self.snap_fail(n, f'поле «{into}» не получило фокус после касания')
            text = str(s['type']); t_type = time.time()
            for i, ch in enumerate(text):   # по одной букве, с живыми паузами
                self.b.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'text': ch, 'unmodifiedText': ch, 'key': ch}, page=True)
                self.b.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': ch}, page=True)
                time.sleep(0.11 + 0.07 * ((i * 7919) % 5) / 4)
            t_typed = time.time(); act2 = self.rw('active()') or {}
            val = act2.get('value') or ''
            if text.lower() not in val.lower():
                raise self.snap_fail(n, f'текст «{text}» не напечатался в поле (в поле: «{val}»)')
            how, tc = self.changed(url0, self.sigA, sigB, t_typed - 0.01, timeout=3.0)
            time.sleep(0.6); self.settle(min_wait=1.0)
            self.check_expect(n, f'ввода «{text}»', s.get('expect'), before)
            st = dict(kind='type', text=text, into=into, auto=False, say=say, t=t, x=x, y=y, box=info['box'], radius=info['radius'], tap_how=info['tapHow'], how='поле',
                      url_before=url0, url_after=self.href(), changed=bool(how) or bool(val), change=how or 'текст в поле', t_change=tc or t_typed, t_typed=t_typed,
                      t_type=t_type, t_settle=self.last_settle, value=val)
            self.steps.append(st); self.log(f'  ввел «{text}» -> {st["change"]}'); return st
        if s.get('back'):
            lab = AUTO.get(self.lang, AUTO['en'])['icons']['back']
            bk = self.rw('findIcon("back", "top")')
            if bk.get('ok'):
                bk = self.visible(n, bk, 'findIcon("back", "top")', lab)
                return self.tap_target(n, bk, 'findIcon("back", "top")', lab, kind='back', say=say)
            # кнопки «назад» на сайте нет: назад браузера. Пальца не видно, поэтому экран стоит, пока читается подпись
            cap = self.say_map.get(n) or AUTO.get(self.lang, AUTO['en'])['back']
            self.dwell(max(1.3, min(7.0, max(2.2, 1.0 + len(show.plain(cap)) / 16.0)) + 0.3))
            url0 = self.href(); self.rw('freeze()'); sigB = self.rw('sig()'); t = time.time(); self.js('history.back()')
            how, tc = self.changed(url0, self.sigA, sigB, t)
            if not how: raise self.snap_fail(n, 'кнопка «назад» браузера ничего не поменяла')
            self.settle(min_wait=0.8)
            st = dict(kind='back', text=lab, auto=False, say=say, t=t, x=None, y=None, box=None, radius=None, url_before=url0, url_after=self.href(),
                      changed=True, change=how, t_change=tc, t_settle=self.last_settle)
            self.steps.append(st); self.log(f'  назад -> {st["url_after"]}'); return st
        raise Fail(f'шаг {n}: не понял шаг {s}. Есть tap, tap_icon, type (+into), scroll_to, point, wait, back')

    def finish(self, tail=3.2):
        time.sleep(tail); self.t_stop = time.time()
        try: self.b.call('Page.stopScreencast', page=True)
        except Exception: pass
        time.sleep(0.3); self.b.close()

# ---------------------------------------------------------------- видео, план, лист проверки
def sequence(sess):
    """Ровные 60 кадров/с из кадров screencast: в момент k/60 на экране последний пришедший к этому моменту кадр. Без масштабирования."""
    fr = sorted(sess.b.frames)
    if len(fr) < 2: raise Fail('браузер не прислал кадров записи')
    if sess.b.bad:
        x = sess.b.bad[0]
        raise Fail(f'кадр записи {x["i"]} не того размера: {x["size"]} при масштабе {x["scale"]}, сдвиг {x["offsetTop"]} (нужно {VW * DPR}x{VH * DPR}). '
                   'Растягивать не буду: рамки бы съехали')
    lag = sorted(r - ts for ts, _, r in fr)[len(fr) // 2]
    shift = 0.0 if -0.05 <= lag <= 1.0 else lag - 0.02   # часы кадров не совпали с часами Python: сводим по моменту прихода
    t0 = fr[0][0] + shift; end = (sess.t_stop or fr[-1][0] + shift + 1)
    seq = os.path.join(sess.tmp, 'seq'); os.makedirs(seq, exist_ok=True)
    n = int((end - t0) * FPS); j = 0
    for k in range(n):
        t = t0 + k / FPS
        while j + 1 < len(fr) and fr[j + 1][0] + shift <= t + 1e-4: j += 1
        dst = os.path.join(seq, f'{k:06d}.jpg')
        try: os.symlink(fr[j][1], dst)
        except OSError: shutil.copy(fr[j][1], dst)
    gaps = [b[0] - a[0] for a, b in zip(fr, fr[1:])]
    return seq, dict(t0=t0, shift=round(shift, 4), lag_median=round(lag, 4), frames=len(fr), seconds=round(end - t0, 2), out_frames=n,
                     max_gap=round(max(gaps), 3), size=[VW * DPR, VH * DPR])

def encode(seq, mp4, fast=False):
    q = ['-preset', 'ultrafast', '-crf', '20'] if fast else ['-preset', 'medium', '-crf', '14']
    show.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(seq, '%06d.jpg'), '-c:v', 'libx264', *q,
              '-pix_fmt', 'yuv420p', '-r', str(FPS), '-movflags', '+faststart', mp4])
    pi = show.probe(mp4)
    if (pi['width'], pi['height']) != (VW * DPR, VH * DPR): raise Fail(f'видео вышло {pi["width"]}x{pi["height"]}, а должно {VW * DPR}x{VH * DPR}')
    return mp4

# Поля статус-бара и полоски «домой» show.py заливает одним цветом, который берет с записи в момент 0,5 с (верхние и нижние 4 px).
# Цвет на 0,5 с случаен (на главной внизу может быть плитка игры), поэтому рекордер выбирает цвет сам (pad_colors)
# и рисует его полосками 4 pt по краям кадров 0,3-0,8 с. Эти кадры в ролик не входят: первый шаг начинается после них.
CAL = (0.3, 0.8, 8)   # с, по, высота полоски в пикселях записи

def edge_rows(video, y, rate=10, n=131):
    """Край кадра (4 px записи) по времени: n цветов поперек экрана в каждой точке."""
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', video, '-vf', f'fps={rate},crop={VW * DPR}:4:0:{y},scale={n}:1:flags=area', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                       capture_output=True)
    b, k = r.stdout, 3 * n
    return [(i / rate, [tuple(b[i * k + 3 * j:i * k + 3 * j + 3]) for j in range(n)]) for i in range(len(b) // k)]

def solid(px, tol=12):
    """Цвет края, если он ровный (панель, фон): 85% точек рядом с медианой; пестрый край (картинки, текст) = None."""
    m = tuple(sorted(c[i] for c in px)[len(px) // 2] for i in range(3))
    ok = [c for c in px if max(abs(c[i] - m[i]) for i in range(3)) <= tol]
    return tuple(round(sum(c[i] for c in ok) / len(ok)) for i in range(3)) if len(ok) >= 0.85 * len(px) else None

def pad_colors(video, plan, lang, page_bg=None):
    """Цвет полей статус-бара и «домой». Ровный край (нижнее меню, шапка, фон) продолжается в поле; если край режет картинки
    или текст, поле берет фон страницы, как безопасная зона на iPhone. Из всех вариантов берется тот, что дольше на экране ролика
    (шаги с паузой на чтение весят больше)."""
    out = {}; bg = tuple(int(page_bg[i:i + 2], 16) for i in (0, 2, 4)) if page_bg else None
    for name, y in (('top', 0), ('bottom', VH * DPR - 4)):
        rows, acc, mixed = edge_rows(video, y), [], 0
        for st in plan['steps']:
            a, b = st['src']; inside = [solid(px) or bg for t, px in rows if a - 0.05 <= t <= b + 0.05]
            mixed += sum(1 for t, px in rows if a - 0.05 <= t <= b + 0.05 and not solid(px))
            if not inside: continue
            read = min(7.0, max(2.2, 1.0 + len(show.plain(st['text'].get(lang, ''))) / 16.0))
            ws = [0.1] * len(inside); ws[0 if st.get('tap') else -1] += read   # пауза на чтение: у касания до него, у остальных в конце
            acc += [(c, w) for c, w in zip(inside, ws) if c]
        groups = []
        for c, w in sorted(acc, key=lambda x: -x[1]):
            for g in groups:
                if max(abs(c[i] - g['c'][i]) for i in range(3)) <= 10: g['w'] += w; g['s'] = [g['s'][i] + c[i] * w for i in range(3)]; break
            else: groups.append(dict(c=c, w=w, s=[v * w for v in c]))
        if not groups: continue
        tot = sum(x['w'] for x in groups); g = max(groups, key=lambda g: g['w'])
        out[name] = '%02X%02X%02X' % tuple(round(v / g['w']) for v in g['s']); out[name + '_share'] = round(g['w'] / tot, 2); out[name + '_mixed'] = mixed
    return out

def paint_edges(seq, colors, tmp):
    """Полоски цвета полей на кадрах 0,3-0,8 с (рисуем в RGB: так цвет доходит до show.py точно)."""
    W, H = VW * DPR, VH * DPR; h = CAL[2]
    vf = f"format=rgb24,drawbox=x=0:y=0:w={W}:h={h}:color=0x{colors['top']}:t=fill,drawbox=x=0:y={H - h}:w={W}:h={h}:color=0x{colors['bottom']}:t=fill"
    cache = {}
    for k in range(int(CAL[0] * FPS), int(CAL[1] * FPS) + 1):
        dst = os.path.join(seq, f'{k:06d}.jpg')
        if not os.path.lexists(dst): break
        src = os.path.realpath(dst)
        if src not in cache:
            cache[src] = os.path.join(tmp, f'cal{len(cache)}.jpg')
            show.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-vf', vf, '-pix_fmt', 'yuvj420p', '-q:v', '1', cache[src]])
        os.remove(dst); os.symlink(cache[src], dst)

def texts_for(scn, lang):
    """Подписи по шагам сценария (без wait), плюс финальная, если есть лишняя строка."""
    say = (scn.get('say') or {}).get(lang) or []
    acts = [s for s in scn['steps'] if 'wait' not in s]
    out = []
    for i, s in enumerate(acts):
        own = s.get('say'); own = own.get(lang) if isinstance(own, dict) else own
        out.append(own or (say[i] if i < len(say) else None))
    return out, (say[len(acts)] if len(say) > len(acts) else (scn.get('final') or {}).get(lang))

def build_plan(sess, scn, lang, mp4, meta, out):
    L = AUTO.get(lang, AUTO['en']); rec = lambda w: round(w - meta['t0'], 3)
    mts, mvals = show.motion_series(mp4, rate=30); dur = show.probe(mp4)['duration']
    def first_jump(T, horizon=2.5):   # начало смены экрана после касания: первый кадр с заметной долей пикового изменения
        win = [(t, v) for t, v in zip(mts, mvals) if T + 0.03 <= t <= T + horizon]
        peak = max((v for _, v in win), default=0)
        if peak < 0.35: return None
        thr = max(0.35, 0.3 * peak); return next(t for t, v in win if v >= thr)
    def quiet_from(t, horizon=4.0):   # экран перестал меняться (догрузка закончилась)
        pts = [(x, v) for x, v in zip(mts, mvals) if t <= x <= t + horizon]
        for i, (x, v) in enumerate(pts):
            if all(vv < 0.35 for xx, vv in pts[i:] if xx <= x + 0.3): return x
        return None
    texts, final = texts_for(scn, lang); ui = 0; plan_steps = []; truth = []
    start = max(CAL[1] + 0.1, rec(sess.t_ready) - 0.1 if sess.t_ready else 0)   # до этого момента калибровка цвета полей и закрытие плашек
    cleans = [rec(c) for c in sess.cleans]
    users = iter(texts)
    for k, st in enumerate(sess.steps):
        user_text = None
        if not st.get('auto'):
            user_text = next(users, None)
        T = rec(st['t']); s = dict(kind=st['kind'])
        start = max([start] + [c for c in cleans if c < T - 0.3])   # плашку закрыли перед этим шагом: шаг начинается с чистого экрана
        tpl = ('scroll_x' if st.get('axis') == 'x' else 'scroll') if st['kind'] == 'scroll' else 'search' if st.get('auto') and st.get('icon') == 'search' else 'back' if st['kind'] == 'back' \
            else 'type' if st['kind'] == 'type' else 'tap'
        text = user_text or L[tpl].format(t=st['text'])
        if st['kind'] == 'point':   # рамка без нажатия до конца записи, финальной подписи «Готово» нет
            bx = [round(v * DPR) for v in st['box']]; end = dur - 0.1; nxt = end
            ps = dict(src=[round(start, 3), round(end, 3)], focus=bx + [max(round(st['radius'] * DPR), 16)], text={lang: text})
        elif st['kind'] == 'scroll':   # без касания: последний кадр шага стоит на паузе, поэтому он уже догруженный
            end = max(rec(st['t_end']) + 0.2, min(rec(st['t_settle']), rec(st['t_end']) + 2.5)); nxt = max(end, rec(st['t_settle']))
            ps = dict(src=[round(start, 3), round(end, 3)], text={lang: text})
            if end - start > 10: ps['speed'] = round(min(6.0, (end - start) / 4.5), 2)   # долгий поиск по странице: в ролике около 4,5 с
        elif st['kind'] == 'type':   # поле в рамке, текст набирается, появляются результаты; без пальца, чтобы подпись не сменилась раньше времени
            settle = rec(st['t_settle']); end = max(rec(st['t_typed']) + 0.6, settle) + 0.25; nxt = end
            bx = [round(v * DPR) for v in st['box']]
            ps = dict(src=[round(start, 3), round(end, 3)], focus=bx + [max(round(st['radius'] * DPR), 16)], text={lang: text})
        elif st.get('box'):
            C = first_jump(T) or (rec(st['t_change']) if st.get('t_change') else T + 0.3)
            end = C + 0.15; settle = rec(st['t_settle']); q = quiet_from(C + 0.1) or settle
            nxt = max(settle, min(q, settle + 1.5))
            bx = [round(v * DPR) for v in st['box']]
            ps = dict(src=[round(start, 3), round(end, 3)], tap=[round(st['x'] * DPR), round(st['y'] * DPR), T],
                      focus=bx + [max(round(st['radius'] * DPR), 16)], text={lang: text})
            s['switch'] = round(C, 3)
        else:   # назад кнопкой браузера: пальца нет, шаг кончается перед сменой экрана (пауза не стоит на пустой странице)
            C = first_jump(T) or T + 0.3; end = max(start + 0.3, C - 0.03); nxt = max(rec(st['t_settle']), C + 0.15)
            ps = dict(src=[round(start, 3), round(end, 3)], text={lang: text})
        if ps['src'][1] - ps['src'][0] < 0.3: ps['src'][1] = round(ps['src'][0] + 0.3, 3)
        plan_steps.append(ps)
        s.update(text=st['text'], say=text, t=T, x=round(st['x'] * DPR) if st.get('x') is not None else None, y=round(st['y'] * DPR) if st.get('y') is not None else None,
                 box=[round(v * DPR) for v in st['box']] if st.get('box') else None, radius=round(st['radius'] * DPR) if st.get('radius') is not None else None,
                 url_before=st['url_before'], url_after=st['url_after'], changed=st['changed'], change=st.get('change'), auto=st.get('auto', False),
                 src=ps['src'], settle=rec(st['t_settle']) if st.get('t_settle') else None)
        for key in ('tap_how', 'how', 'retried_js_click', 'value', 'moved', 'axis', 'target', 'label', 'alts', 'icon', 'sought'):
            if st.get(key) is not None: s[key] = st[key]
        truth.append(s); start = nxt + 0.05
    if not sess.steps or sess.steps[-1]['kind'] != 'point':
        plan_steps.append(dict(src=[round(start, 3), round(dur - 0.1, 3)], text={lang: final or L['final']}))
    title = (scn.get('title') or {}).get(lang) or {'uk': 'Як це зробити', 'ru': 'Как это сделать'}.get(lang, 'How to do it')
    slug = scn.get('slug') or re.sub(r'[^a-z0-9]+', '-', (urllib.parse.urlparse(sess.url).hostname or 'site') + '-' + '-'.join(
        str(s.get('tap') or s.get('type') or s.get('scroll_to') or '') for s in scn['steps'][:3]).lower()).strip('-')[:60] or 'guide'
    plan = dict(slug=slug, title={lang: title}, languages=[lang], topic=scn.get('topic', ''), screen={'status_bar': True}, steps=plan_steps,
                questions=scn.get('questions', {}), operator_reply=scn.get('operator_reply', {}), recorded=time.strftime('%Y-%m-%d'),
                recorder=dict(url=sess.url, viewport=[VW, VH], scale=DPR))
    return plan, truth

def proof(mp4, truth, path, tmp):
    """Лист проверки: кадр записи за 0,25 с до касания, поверх рамка элемента (по его границам) и точка касания."""
    items = [s for s in truth if s.get('box')]
    if not items: return None
    tiles = []
    for i, s in enumerate(items):
        f = os.path.join(tmp, f'proof{i}.jpg'); t = max(0.0, s['t'] - 0.25)
        show.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{t:.3f}', '-i', mp4, '-frames:v', '1', '-q:v', '2', f])
        x, y, w, h = [v / DPR for v in s['box']]; r = (s.get('radius') or 0) / DPR
        dot = '' if s.get('x') is None else \
            f'<i class="d" style="left:{s["x"] / DPR}px;top:{s["y"] / DPR}px"></i><i class="h" style="top:{s["y"] / DPR}px"></i><i class="v" style="left:{s["x"] / DPR}px"></i>'
        lab = f'{i + 1}. {s["kind"]} «{s["text"]}» t={s["t"]:.2f} box={s["box"]} r={s.get("radius")}'
        tiles.append(f'<div class="t"><div class="f"><img src="file://{urllib.parse.quote(f)}"><b style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;border-radius:{r}px"></b>{dot}</div>'
                     f'<p>{lab.replace("&", "&amp;").replace("<", "&lt;")}</p></div>')
    cols = min(4, len(tiles)); rows = (len(tiles) + cols - 1) // cols; Wp, Hp = cols * (VW + 16) + 16, rows * (VH + 60) + 16
    html = ('<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#15161c;width:%dpx;padding:8px;box-sizing:border-box;display:flex;flex-wrap:wrap;font:12px -apple-system,Arial}'
            '.t{width:%dpx;margin:8px}.f{position:relative;width:%dpx;height:%dpx;overflow:hidden}.f img{width:100%%;height:100%%;display:block}'
            'b{position:absolute;box-sizing:border-box;outline:1px solid #39ff14;outline-offset:0;background:rgba(57,255,20,.10)}'
            'i.d{position:absolute;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%%;background:#ff2d55;box-shadow:0 0 0 2px #fff}'
            'i.h,i.v{position:absolute;background:rgba(255,45,85,.55)}i.h{left:0;right:0;height:.5px}i.v{top:0;bottom:0;width:.5px}'
            'p{color:#ddd;margin:6px 0 0;word-break:break-all}</style>' % (Wp, VW, VW, VH)) + ''.join(tiles)
    page = os.path.join(tmp, 'proof.html'); open(page, 'w', encoding='utf-8').write(html)
    b = show.Browser(show.find_browser())
    try:
        b.call('Emulation.setDeviceMetricsOverride', {'width': Wp, 'height': Hp, 'deviceScaleFactor': DPR, 'mobile': False}, page=True)
        b.call('Page.enable', page=True); b.call('Page.navigate', {'url': 'file://' + urllib.parse.quote(page)}, page=True); time.sleep(0.8)
        b.js('Promise.all([...document.images].map(i => i.decode().catch(() => 0))).then(() => 1)')
        open(path, 'wb').write(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, page=True)['data']))
    finally:
        b.close()
    return path

def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'login':
        lp = argparse.ArgumentParser(prog='record_web.py login', description='окно Chrome для входа в тестовый аккаунт (вход делает человек)')
        lp.add_argument('cmd'); lp.add_argument('url'); lp.add_argument('--profile', required=True); lp.add_argument('--timeout', type=float, default=1800)
        la = lp.parse_args(); return login(la.url, la.profile, la.timeout)
    ap = argparse.ArgumentParser(description='запись сценария на сайте в виде iPhone для show.py')
    ap.add_argument('url'); ap.add_argument('steps'); ap.add_argument('--out', required=True); ap.add_argument('--lang', default='uk')
    ap.add_argument('--keep-banners', action='store_true', help='не закрывать плашки приложения и рекламы перед записью')
    ap.add_argument('--profile', help='папка профиля Chrome с входом в тестовый аккаунт (сначала: record_web.py login URL --profile DIR)')
    a = ap.parse_args()
    scn = json.load(open(a.steps, encoding='utf-8'))
    if not scn.get('steps'): die('в steps.json нет шагов')
    pts = [i for i, s in enumerate(scn['steps']) if 'point' in s]
    if pts and pts != [len(scn['steps']) - 1]: die('шаг point (рамка без нажатия) может быть только последним')
    profile = None
    if a.profile:
        profile = os.path.abspath(os.path.expanduser(a.profile))
        if not os.path.isdir(profile): die(f'нет профиля {profile}. Сначала вход: python3 {os.path.abspath(__file__)} login {a.url} --profile {a.profile}')
        if profile_busy(profile): die(f'профиль {profile} открыт в окне Chrome (вход или другая запись): закрой окно и запусти снова')
    items = scn.get('blur') or []
    if isinstance(items, str): items = [items]
    blur = dict(auto=bool(scn.get('blur_auto', bool(profile))), items=[str(x) for x in items])
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.startswith('fail-step'): os.remove(os.path.join(out, f))
    sess = Session(a.url, out, a.lang, a.keep_banners, profile=profile, blur=blur)
    texts, _ = texts_for(scn, a.lang); acts = [n for n, s in enumerate(scn['steps'], start=1) if 'wait' not in s]
    sess.say_map = {n: t for n, t in zip(acts, texts) if t}
    try:
        sess.start()
        for n, s in enumerate(scn['steps'], start=1):
            sess.log(f'шаг {n}: {json.dumps(s, ensure_ascii=False)}'); sess.do(n, s)
        if blur['auto'] or blur['items']:
            try: meta_blur = sess.js('window.__rwPriv ? [window.__rwPriv.n, window.__rwPriv.skipped] : null')
            except RuntimeError: meta_blur = None
        else: meta_blur = None
        sess.finish()
    except Fail as e:
        try: sess.b.close()
        except Exception: pass
        shutil.rmtree(sess.tmp, ignore_errors=True); die(str(e), 2)
    except BaseException:
        try: sess.b.close()
        except Exception: pass
        raise
    try:
        mp4 = os.path.join(out, f'recording.{a.lang}.mp4')
        seq, meta = sequence(sess)
        draft = encode(seq, os.path.join(sess.tmp, 'draft.mp4'), fast=True)   # черновик для границ шагов и цвета полей
        plan, truth = build_plan(sess, scn, a.lang, draft, meta, out)
        cols = pad_colors(draft, plan, a.lang, sess.page_bg)
        if 'top' in cols and 'bottom' in cols: paint_edges(seq, cols, sess.tmp)
        encode(seq, mp4)
        got = [show.edge_color(mp4, VW * DPR, VH * DPR, y)[0] for y in (0, VH * DPR - 4)]   # что увидит show.py
        if cols.get('top'):
            off = max(abs(int(g[i:i + 2], 16) - int(c[i:i + 2], 16)) for g, c in zip(got, (cols['top'], cols['bottom'])) for i in (0, 2, 4))
            if off > 6: sess.log(f'  внимание: цвет полей в записи {got}, а выбран {cols["top"]}, {cols["bottom"]}')
        plan['screen'].update(top_color=got[0], bottom_color=got[1])
        meta['pad'] = dict(cols, seen_by_show=got, page_bg=sess.page_bg)
        meta['account'] = bool(profile); meta['blur'] = dict(blur, marked=meta_blur[0] if meta_blur else None, skipped=meta_blur[1] if meta_blur else None)
        json.dump(plan, open(os.path.join(out, 'plan.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        json.dump(dict(url=a.url, lang=a.lang, viewport=[VW, VH], scale=DPR, recording=os.path.basename(mp4), video=meta, steps=truth),
                  open(os.path.join(out, 'truth.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        pr = proof(mp4, truth, os.path.join(out, 'proof.png'), sess.tmp)
        show.run([sys.executable, os.path.join(HERE, 'show.py'), 'prep', mp4, '--out', out, '--max-frames', '400'])
    except Fail as e:
        die(str(e), 2)
    finally:
        shutil.rmtree(sess.tmp, ignore_errors=True)
    print(f'готово: {mp4}\n  {meta["seconds"]} с, кадров от браузера {meta["frames"]} (самая длинная пауза {meta["max_gap"]} с), видео {VW * DPR}x{VH * DPR} {FPS} к/с')
    for s, p in zip(truth, plan['steps']):
        print(f'  {s["kind"]:6} «{s["text"]}» t={s["t"]:.2f} касание={(s["x"], s["y"]) if s.get("x") is not None else "-"} рамка={s.get("box")} r={s.get("radius")} src={p["src"]}')
    if meta.get('blur', {}).get('auto') or meta.get('blur', {}).get('items'):
        print(f'  размытие: элементов {meta["blur"]["marked"]}' + (f', пропущено (текст прямо в body) {meta["blur"]["skipped"]}' if meta['blur'].get('skipped') else '')
              + '. Проверь кадры: формы платежных систем во фреймах сами не размываются')
    print(f'  план: {os.path.join(out, "plan.json")}\n  проверка рамок: {pr}\n  дальше: python3 {os.path.join(HERE, "show.py")} render {out}')

if __name__ == '__main__':
    main()
