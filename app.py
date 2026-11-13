#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, time, random, json, requests, subprocess,ctypes
from urllib.parse import quote
from seleniumbase import SB

# 环境变量配置(可以直接私库在双引号里填写)
EMAIL         = os.environ.get("EMAIL") or ""           # 邮箱必填，登录和通知使用
PASSWORD      = os.environ.get("PASSWORD") or ""        # 主用密码登录方式, 失败时才使用,必须填写
MP_URL        = (os.environ.get("MP_URL") or "").strip()  # MoviePilot 域名/地址, 未写协议时默认 https://
MP_APIKEY     = os.environ.get("MP_APIKEY") or ""       # MoviePilot UrlNotify 插件的 apikey
MP_CHANNEL    = os.environ.get("MP_CHANNEL") or ""      # 可选, 指定通知渠道(Wechat/Feishu/Telegram 等), 不填使用插件默认
MP_MTYPE      = os.environ.get("MP_MTYPE") or ""        # 可选, 指定消息类型, 不填使用插件默认

if MP_URL and not MP_URL.startswith(("http://", "https://")):
    MP_URL = "https://" + MP_URL
MP_URL = MP_URL.rstrip("/")

BASE_URL = "https://bot-hosting.net"

if not (EMAIL and PASSWORD):
    print("ℹ️ 未配置 EMAIL 和 PASSWORD,脚本终止。")
    sys.exit(1)

# 发送通知(经 MoviePilot UrlNotify 插件转发到企业微信)
def send_moviepilot_message(message: str):
    if not MP_URL or not MP_APIKEY:
        print("⚠️ MoviePilot 通知未配置(MP_URL/MP_APIKEY)，跳过通知")
        return
    url = f"{MP_URL}/api/v1/plugin/UrlNotify/send"
    params = {"apikey": MP_APIKEY}
    if MP_CHANNEL:
        params["channel"] = MP_CHANNEL
    if MP_MTYPE:
        params["mtype"] = MP_MTYPE
    try:
        resp = requests.post(
            url,
            params=params,
            json={"title": "Bot-hosting 续期通知", "text": message},
            timeout=15,
        )
        resp.raise_for_status()
        print(f"✅ MoviePilot 通知已发送: {resp.text[:200]}")
    except Exception as e:
        print(f"❌ MoviePilot 通知发送失败: {e}")

# 通知格式
def format_notification(status: str, extra: str = "", error: str = "", expiry_date: str = "") -> str:
    local_time = time.gmtime(time.time() + 8 * 3600)
    now = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        if len(name) > 4:
            masked_email = f"{name[:2]}****{name[-2:]}@{domain}"
        else:
            masked_email = f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + '****' 
    
    lines = [
        "🇫🇮 Bot-hosting 续期通知",
        "",
        f"{status}",
        f"👤 登录账户: {masked_email}",
    ]
    if expiry_date:
        lines.append(f"📅 到期时间: {expiry_date}")
    if extra:
        lines.append(extra)
    if error:
        lines.append(f"⚠️ 错误信息: {error}")
    lines.append(f"⏱️ 登录时间: {now}")
    return "\n".join(lines)

# ---------- 基础工具 ----------
def js(sb, script, default=None, errors=None):
    try:
        result = sb.execute_script(script)
        return default if result is None else result
    except Exception as e:
        if errors is not None:
            errors.append(f"execute_script: {type(e).__name__}: {e}")
        try:
            result = sb.cdp.evaluate("(function(){ " + script + " })()")
            return default if result is None else result
        except Exception as e2:
            if errors is not None:
                errors.append(f"cdp.evaluate: {type(e2).__name__}: {e2}")
            return default

# Turnstile 定位失败时的现场诊断快照
def diag_turnstile_dom(sb, errors=None):
    snap = js(sb, """
        var out = [];
        var ifr = document.querySelectorAll('iframe');
        out.push('top-doc iframes: ' + ifr.length);
        for (var i = 0; i < ifr.length; i++) {
            var r = ifr[i].getBoundingClientRect();
            out.push('iframe w=' + Math.round(r.width) + ' h=' + Math.round(r.height) + ' src=' + (ifr[i].src || '').slice(0, 90));
        }
        var ts = document.querySelectorAll('[class*="turnstile"], [id*="turnstile"], input[name="cf-turnstile-response"]');
        out.push('turnstile-ish elements: ' + ts.length);
        for (var j = 0; j < ts.length; j++) {
            var rr = ts[j].getBoundingClientRect();
            var cls = (typeof ts[j].className === 'string') ? ts[j].className : (ts[j].getAttribute('class') || '');
            out.push(' - ' + ts[j].tagName + ' class=' + cls + ' w=' + Math.round(rr.width) + ' h=' + Math.round(rr.height));
        }
        out.push('window.turnstile=' + (typeof window.turnstile) + ' readyState=' + document.readyState);
        return out.join('\\n');
    """, "")
    for line in str(snap).splitlines():
        print("   [diag] " + line)
    if errors:
        for err in errors:
            print("   [diag][exec-error] " + str(err)[:200])

#  页面注入脚本
# 可见弹窗定位辅助（登录页没有弹窗时返回 null）
DIALOG_HELPERS_JS = """
function __shown(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    if (r.width < 8 && r.height < 8) return false;
    var st = window.getComputedStyle(el);
    if (!st) return false;
    return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
}
function __findDialog() {
    var list = document.querySelectorAll('[role="dialog"], dialog[open], .modal.show, .modal.in');
    var first = null;
    for (var i = 0; i < list.length; i++) {
        if (!__shown(list[i])) continue;
        if (/renew/i.test(list[i].innerText || '')) return list[i];
        if (!first) first = list[i];
    }
    if (first) return first;
    var all = document.querySelectorAll('div');
    var best = null;
    for (var j = 0; j < all.length; j++) {
        var st = window.getComputedStyle(all[j]);
        if (!st) continue;
        if (st.position !== 'fixed' || parseInt(st.zIndex || '0', 10) <= 100) continue;
        var r = all[j].getBoundingClientRect();
        if (r.width < 250 || r.height < 150 || !__shown(all[j])) continue;
        if (/renew/i.test(all[j].innerText || '')) return all[j];
        if (!best) best = all[j];
    }
    return best;
}
"""

# Turnstile token：优先读取当前可见弹窗内的隐藏域，避免拿到其它 widget 的 token
TURNSTILE_TOKEN_JS = DIALOG_HELPERS_JS + """
var dlg = __findDialog();
var el = dlg ? dlg.querySelector('input[name="cf-turnstile-response"]') : null;
if (!el) el = document.querySelector('input[name="cf-turnstile-response"]');
if (el && el.value) return el.value;
try { if (window.turnstile && window.turnstile.getResponse) {
        var t = window.turnstile.getResponse(); if (t) return t; } } catch (e) {}
return '';
"""

TURNSTILE_EXISTS_JS = DIALOG_HELPERS_JS + """
function __hasTs(root) {
    if (!root) return false;
    return root.querySelector(
        'input[name="cf-turnstile-response"], iframe[src*="challenges.cloudflare.com"], .cf-turnstile'
    ) !== null;
}
var dlg = __findDialog();
if (dlg && __hasTs(dlg)) return true;
return __hasTs(document);
"""
TS_COORDS_JS = DIALOG_HELPERS_JS + """
function findWidget(root) {
    if (!root) return null;
    var els = root.querySelectorAll(
        'iframe[src*="challenges.cloudflare.com"], .cf-turnstile, [id*="cf-chl"]');
    for (var i = 0; i < els.length; i++) {
        var r = els[i].getBoundingClientRect();
        if (r.width > 50 && r.height > 20) return els[i];
    }
    var all = root.querySelectorAll('*');
    for (var j = 0; j < all.length; j++) {
        if (all[j].shadowRoot) {
            var f = findWidget(all[j].shadowRoot);
            if (f) return f;
        }
    }
    return null;
}
function boxFromTokenInput(root) {
    if (!root) return null;
    var el = root.querySelector('input[name="cf-turnstile-response"]');
    var cur = el ? el.parentElement : null;
    for (var k = 0; k < 6 && cur; k++) {
        var r = cur.getBoundingClientRect();
        if (r.width > 100 && r.width < 600 && r.height > 30 && r.height < 140) return cur;
        cur = cur.parentElement;
    }
    return null;
}
var dlg = __findDialog();
var hit = findWidget(dlg) || boxFromTokenInput(dlg);
if (!hit) hit = findWidget(document) || boxFromTokenInput(document);
if (!hit) return null;
var hr = hit.getBoundingClientRect();
return {cx: Math.round(hr.x + 30), cy: Math.round(hr.y + hr.height / 2)};
"""

# 弹窗内按钮清单（文本/class/禁用状态/坐标），用于准确点击"Renew for 4 days"
DIALOG_BUTTONS_JS = DIALOG_HELPERS_JS + """
var dlg = __findDialog();
var root = dlg || document;
var out = {found: !!dlg, buttons: [], text: '', html: ''};
out.text = (root.innerText || '').replace(/\\s+/g, ' ').slice(0, 500);
out.html = dlg ? String(dlg.outerHTML || '').slice(0, 4000) : '';
var els = root.querySelectorAll('button, [role="button"], a.btn');
for (var i = 0; i < els.length; i++) {
    var el = els[i], r = el.getBoundingClientRect();
    var st = window.getComputedStyle(el);
    var cls = String(el.className || '');
    out.buttons.push({
        text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 80),
        cls: cls.slice(0, 120),
        disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true' ||
                     /\\bdisabled\\b/.test(cls) || st.pointerEvents === 'none' ||
                     parseFloat(st.opacity || '1') < 0.5),
        visible: __shown(el) && r.width > 20 && r.height > 10,
        x: Math.round(r.x), y: Math.round(r.y),
        w: Math.round(r.width), h: Math.round(r.height)
    });
}
return JSON.stringify(out);
"""

# 滚动到确认按钮并返回最新坐标
SCROLL_CONFIRM_BTN_JS = DIALOG_HELPERS_JS + """
var dlg = __findDialog();
var root = dlg || document;
var els = root.querySelectorAll('button, [role="button"], a.btn');
var target = null;
for (var i = 0; i < els.length; i++) {
    var t = (els[i].innerText || '').replace(/\\s+/g, ' ').trim();
    if (!/renew/i.test(t)) continue;
    if (/free\\s*plan/i.test(t)) continue;
    if (/\\d+\\s*days?/i.test(t)) { target = els[i]; break; }
    if (!dlg) continue;
    if (!target && __shown(els[i])) target = els[i];
}
if (!target) return null;
try { target.scrollIntoView({block: 'center', inline: 'center'}); } catch (e) {}
var r = target.getBoundingClientRect();
return {
    x: Math.round(r.x), y: Math.round(r.y),
    w: Math.round(r.width), h: Math.round(r.height),
    text: (target.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 80)
};
"""

# 在页面内记录 fetch/XHR 的请求与响应，用于确认续期请求是否真的发出
NET_CAPTURE_JS = """
if (window.__renewNetInstalled) return 'installed';
window.__renewNet = [];
window.__renewNetInstalled = true;
function __interesting(url) {
    var s = String(url || '');
    if (!s || /^data:|^blob:/i.test(s)) return false;
    if (/\\.(png|jpe?g|gif|svg|webp|ico|css|woff2?|ttf)(\\?|$)/i.test(s)) return false;
    if (/(google-analytics|googletagmanager|analytics\\.google|doubleclick|facebook\\.net|clarity\\.ms|hotjar|sentry\\.io)/i.test(s)) return false;
    if (/(challenges\\.cloudflare\\.com|cdn-cgi\\/challenge-platform|cloudflareinsights)/i.test(s)) return false;
    return true;
}
var __origFetch = window.fetch;
if (__origFetch) {
    window.fetch = function () {
        var input = arguments[0], init = arguments[1] || {};
        var url = (typeof input === 'string') ? input : (input && input.url) || '';
        var method = String(init.method || (input && input.method) || 'GET').toUpperCase();
        var p = __origFetch.apply(this, arguments);
        if (method !== 'GET' && __interesting(url)) {
            var entry = {kind: 'fetch', method: method, url: String(url), status: null,
                         body: null, reqBody: null, reqHeaders: null, respHeaders: null, t: Date.now()};
            try {
                if (init.body != null) entry.reqBody = String(init.body).slice(0, 1000);
                if (init.headers) entry.reqHeaders = JSON.stringify(init.headers).slice(0, 1000);
            } catch (e) {}
            window.__renewNet.push(entry);
            try {
                p.then(function (resp) {
                    entry.status = resp.status;
                    try {
                        var hs = [];
                        resp.headers.forEach(function (v, k) { hs.push(k + ': ' + v); });
                        entry.respHeaders = hs.join('; ').slice(0, 1000);
                    } catch (e) {}
                    try { resp.clone().text().then(function (t) {
                        entry.body = String(t || '').slice(0, 3000);
                    }).catch(function () {}); } catch (e) {}
                    return resp;
                }).catch(function (err) { entry.error = String(err); });
            } catch (e) {}
        }
        return p;
    };
}
var __origOpen = XMLHttpRequest.prototype.open;
var __origSend = XMLHttpRequest.prototype.send;
var __origSetHeader = XMLHttpRequest.prototype.setRequestHeader;
XMLHttpRequest.prototype.setRequestHeader = function (key, value) {
    if (this.__netEntry) {
        this.__netEntry.reqHeaders = (this.__netEntry.reqHeaders ? this.__netEntry.reqHeaders + '; ' : '')
                                     + key + ': ' + value;
    }
    return __origSetHeader.apply(this, arguments);
};
XMLHttpRequest.prototype.open = function (method, url) {
    this.__netEntry = {kind: 'xhr', method: String(method || 'GET').toUpperCase(),
                       url: String(url || ''), status: null, body: null, reqBody: null,
                       reqHeaders: null, respHeaders: null, t: Date.now()};
    return __origOpen.apply(this, arguments);
};
XMLHttpRequest.prototype.send = function (body) {
    var self = this, entry = this.__netEntry;
    if (entry) {
        try { if (body != null) entry.reqBody = String(body).slice(0, 1000); } catch (e) {}
    }
    if (entry && entry.method !== 'GET' && __interesting(entry.url)) {
        window.__renewNet.push(entry);
        this.addEventListener('load', function () {
            entry.status = self.status;
            try { entry.body = String(self.responseText || '').slice(0, 3000); } catch (e) {}
        });
        this.addEventListener('error', function () { entry.error = 'xhr error'; });
    }
    return __origSend.apply(this, arguments);
};
return 'installed';
"""

# 可见的 toast/alert 提示，便于发现"验证失败/已达到冷却"等服务端反馈
FEEDBACK_JS = """
var out = [];
var els = document.querySelectorAll('[role="alert"], .alert, .toast, [class*="toast"], [class*="notification"]');
for (var i = 0; i < els.length; i++) {
    var r = els[i].getBoundingClientRect();
    var st = window.getComputedStyle(els[i]);
    if (r.width <= 0 || r.height <= 0 || st.display === 'none' || st.visibility === 'hidden') continue;
    var t = (els[i].innerText || '').replace(/\\s+/g, ' ').trim();
    if (t) out.push(t.slice(0, 200));
}
return out.join(' | ').slice(0, 500);
"""

# 只从 Free plan 卡片中提取文本，避免读到其它卡片的日期
FREE_PLAN_TEXT_JS = """
var all = document.querySelectorAll('div, section, article, li');
var best = null;
for (var i = 0; i < all.length; i++) {
    var t = (all[i].innerText || '');
    if (!/free\\s*plan/i.test(t)) continue;
    if (!/(expir|renew)/i.test(t)) continue;
    if (!/\\d{1,2}\\s+[A-Za-z]{3,9}\\s+\\d{4}|\\d{1,2}\\/\\d{1,2}\\/\\d{4}|\\d{4}-\\d{2}-\\d{2}/.test(t)) continue;
    if (t.length > 1500) continue;
    if (!best || t.length < ((best.innerText || '').length)) best = all[i];
}
return best ? best.innerText : '';
"""

# 浏览器环境指纹，用于判断服务端是否按自动化特征拒绝续期
FINGERPRINT_JS = """
var out = {};
try {
    out.ua = navigator.userAgent;
    out.webdriver = navigator.webdriver;
    out.languages = (navigator.languages || []).join(',');
    out.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    out.screen = screen.width + 'x' + screen.height;
    out.outer = window.outerWidth + 'x' + window.outerHeight;
    out.inner = window.innerWidth + 'x' + window.innerHeight;
    out.cores = navigator.hardwareConcurrency;
    out.plugins = navigator.plugins.length;
    var gl = document.createElement('canvas').getContext('webgl');
    var dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
    out.webglVendor = dbg ? String(gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL)) : '';
    out.webglRenderer = dbg ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : '';
    var names = [];
    document.cookie.split(';').forEach(function (c) {
        var n = c.split('=')[0].trim();
        if (n) names.push(n);
    });
    out.cookies = names.join(',');
    out.cfClearance = names.indexOf('cf_clearance') >= 0;
} catch (e) { out.error = String(e); }
return JSON.stringify(out);
"""

# Turnstile 脚本异步渲染，轮询等待组件出现
def wait_turnstile_present(sb, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if js(sb, TURNSTILE_EXISTS_JS, False):
            return True
        time.sleep(1)
    return False

def _activate_window():
    if os.name == "nt":
        return

    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _windows_mouse_click(x: int, y: int):
    try:
        user32 = ctypes.windll.user32
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.08)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
    except Exception:
        pass

def _mouse_position():
    try:
        r = subprocess.run(["xdotool", "getmouselocation", "--shell"],
                           capture_output=True, text=True, timeout=3)
        values = {}
        for line in r.stdout.splitlines():
            if "=" in line:
                key, val = line.split("=", 1)
                values[key] = val
        return int(values.get("X", 0)), int(values.get("Y", 0))
    except Exception:
        return None

def _human_mouse_move(x: int, y: int):
    """分多段移动鼠标，避免坐标瞬移这种明显的非人类轨迹"""
    start = _mouse_position()
    if not start:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)],
                       timeout=3, stderr=subprocess.DEVNULL)
        return
    sx, sy = start
    steps = random.randint(4, 7)
    for i in range(1, steps + 1):
        t = i / steps
        mx = int(sx + (x - sx) * t + random.uniform(-8, 8))
        my = int(sy + (y - sy) * t + random.uniform(-8, 8))
        subprocess.run(["xdotool", "mousemove", str(mx), str(my)],
                       timeout=2, stderr=subprocess.DEVNULL)
        time.sleep(random.uniform(0.06, 0.18))

def _xdotool_click(x: int, y: int):
    if os.name == "nt":
        _windows_mouse_click(x, y)
        return

    _activate_window()
    try:
        _human_mouse_move(x, y)
        time.sleep(random.uniform(0.2, 0.6))
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

def _screen_point(sb, cx, cy):
    """把页面视口坐标换算成屏幕坐标（兼容 xvfb 下的浏览器窗口标题栏偏移）"""
    wi = js(sb, "return '' + (window.screenX || 0) + '|' + (window.screenY || 0) + '|' +"
                " window.outerHeight + '|' + window.innerHeight;", "")
    parts = str(wi).split("|")
    sx, sy = int(parts[0] or 0), int(parts[1] or 0)
    bar = int(parts[2] or 800) - int(parts[3] or 768)
    return int(cx) + sx, int(cy) + sy + bar

def _move_mouse_screen(x, y):
    if os.name == "nt":
        try:
            ctypes.windll.user32.SetCursorPos(int(x), int(y))
        except Exception:
            pass
        return
    _human_mouse_move(int(x), int(y))

def _click_viewport_point(sb, cx, cy, label="元素") -> bool:
    try:
        ax, ay = _screen_point(sb, cx, cy)
        print(f"🖱️ 底层点击 {label} ({ax}, {ay})")
        _xdotool_click(ax, ay)
        return True
    except Exception as e:
        print(f"⚠️ 底层点击 {label} 失败: {e}")
        return False

def turnstile_token(sb) -> str:
    token = js(sb, TURNSTILE_TOKEN_JS, "")
    return token if isinstance(token, str) else ""

def _click_turnstile(sb, locate_timeout=10) -> bool:
    coords = None
    errors = []
    deadline = time.time() + locate_timeout
    while time.time() < deadline:
        coords = js(sb, TS_COORDS_JS, None, errors)
        if coords:
            break
        time.sleep(1)
    if not coords:
        print("⚠️ 无法定位 Turnstile 坐标, 打印现场诊断:")
        diag_turnstile_dom(sb, errors)
        return False

    if _click_viewport_point(sb, int(coords["cx"]), int(coords["cy"]), "Turnstile"):
        time.sleep(3)
        return True
    return False

def click_turnstile(sb) -> bool:
    if _click_turnstile(sb):
        return True
    coords = js(sb, TS_COORDS_JS)
    if coords:
        try:
            if hasattr(sb, "cdp") and hasattr(sb.cdp, "gui_click_x_y"):
                print(f"🖱️ 坐标点击 Turnstile ({coords['cx']},{coords['cy']})")
                sb.cdp.gui_click_x_y(int(coords["cx"]), int(coords["cy"]))
                return True
        except Exception as e:
            print(f"⚠️ 坐标点击失败: {e}")
    try:
        if hasattr(sb, "cdp") and hasattr(sb.cdp, "click_captcha"):
            print("🖱️ 兜底调用cdp点击 ...")
            sb.cdp.click_captcha()
            return True
        print("⚠️ 当前 SeleniumBase 版本无 sb.cdp.click_captcha")
    except Exception as e:
        print(f"⚠️ click_captcha 出错: {e}")
    return False

def solve_turnstile(sb, timeout=90, tag="Turnstile", first_wait=8) -> bool:
    if turnstile_token(sb):
        return True

    deadline = time.time() + timeout
    next_click = time.time() + first_wait
    clicks = 0
    while time.time() < deadline:
        if turnstile_token(sb):
            print(f"✅ {tag}已通过(已获取 token)")
            return True
        if time.time() >= next_click:
            clicks += 1
            print(f"🖱️ 第 {clicks} 次点击 Turnstile 验证框...")
            click_turnstile(sb)
            next_click = time.time() + 10 + random.uniform(0, 3)
        time.sleep(2)
    ok = bool(turnstile_token(sb))
    print(f"{'✅' if ok else '❌'} {tag}{'已通过' if ok else '未通过'}")
    return ok

def handle_turnstile(sb) -> bool:
    print("🛡️ 处理 Turnstile 验证...")
    return solve_turnstile(sb, timeout=90, tag="Turnstile", first_wait=8)
    
# 获取当前出口ip
def get_current_ip(proxy_server: str = "") -> str:
    proxies = None
    if proxy_server:
        proxies = {"http": proxy_server, "https": proxy_server}
    response = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=15)
    response.raise_for_status()
    return response.text.strip()

# 代理地址归一化，兼容:
#   http://user:pass@host:port / user:pass@host:port / host:port:user:pass / host:port / socks5://host:port
# 返回 (SeleniumBase 代理, requests 代理, 展示文本)
def normalize_proxy(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return "", "", ""
    scheme = "http"
    rest = raw
    if "://" in raw:
        scheme, rest = raw.split("://", 1)
    scheme = scheme.lower()
    user = pwd = ""
    if "@" in rest:
        cred, rest = rest.rsplit("@", 1)
        user, _, pwd = cred.partition(":")
    elif rest.count(":") == 3:  # b2proxy 导出的 host:port:user:pass
        host, port, user, pwd = rest.split(":", 3)
        rest = f"{host}:{port}"

    if scheme.startswith("socks"):
        if user:
            print("⚠️ Chrome 不支持 SOCKS5 认证, 请改用代理商提供的 HTTP 端口")
        sb_proxy = f"{scheme}://{rest}"
    elif user:
        sb_proxy = f"{user}:{pwd}@{rest}"
    else:
        sb_proxy = rest

    req_proxy = f"{scheme}://"
    if user:
        req_proxy += f"{quote(user, safe='')}:{quote(pwd, safe='')}@"
    req_proxy += rest
    display = f"{scheme}://{rest}" + (f" (用户: {user})" if user else "")
    return sb_proxy, req_proxy, display

# 时间格式化（兼容 HH:MM:SS、HH:MM 和 "3d 4h 5m" 等写法）
def format_countdown(countdown_str: str) -> str:
    if not countdown_str:
        return ""
    text = re.sub(r"\s+", " ", str(countdown_str)).strip()
    if ":" in text and not re.search(r"[dhms]", text, re.I):
        try:
            parts = text.split(":")
            h, m = int(parts[0]), int(parts[1])
            return f"{h}h{m}min" if h > 0 else f"{m}min"
        except Exception:
            return text
    return text

# 归一化日期为 YYYY/MM/DD
def normalize_date(date_str: str) -> str:
    parts = date_str.split('/')
    if len(parts) == 3:
        if len(parts[2]) == 4:   # MM/DD/YYYY
            return f"{parts[2]}/{int(parts[0]):02d}/{int(parts[1]):02d}"
        if len(parts[0]) == 4:   # YYYY/MM/DD
            return f"{parts[0]}/{int(parts[1]):02d}/{int(parts[2]):02d}"
    return date_str

# 日期格式：14 Nov 2026 / 14/11/2026 / 2026-11-14
DATE_RE = r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})"

# 续期冷却倒计时，兼容 "Renew in 3d 4h 5m" 和 "Renew in 00:23:59"
COUNTDOWN_RE = re.compile(
    r"(?:Renewal cooldown|Renew in|Renewable in|Next renew in)\s*[:\-]?\s*"
    r"((?:\d+\s*[dhms]\s*)+|\d{1,3}:\d{2}(?::\d{2})?)",
    re.I,
)

def extract_countdown(text: str) -> str:
    match = COUNTDOWN_RE.search(text or "")
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""

def extract_expiry_date(page_source: str) -> str:
    patterns = [
        r"[Ee]xpires\s*[:\-]?\s*" + DATE_RE,   # 优先匹配包含 "Expires" 的
        DATE_RE,                                # 兜底匹配
    ]
    
    for pattern in patterns:
        match = re.search(pattern, page_source)
        if match:
            # match.group(1) 现在能准确拿到完整的日期字符串
            return normalize_date(match.group(1))
            
    return None

# 优先从 Free plan 卡片提取到期日期，避免读到其它卡片的日期
def get_expiry_from_dom(sb) -> str:
    try:
        free_plan_text = str(js(sb, FREE_PLAN_TEXT_JS, "") or "")
        match = re.search(DATE_RE, free_plan_text)
        if match:
            return normalize_date(match.group(1))
    except Exception:
        pass
    for selector in ['span.st-meta', '.st-meta', '[class*="st-meta"]']:
        try:
            if sb.is_element_present(selector):
                match = re.search(DATE_RE, sb.get_text(selector))
                if match:
                    return normalize_date(match.group(1))
        except Exception:
            pass
    return None

# 点击确认后轮询账单页，确认续期是否真的生效
# 返回 (是否成功, 最新到期日, 冷却倒计时, 说明)
def confirm_renewal_result(sb, current_expiry: str, timeout: int = 60) -> tuple:
    deadline = time.time() + timeout
    last_expiry = current_expiry
    rounds = 0
    while True:
        rounds += 1
        sb.sleep(3)
        try:
            # 带时间戳重新打开账单页，避开前端缓存
            sb.open(f"{BASE_URL}/dash/billings?_r={int(time.time())}")
            sb.wait_for_ready_state_complete()
            sb.sleep(2)
        except Exception as e:
            print(f"⚠️ 刷新账单页失败: {e}")
        try:
            text = sb.get_page_text() + "\n" + sb.get_page_source()
        except Exception:
            text = sb.get_page_source()
        latest = get_expiry_from_dom(sb) or extract_expiry_date(text)
        if latest:
            last_expiry = latest
        countdown = extract_countdown(text)
        print(f"🔎 第 {rounds} 次核对: 到期日={last_expiry or '未知'} 倒计时={countdown or '无'}")
        if countdown:
            return True, last_expiry, countdown, "账单页已出现下次可续期倒计时"
        if current_expiry and latest and latest != current_expiry:
            return True, last_expiry, "", f"到期时间已更新（{current_expiry} → {latest}）"
        if time.time() >= deadline:
            return False, last_expiry, "", f"{timeout} 秒内账单页未出现续期倒计时，到期时间也未变化"
        sb.sleep(3)

# ---------- 续期弹窗与网络诊断 ----------
def get_dialog_state(sb) -> dict:
    raw = js(sb, DIALOG_BUTTONS_JS, "{}")
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def wait_dialog(sb, timeout: int = 30) -> dict:
    deadline = time.time() + timeout
    state = {}
    while time.time() < deadline:
        state = get_dialog_state(sb)
        # 弹窗结构识别失败时，只要页面上出现了续期确认按钮也算弹窗已就绪
        if state.get("found") or pick_renew_confirm_button(state):
            return state
        time.sleep(1)
    return state

def pick_renew_confirm_button(state: dict):
    """在弹窗按钮里挑选续期确认按钮（排除入口按钮 Renew free plan）"""
    candidates = []
    for btn in state.get("buttons", []):
        text = (btn.get("text") or "").strip()
        if not btn.get("visible") or not text:
            continue
        if not re.search(r"renew", text, re.I):
            continue
        if re.search(r"free\s*plan", text, re.I):
            continue
        # 没识别到弹窗时，只接受带天数的按钮，避免误点页面上的其它 Renew 入口
        if not state.get("found") and not re.search(r"\d+\s*days?", text, re.I):
            continue
        candidates.append(btn)
    for btn in candidates:
        if re.search(r"\d+\s*days?", btn["text"], re.I):
            return btn
    return candidates[0] if candidates else None

def print_dialog_state(state: dict, tag: str = "弹窗"):
    buttons = state.get("buttons") or []
    print(f"🧭 {tag}按钮清单({len(buttons)}个):")
    for btn in buttons:
        print(f"   - '{btn.get('text')}' class='{btn.get('cls')}' disabled={btn.get('disabled')} "
              f"visible={btn.get('visible')} rect=({btn.get('x')},{btn.get('y')},"
              f"{btn.get('w')}x{btn.get('h')})")

def wait_renew_confirm_enabled(sb, timeout: int = 30):
    """等待弹窗确认按钮出现且可点击（Turnstile 通过后按钮才启用）"""
    deadline = time.time() + timeout
    state = get_dialog_state(sb)
    while time.time() < deadline:
        state = get_dialog_state(sb)
        btn = pick_renew_confirm_button(state)
        if btn and not btn.get("disabled") and btn.get("w", 0) > 40 and btn.get("h", 0) > 15:
            return btn, state
        time.sleep(1)
    return None, state

def install_net_capture(sb):
    try:
        result = js(sb, NET_CAPTURE_JS, "")
        print(f"📡 页面网络记录已就绪: {result or 'unknown'}")
    except Exception as e:
        print(f"⚠️ 启用网络记录失败: {e}")

def read_net_log(sb) -> list:
    raw = js(sb, "return JSON.stringify(window.__renewNet || []);", "[]")
    try:
        data = json.loads(raw or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []

def print_net_entries(entries: list, tag: str = "续期请求"):
    if not entries:
        print(f"📡 {tag}: 未捕获到任何非 GET 请求")
        return
    print(f"📡 {tag}({len(entries)}条):")
    for entry in entries[-20:]:
        print(f"   - [{entry.get('kind')}] {entry.get('method')} {entry.get('url')} "
              f"-> {entry.get('status')} body={(entry.get('body') or '')[:400]}")
        if entry.get("reqBody"):
            print(f"     请求体: {str(entry.get('reqBody'))[:400]}")
        if entry.get("reqHeaders"):
            print(f"     请求头: {str(entry.get('reqHeaders'))[:400]}")
        if entry.get("respHeaders"):
            print(f"     响应头: {str(entry.get('respHeaders'))[:400]}")
        if entry.get("error"):
            print(f"     error={entry.get('error')}")

def wait_renew_request(sb, since: int = 0, timeout: int = 45, require_status: bool = True):
    """等待点击确认后的非 GET 请求；require_status=False 时只要请求已发出就算命中"""
    deadline = time.time() + timeout
    data = []
    while time.time() < deadline:
        data = read_net_log(sb)
        for entry in data[since:]:
            if not entry.get("url"):
                continue
            if not require_status:
                return True, data
            if entry.get("status") is not None:
                time.sleep(1)  # 等响应体异步读取完成
                return True, read_net_log(sb)
        time.sleep(1)
    return False, read_net_log(sb)

def get_visible_feedback(sb) -> str:
    return str(js(sb, FEEDBACK_JS, "") or "")

def print_fingerprint(sb):
    """打印关键浏览器指纹，便于判断服务端是否按自动化特征拒绝"""
    raw = js(sb, FINGERPRINT_JS, "{}")
    try:
        data = json.loads(raw or "{}")
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    print("🧬 浏览器环境: "
          f"webdriver={data.get('webdriver')} tz={data.get('timezone')} "
          f"lang={data.get('languages')} screen={data.get('screen')} "
          f"window={data.get('outer')} inner={data.get('inner')} "
          f"cores={data.get('cores')} plugins={data.get('plugins')}")
    print("🧬 WebGL: "
          f"{data.get('webglVendor') or '未知'} / {data.get('webglRenderer') or '未知'} "
          f"cf_clearance={data.get('cfClearance')} "
          f"cookies={data.get('cookies') or '无'}")
    print(f"🧬 UA: {data.get('ua') or '未知'}")

def looks_like_success_response(status, body: str) -> bool:
    try:
        code = int(status)
    except Exception:
        return False
    if not (200 <= code < 300):
        return False
    text = (body or "").lower()
    if re.search(r'"(success|ok)"\s*:\s*(false|"false")', text):
        return False
    if re.search(r'"(error|errors)"\s*:', text):
        return False
    if re.search(r"\b(error|failed|invalid|forbidden|expired|denied|cooldown|too many)\b", text):
        return False
    if re.search(r"<title>\s*(login|sign in)", text):
        return False
    return True

def find_outer_renew_button(sb):
    """返回 (状态, 按钮文本, selector)；状态为 ready / cooldown / None"""
    possible_selectors = [
        'type:button("Renew free plan")',
        'button:contains("Renew free plan")',
        'button:contains("Renew")',
        '[class*="btn btn-primary btn-sm"]',
    ]
    for selector in possible_selectors:
        try:
            if not sb.is_element_visible(selector):
                continue
            button_text = sb.get_text(selector)
            if extract_countdown(button_text):
                return "cooldown", button_text, selector
            if re.search(r"renew", button_text, re.I):
                return "ready", button_text, selector
        except Exception:
            continue
    return None, None, None

def attempt_renewal(sb, current_expiry: str) -> dict:
    """执行一次续期：点入口按钮 -> 过 Turnstile -> 点确认 -> 等请求 -> 复核结果"""
    state, button_text, selector = find_outer_renew_button(sb)
    if state == "cooldown":
        countdown = extract_countdown(button_text)
        print(f"✅ 当前已处于续期冷却: '{button_text}'")
        return {"ok": True, "expiry": current_expiry, "countdown": countdown,
                "reason": f"账单页已显示冷却倒计时（{button_text}）"}
    if state != "ready":
        return {"ok": False, "expiry": current_expiry, "countdown": "",
                "reason": "未找到可用的续期按钮或倒计时"}

    print(f"🔄 点击外部续期按钮: '{button_text}'")
    try:
        sb.sleep(2)
        sb.click(selector)
    except Exception as e:
        return {"ok": False, "expiry": current_expiry, "countdown": "",
                "reason": f"点击外部续期按钮失败: {e}"}

    dialog = wait_dialog(sb, timeout=30)
    if not dialog.get("found") and not pick_renew_confirm_button(dialog):
        feedback = get_visible_feedback(sb)
        print(f"💬 页面提示: {feedback or '（无）'}")
        return {"ok": False, "expiry": current_expiry, "countdown": "",
                "reason": "点击续期按钮后未出现续期弹窗", "evidence": {"feedback": feedback}}
    print(f"🧾 续期弹窗已出现: {dialog.get('text', '')[:160]}")
    print_dialog_state(dialog)

    turnstile_passed = True
    if wait_turnstile_present(sb, timeout=40):
        turnstile_passed = handle_turnstile(sb)
        if not turnstile_passed:
            print("❌ 弹窗 Turnstile 验证失败，尝试兜底点击...")
            try:
                sb.cdp.click_captcha()
                sb.sleep(4)
                turnstile_passed = bool(turnstile_token(sb))
            except Exception as e:
                print(f"⚠️ 兜底点击失败: {e}")
    else:
        print("ℹ️ 弹窗内未检测到 Turnstile")

    if not turnstile_passed:
        feedback = get_visible_feedback(sb)
        print(f"💬 页面提示: {feedback or '（无）'}")
        return {"ok": False, "expiry": current_expiry, "countdown": "",
                "reason": "Turnstile 验证未通过", "evidence": {"feedback": feedback}}

    print("⏳ 等待弹窗确认按钮变为可用...")
    confirm_btn, latest_state = wait_renew_confirm_enabled(sb, timeout=30)
    print_dialog_state(latest_state, "等待后")
    if not confirm_btn:
        feedback = get_visible_feedback(sb)
        print("⚠️ 未找到可用的续期确认按钮，弹窗 HTML 片段：")
        print(str(latest_state.get("html", ""))[:3000])
        print(f"💬 页面提示: {feedback or '（无）'}")
        return {"ok": False, "expiry": current_expiry, "countdown": "",
                "reason": "弹窗内未找到可用的续期确认按钮",
                "evidence": {"feedback": feedback, "dialog_html": latest_state.get("html", "")}}

    mark = int(js(sb, "window.__renewMark = (window.__renewNet || []).length; "
                      "return window.__renewMark;", 0) or 0)

    # 模拟真人读完提示再操作：随机停留 + 轻微滚动 + 鼠标移动
    sb.sleep(random.uniform(2.0, 4.5))
    try:
        jx, jy = _screen_point(sb, random.randint(200, 900), random.randint(120, 620))
        _move_mouse_screen(jx, jy)
        sb.sleep(random.uniform(0.3, 0.9))
    except Exception:
        pass
    js(sb, "window.scrollBy(0, " + str(random.randint(10, 60)) + "); return 1;", 1)
    sb.sleep(random.uniform(0.3, 0.8))

    point = js(sb, SCROLL_CONFIRM_BTN_JS, None)
    clicked = False
    if point and point.get("w", 0) > 0:
        cx = int(point["x"] + point["w"] / 2)
        cy = int(point["y"] + point["h"] / 2)
        print(f"🖱️ 点击续期确认按钮 '{point.get('text')}' ({cx}, {cy})")
        clicked = _click_viewport_point(sb, cx, cy, "续期确认按钮")
    if not clicked:
        try:
            sb.click('div[role="dialog"] button.btn-primary', timeout=5)
            clicked = True
            print("✅ 已兜底点击续期确认按钮")
        except Exception as e:
            print(f"⚠️ 兜底点击续期确认按钮失败: {e}")

    if not clicked:
        return {"ok": False, "expiry": current_expiry, "countdown": "",
                "reason": "未能点击弹窗确认按钮"}

    # 先用短超时确认请求是否真的发出，没发出说明点击未生效，再补一次 SeleniumBase 点击
    fired, net = wait_renew_request(sb, since=mark, timeout=12, require_status=False)
    if not fired:
        feedback = get_visible_feedback(sb)
        print(f"⚠️ 首次点击后 12 秒内未发出任何续期请求，页面提示: {feedback or '（无）'}")
        print("🖱️ 尝试用 SeleniumBase 再点一次确认按钮...")
        try:
            sb.click('div[role="dialog"] button.btn-primary', timeout=5)
        except Exception as e:
            print(f"⚠️ 二次点击失败: {e}")
        fired, net = wait_renew_request(sb, since=mark, timeout=15, require_status=False)

    print("⏳ 等待续期请求返回（最多 45 秒）...")
    captured, net = wait_renew_request(sb, since=mark, timeout=45)
    candidates = net[mark:]
    print_net_entries(candidates)
    feedback = get_visible_feedback(sb)
    if feedback:
        print(f"💬 点击后页面提示: {feedback}")
    dialog_after = get_dialog_state(sb)
    print(f"🧭 点击后弹窗状态: {'仍显示' if dialog_after.get('found') else '已关闭'}")

    req_status = None
    req_body = ""
    # 优先看续期/订阅相关接口，找不到再退回站点内任意请求，避免把其它 API 当成续期结果
    ordered = [e for e in candidates
               if re.search(r"renew|subscription|billing|plan|checkout",
                            str(e.get("url") or ""), re.I)] + candidates
    for entry in ordered:
        url = str(entry.get("url") or "")
        if entry.get("status") is not None and ("bot-hosting" in url or url.startswith("/")):
            req_status = entry.get("status")
            req_body = str(entry.get("body") or "")
    api_success = looks_like_success_response(req_status, req_body)
    evidence = {
        "net": candidates,
        "feedback": feedback,
        "dialog_closed": not dialog_after.get("found"),
        "req_status": req_status,
        "req_body": req_body[:1000],
    }

    sb.sleep(2)
    ok, new_expiry, countdown, reason = confirm_renewal_result(sb, current_expiry, timeout=60)
    if ok:
        return {"ok": True, "expiry": new_expiry, "countdown": countdown,
                "reason": reason, "evidence": evidence}
    if api_success:
        return {"ok": True, "expiry": new_expiry or current_expiry, "countdown": "",
                "reason": f"续期接口返回 HTTP {req_status}，服务端已接受", "evidence": evidence}
    if req_status:
        return {"ok": False, "expiry": new_expiry, "countdown": "",
                "reason": f"续期请求返回 HTTP {req_status}: {req_body[:200]}", "evidence": evidence}
    if captured or fired:
        return {"ok": False, "expiry": new_expiry, "countdown": "",
                "reason": "已发出请求但未拿到有效响应，结果未知", "evidence": evidence}
    return {"ok": False, "expiry": new_expiry, "countdown": "",
            "reason": "点击确认按钮后未捕获到续期请求（按钮未真正提交或被前端拦截）",
            "evidence": evidence}

def save_debug_artifacts(sb, tag: str, evidence=None):
    """失败时保存截图、页面 HTML 和网络证据，便于排查"""
    png_path = f"renew_debug_{tag}.png"
    try:
        sb.driver.save_screenshot(png_path)
        print(f"📸 已保存现场截图: {png_path}")
    except Exception as e:
        try:
            sb.save_screenshot(png_path)
            print(f"📸 已保存现场截图: {png_path}")
        except Exception as e2:
            print(f"⚠️ 保存截图失败: {e} / {e2}")
    try:
        html_path = f"renew_debug_{tag}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(sb.get_page_source())
        print(f"📄 已保存页面 HTML: {html_path}")
    except Exception as e:
        print(f"⚠️ 保存 HTML 失败: {e}")
    if evidence:
        try:
            net_path = f"renew_debug_{tag}_net.json"
            with open(net_path, "w", encoding="utf-8") as f:
                json.dump(evidence, f, ensure_ascii=False, indent=2)
            print(f"📡 已保存网络与提示证据: {net_path}")
        except Exception as e:
            print(f"⚠️ 保存网络证据失败: {e}")

# 主流程
def main():
    print("#" * 25)
    print("   Bot-hosting 自动续期")
    print("#" * 25)

    IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
    PROXY_RAW = os.environ.get("PROXY_SERVER", "").strip()
    if IS_PROXY and not PROXY_RAW:
        PROXY_RAW = "socks5://127.0.0.1:1080"  # 未显式配置时使用本地 sing-box
    SB_PROXY, PROXY_URL, PROXY_DISPLAY = normalize_proxy(PROXY_RAW)
    IS_PROXY = IS_PROXY and bool(SB_PROXY)
    HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true" 

    sb_kwargs = {"uc": True, "headless": HEADLESS, "locale_code": "en-US"}

    if IS_PROXY:
        print(f"🔗 挂载代理: {PROXY_DISPLAY}")
        sb_kwargs["proxy"] = SB_PROXY
    else:
        print("🍭 未使用代理，直连访问")

    with SB(**sb_kwargs) as sb:
        try:
            ip = get_current_ip(PROXY_URL if IS_PROXY else "")
            print(f"📍 当前出口IP: {ip}")
        except Exception as e:
            print(f"⚠️ 获取出口 IP 失败: {e}")

        login_ok = False

        # 账号密码登录（密码不过期，唯一登录方式；整段兜异常，失败只标记 login_ok=False 走统一失败通知）
        if EMAIL and PASSWORD:
            print("🚀 启动浏览器...")
            try:
                print(f"🌐 访问 {BASE_URL}/login")
                sb.open(f"{BASE_URL}/login")
                sb.wait_for_ready_state_complete()
                sb.sleep(3)
                sb.click('button[type="submit"]') # 点击 Continue with email 按钮
                sb.sleep(12)  # 等待页面加载
                print(f"📧 填写邮箱...")
                sb.input('input[type="email"]', EMAIL)
                sb.sleep(1)
                print(f"🔑 填写密码...")
                sb.input('input[type="password"]', PASSWORD)
                sb.sleep(3)

                if wait_turnstile_present(sb):
                    if not handle_turnstile(sb):
                        print("❌ 登录界面的 Turnstile 验证失败，尝试兜底点击...")
                        try:
                            sb.cdp.click_captcha()  # 再次尝试点击 Turnstile 验证
                            sb.sleep(4)
                        except Exception as e:
                            print(f"⚠️ 兜底点击失败: {e}")
                        # sb.save_screenshot("turnstile_failed.png")
                else:
                    print("ℹ️ 未检测到 Turnstile")
                sb.sleep(1)
                sb.click('button[type="submit"]') # 点击登录按钮
                print("🖱️ 提交登录按钮")
                sb.sleep(6)  # 等待页面加载
                sb.wait_for_ready_state_complete()
                sb.open(f"{BASE_URL}/dash/billings")
                sb.wait_for_ready_state_complete()
                sb.sleep(3)
                current_url = sb.get_current_url()
                current_title = sb.get_title()
                print(f"📝 当前URL: {current_url}, Title: {current_title}")

                if "/dash/billings" in current_url and "/login" not in current_url and "error=" not in current_url:
                    login_ok = True
                    print("✅ Password 登录成功,当前已到达账单页")
                else:
                    print(f"❌ Password 登录后仍未到达账单页，当前URL: {current_url}")
            except Exception as e:
                    print(f"❌ Password 登录过程异常: {type(e).__name__}: {str(e)[:150]}")

        if not login_ok:
            send_moviepilot_message(format_notification("❌ 登录失败", error="Password 登录失败"))
            return

        # 提取当前到期日期
        sb.sleep(3)
        try:
            page_source = sb.get_page_text() + "\n" + sb.get_page_source()
        except Exception:
            page_source = sb.get_page_source()
        current_expiry = get_expiry_from_dom(sb) or extract_expiry_date(page_source)
        if current_expiry:
            print(f"📅 当前到期日期: {current_expiry}")
        else:
            print("⚠️ 未能提取当前到期日期")

        # 先记录一次浏览器环境，便于判断续期被拒是否与自动化特征有关
        print_fingerprint(sb)

        # 续期：定位入口按钮 -> 过 Turnstile -> 点确认 -> 等待请求 -> 复核结果，失败自动重试一次
        result = None
        for attempt in range(1, 3):
            if attempt > 1:
                print("🔁 重新加载账单页后重试续期...")
                try:
                    sb.open(f"{BASE_URL}/dash/billings?_r={int(time.time())}")
                    sb.wait_for_ready_state_complete()
                    sb.sleep(3)
                except Exception as e:
                    print(f"⚠️ 重载账单页失败: {e}")
                    break
            install_net_capture(sb)
            result = attempt_renewal(sb, current_expiry)
            if result.get("ok"):
                break
            print(f"⚠️ 第 {attempt} 次续期未成功: {result.get('reason')}")
            print_fingerprint(sb)
            save_debug_artifacts(sb, f"attempt{attempt}", result.get("evidence"))

        if result and result.get("ok"):
            new_expiry = result.get("expiry") or current_expiry
            new_countdown = result.get("countdown") or ""
            reason = result.get("reason") or "续期成功"
            print(f"✅ 续期成功（{reason}）")
            extra = f"⏱️ 可续期时间: {format_countdown(new_countdown)}后" if new_countdown else reason
            send_moviepilot_message(
                format_notification(
                    "✅ 续期成功",
                    extra=extra,
                    expiry_date=new_expiry or "（未获取到）"
                )
            )
        else:
            reason = (result or {}).get("reason") or "续期失败"
            new_expiry = (result or {}).get("expiry") or current_expiry
            print(f"❌ 续期失败（{reason}）")
            send_moviepilot_message(
                format_notification(
                    "❌ 续期失败",
                    error=reason,
                    expiry_date=new_expiry or "（未获取到）"
                )
            )

        print("🏁 脚本执行完毕")

if __name__ == "__main__":
    main()
