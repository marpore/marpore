"""Draw the 24-hour city as one animated SVG.

How the picture encodes the data:
  x axis           hour of day (0-24); the sky follows today's sunrise, sunset and weather
  building height  commits made in that hour, all time
  floors           stacked by year, oldest at the bottom (brick, then concrete, then glass)
  window colour    languages used in that year
"""
from __future__ import annotations

import datetime as dt
import math
import random

W, H, GROUND, FLOOR = 960, 452, 290, 9
GUTTER = 36                 # left margin that holds the commit ruler
COL = (W - GUTTER) / 24     # width of one hour
WATER_TOP, WATER_BOTTOM = GROUND + 14, GROUND + 94
MAX_HEIGHT = 200
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
OTHER = "Other"
OTHER_COLOR = "#8a93b0"
COVER = {"clear": 0, "partly": .2, "cloudy": .6, "fog": .5, "rain": .75, "thunder": .88, "snow": .7}
ERA_TINT = [(40, 10, -8), (8, 8, 4), (-10, 10, 30)]   # brick / concrete / glass
NEON = ["#ff5fa2", "#5ff2ff", "#9dff6a", "#ffd166"]
AWNING = ["#e76f51", "#2a9d8f", "#e9c46a", "#8ab4f8", "#c77dff"]
SYNODIC = 29.530588
FONT = {   # 5x7 dot-matrix glyphs
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01110", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "01110 00100 00100 00100 00100 00100 01110", "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001", "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001", "N": "10001 11001 10101 10011 10001 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110", "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101", "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 11011 10001", "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100", "Z": "11111 00001 00010 00100 01000 10000 11111",
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111", "3": "11110 00001 00001 01110 00001 00001 11110",
    "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "01110 10000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 00100 00100 00100",
    "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00001 01110",
    ":": "00000 00100 00000 00000 00000 00100 00000", ".": "00000 00000 00000 00000 00000 00000 00100",
    ",": "00000 00000 00000 00000 00000 00100 01000", "%": "11001 11010 00010 00100 01000 01011 10011",
    "/": "00001 00010 00010 00100 01000 01000 10000", "-": "00000 00000 00000 01110 00000 00000 00000",
    "+": "00000 00100 00100 11111 00100 00100 00000", "#": "01010 01010 11111 01010 11111 01010 01010",
}


# ---------- small helpers ----------
def X(hour):
    return GUTTER + hour * COL


def hexrgb(s):
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def rgb(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in c)


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def add(c, v):
    return tuple(x + (v if isinstance(v, (int, float)) else v[i]) for i, x in enumerate(c))


def vivid(color):
    """Brighten a language colour so it still reads as a lit window at night."""
    c = hexrgb(color)
    top = max(c)
    return rgb(tuple(v * 216 / top for v in c)) if 0 < top < 216 else rgb(c)


def plural(n, word):
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}S"


def ptext(text, x, y, px, fill, extra=""):
    uses = "".join(f'<use href="#g{ord(ch)}" x="{i * 6}"/>' for i, ch in enumerate(text) if ch in FONT)
    return f'<g transform="translate({x:.1f},{y:.1f}) scale({px})" fill="{fill}" {extra}>{uses}</g>'


def dot_text(text):
    """Upper-case and keep only what the dot-matrix font can show."""
    return "".join(ch if ch in FONT or ch == " " else " " for ch in text.upper())


def nice_step(top):
    target = max(top / 2.2, 1)
    magnitude = 10 ** math.floor(math.log10(target))
    for m in (1, 2, 5, 10):
        if m * magnitude >= target:
            return m * magnitude
    return 10 * magnitude


def ridge_h(x, base, amp, k):
    return base + amp * (.5 * math.sin(x / 90 + k) + .3 * math.sin(x / 37 + 2 * k) + .2 * math.sin(x / 17 + 3 * k) + .6)


def ridge(base, amp, k, shift=0.0):
    return " ".join([f"-10,{GROUND}"] + [f"{x},{GROUND - ridge_h(x - shift, base, amp, k):.1f}" for x in range(-10, W + 20, 10)] + [f"{W + 10},{GROUND}"])


def moon_age(day):
    noon_utc = dt.datetime(day.year, day.month, day.day, 3)   # about local noon in East Asia; precision is not critical
    return ((noon_utc - dt.datetime(2000, 1, 6, 18, 14)).total_seconds() / 86400) % SYNODIC


def moon_svg(cx, cy, r, age):
    p = age / SYNODIC
    rx, waxing = abs(math.cos(2 * math.pi * p)) * r, p < .5
    q = p if waxing else 1 - p
    d = f"M{cx:.1f},{cy - r:.1f} A{r},{r} 0 0 1 {cx:.1f},{cy + r:.1f} A{rx:.2f},{r} 0 0 {0 if q < .25 else 1} {cx:.1f},{cy - r:.1f}Z"
    flip = "" if waxing else f' transform="translate({2 * cx:.1f},0) scale(-1,1)"'
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 3.2}" fill="url(#moonhalo)"/>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="#c9d3ff" opacity=".12"/>'
            f'<clipPath id="lit"><path d="{d}"{flip}/></clipPath>'
            f'<path d="{d}" fill="#fff6d8" filter="url(#glow)"{flip}/>'
            f'<g clip-path="url(#lit)" fill="#d9c98f" opacity=".55"><circle cx="{cx - 4:.1f}" cy="{cy - 5:.1f}" r="3.2"/>'
            f'<circle cx="{cx + 5:.1f}" cy="{cy + 2:.1f}" r="2.4"/><circle cx="{cx - 2:.1f}" cy="{cy + 7:.1f}" r="2"/><circle cx="{cx + 8:.1f}" cy="{cy - 7:.1f}" r="1.5"/></g>')


class Sky:
    """Light and weather as a function of the hour."""

    def __init__(self, sunrise, sunset, weather):
        self.sr, self.ss, self.wx = sunrise, sunset, weather
        sr, ss = sunrise, sunset
        keys = [(0, "#040716", "#121a3e"), (sr - 1.6, "#050919", "#161d45"), (sr - .8, "#0f1a45", "#5a4a86"),
                (sr - .2, "#22357a", "#e07f7a"), (sr + .3, "#3f66b0", "#ffb070"), (sr + 1.0, "#4f8fda", "#ffe0a8"),
                (sr + 2.2, "#4a9ae4", "#cfeafa"), ((sr + ss) / 2, "#3d90e0", "#bfe2f8"), (ss - 2.2, "#4a98e2", "#d2e9f7"),
                (ss - 1.0, "#5187d0", "#ffd898"), (ss - .3, "#4a5aa6", "#ff9a62"), (ss + .3, "#31307a", "#e5607a"),
                (ss + .9, "#161a4c", "#6b3f85"), (ss + 1.7, "#060a20", "#1a1f4c"), (24, "#040716", "#121a3e")]
        self.keys = sorted((max(0, min(24, h)), a, b) for h, a, b in keys)

    def daylight(self, h):
        sr, ss = self.sr, self.ss
        if h < sr - .8 or h > ss + 1.2:
            return 0.0
        if h < sr + 1.5:
            return (h - (sr - .8)) / 2.3
        if h > ss - 1.2:
            return ((ss + 1.2) - h) / 2.4
        return 1.0

    def twilight(self, h):
        return max(0, 1 - abs(h - self.sr) / 1.3, 1 - abs(h - self.ss) / 1.3)

    def kind(self, h):
        return self.wx[min(23, max(0, int(h)))]

    def cover(self, h):
        return COVER[self.kind(h)]

    def color(self, h, idx):
        for (h0, *c0), (h1, *c1) in zip(self.keys, self.keys[1:]):
            if h0 <= h <= h1:
                return lerp(hexrgb(c0[idx]), hexrgb(c1[idx]), (h - h0) / (h1 - h0) if h1 > h0 else 0)
        return hexrgb(self.keys[-1][1 + idx])

    def timed(self, night, day, dusk, amount=.6):
        return lambda h: lerp(lerp(night, day, self.daylight(h)), dusk, self.twilight(h) * amount)


def hgrad(gid, fn, opacity=None):
    s = [f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{GUTTER}" x2="{W}" y1="0" y2="0">']
    for i in range(97):
        h = i / 4
        op = f' stop-opacity="{opacity(h):.2f}"' if opacity else ""
        s.append(f'<stop offset="{h / 24:.4f}" stop-color="{rgb(fn(h))}"{op}/>')
    return "".join(s) + "</linearGradient>"


def cloud(rng, sky, cx, cy, s, h, kind):
    """A cumulus built from overlapping puffs, with a shaded underside."""
    d = sky.daylight(h)
    base = {"partly": ((255, 255, 255), (198, 215, 236)), "cloudy": ((220, 226, 237), (160, 171, 192)),
            "rain": ((152, 162, 184), (98, 108, 134)), "thunder": ((114, 122, 150), (62, 70, 98)),
            "snow": ((230, 235, 244), (178, 188, 208))}[kind]
    wide = kind != "partly"
    tint = .45 if kind in ("rain", "thunder", "snow") else 1
    light, shade = (lerp(lerp(c, n, (1 - d) * .82), t, sky.twilight(h) * a * tint)
                    for c, n, t, a in ((base[0], (52, 60, 96), (255, 196, 168), .6), (base[1], (26, 32, 60), (206, 120, 140), .5)))
    hi = lerp(light, (255, 255, 255), .55)
    span = (64 if wide else 36) * s
    n = rng.randint(6, 8) if wide else rng.randint(4, 6)
    lobes = []
    for i in range(n):
        t = i / (n - 1)
        r = ((7.5 + 5.5 * math.sin(math.pi * t)) if wide else (7 + 7 * math.sin(math.pi * t) ** .8)) * s * rng.uniform(.9, 1.12)
        lobes.append((cx + (t - .5) * span + rng.uniform(-2, 2) * s, cy - r * .78 + rng.uniform(-1, 1) * s, r))
    crown = [(cx + rng.uniform(-.2, .2) * span, cy - rng.uniform(13, 18) * s, rng.uniform(8, 11) * s)
             for _ in range(2 if wide else rng.randint(1, 2))]

    def circles(items, dx, dy, k):
        return "".join(f'<circle cx="{x + dx * r:.1f}" cy="{y + dy * r:.1f}" r="{r * k:.1f}"/>' for x, y, r in items)
    return (f'<g class="cloud" style="animation-delay:-{rng.uniform(0, 16):.1f}s">'
            f'<g fill="{rgb(shade)}"><ellipse cx="{cx:.1f}" cy="{cy - 3 * s:.1f}" rx="{span * .5:.1f}" ry="{7 * s:.1f}"/>{circles(lobes + crown, 0, 0, 1)}</g>'
            f'<g fill="{rgb(light)}"><ellipse cx="{cx - s:.1f}" cy="{cy - 5.5 * s:.1f}" rx="{span * .47:.1f}" ry="{6 * s:.1f}"/>{circles(lobes + crown, -.06, -.2, .9)}</g>'
            f'<g fill="{rgb(hi)}" opacity=".4">{circles(crown, -.14, -.26, .68)}</g></g>')


STYLE = """<style>
.tw{animation:tw 3.4s ease-in-out infinite}
@keyframes tw{0%,100%{opacity:.2}50%{opacity:1}}
.blink{animation:blink 2s steps(1) infinite}
@keyframes blink{0%,60%{opacity:1}61%,100%{opacity:.08}}
.neon{animation:neon 5s steps(1) infinite}
@keyframes neon{0%,100%{opacity:1}90%{opacity:.3}92%{opacity:1}95%{opacity:.5}96%{opacity:1}}
.cloud{animation:drift 16s ease-in-out infinite alternate}
@keyframes drift{from{transform:translateX(-8px)}to{transform:translateX(8px)}}
.rays{animation:spin 90s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.drop{animation:fall .8s linear infinite}
@keyframes fall{from{transform:translate(0,0)}to{transform:translate(-46px,210px)}}
.splash{animation:splash 1s ease-out infinite;transform-box:fill-box;transform-origin:center}
@keyframes splash{from{transform:scale(.2);opacity:.9}to{transform:scale(1.5);opacity:0}}
.flake{animation:snow 8s linear infinite}
@keyframes snow{0%{transform:translate(0,0)}25%{transform:translate(6px,74px)}50%{transform:translate(-3px,148px)}75%{transform:translate(7px,222px)}100%{transform:translate(1px,296px)}}
.fog{animation:fog 22s ease-in-out infinite alternate}
@keyframes fog{from{transform:translateX(-18px)}to{transform:translateX(18px)}}
.bolt,.flash{animation:bolt 5s linear infinite;opacity:0}
.flash{animation-name:flash}
@keyframes bolt{0%,88%{opacity:0}89%{opacity:1}91%{opacity:.1}92%{opacity:.95}95%,100%{opacity:0}}
@keyframes flash{0%,88%{opacity:0}89%{opacity:.5}91%{opacity:.05}92%{opacity:.4}96%,100%{opacity:0}}
.shoot{animation:shoot 11s linear infinite;opacity:0}
@keyframes shoot{0%,90%{opacity:0;transform:translate(0,0)}91%{opacity:1}96%,100%{opacity:0;transform:translate(-60px,34px)}}
.plane{animation:plane 38s linear infinite}
@keyframes plane{from{transform:translate(0,0)}to{transform:translate(210px,-90px)}}
.birds{animation:birds 50s linear infinite alternate}
@keyframes birds{from{transform:translate(0,0)}to{transform:translate(120px,-16px)}}
.train{animation:run 26s linear infinite}
@keyframes run{from{transform:translateX(-80px)}to{transform:translateX(1000px)}}
.shim{animation:tw 5s ease-in-out infinite}
.ripple{animation:splash 1.6s ease-out infinite;transform-box:fill-box;transform-origin:center}
.ticker{animation:tick TICKDURs linear infinite}
@keyframes tick{to{transform:translateX(-TICKLENpx)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.bolt,.flash,.shoot{opacity:0}}
</style>"""


def render(d: dict) -> str:
    login = d["login"]
    day = dt.date.fromisoformat(d["date"])
    sky = Sky(d["sunrise"], d["sunset"], d["weather"])
    SR, SS, WX = sky.sr, sky.ss, sky.wx
    NOON = (SR + SS) / 2
    snow_cover = {h for h, on in enumerate(d["snow_cover"]) if on}
    rs = random.Random(d["date"])               # sky and weather change every day
    rc = random.Random(f"{login}:scenery")      # scenery stays put

    # ---------- data ----------
    hist = {int(h): {int(y): langs for y, langs in by_year.items()} for h, by_year in d["hist"].items()}
    totals = [sum(sum(langs.values()) for langs in hist.get(h, {}).values()) for h in range(24)]
    top = max(totals) or 1
    pxc = MAX_HEIGHT / top                      # pixels per commit
    floors = [0 if t <= 0 else max(1, round(t * pxc / FLOOR)) for t in totals]
    tops = [GROUND - n * FLOOR for n in floors]
    tallest = max(range(24), key=lambda h: totals[h])
    since, this_year = d["since"], day.year
    span = this_year - since + 1

    lang_total: dict[str, float] = {}
    for by_year in hist.values():
        for langs in by_year.values():
            for name, weight in langs.items():
                lang_total[name] = lang_total.get(name, 0) + weight
    grand = sum(lang_total.values()) or 1
    # Languages get their own colour, largest first, for as many as fit on one legend row;
    # the long tail is grouped as "Other".
    def entry(name, share):
        pct = f"{share * 100:.0f}" if share >= .0095 else f"{share * 100:.1f}"
        return name, pct, 9.5 + len(name) * 5.2 + 3 + (len(pct) + 1) * 4.8

    def with_other(names):
        out = [(n, lang_total[n] / grand) for n in names]
        rest = 1 - sum(share for _, share in out)
        return out + [(OTHER, rest)] if rest > .005 else out

    ranked = [n for n in sorted(lang_total, key=lambda n: -lang_total[n]) if n != OTHER and lang_total[n] / grand >= .005][:16]
    shares = with_other(ranked)
    while len(ranked) > 1 and sum(entry(*item)[2] + 14 for item in shares) - 14 > W - 32:
        ranked.pop()
        shares = with_other(ranked)
    colors = {n: vivid(d["colors"].get(n) or OTHER_COLOR) for n in ranked}
    colors[OTHER] = OTHER_COLOR
    legend = [[entry(*item) for item in shares]]
    height = H

    def era(year):
        age = this_year - year
        return 2 if age < span / 3 else 1 if age < 2 * span / 3 else 0

    def floor_years(h, n):
        by_year = sorted((y, sum(langs.values())) for y, langs in hist[h].items())
        total = sum(w for _, w in by_year)
        out, idx, acc = [], 0, by_year[0][1]
        for i in range(n):
            while idx < len(by_year) - 1 and (i + .5) / n > acc / total:
                idx += 1
                acc += by_year[idx][1]
            out.append(by_year[idx][0])
        return out

    def pick_language(h, year, r):
        langs = hist[h][year]
        total = sum(langs.values())
        acc = 0
        for name in sorted(langs):
            acc += langs[name]
            if r * total <= acc:
                return name if name in colors else OTHER
        return OTHER

    back, mid, city, front = [], [], [], []   # static backdrop / moving sky / static city / moving foreground

    # ---------- sky ----------
    back.append(f'<rect width="{W}" height="{GROUND}" fill="url(#zenith)"/><rect width="{W}" height="{GROUND}" fill="url(#horizon)" mask="url(#hm)"/>')
    for hx, gid in ((SR, "dawn"), (SS, "dusk")):
        back.append(f'<ellipse cx="{X(hx):.0f}" cy="{GROUND}" rx="120" ry="90" fill="url(#{gid})" opacity="{.75 * (1 - sky.cover(hx) * .6):.2f}"/>')
    back.append(f'<rect width="{W}" height="{GROUND}" fill="url(#overcast)"/>')
    major = nice_step(top)
    for i in range(1, int(top * 1.02 / major) + 1):
        back.append(f'<path d="M0,{GROUND - i * major * pxc:.1f} H{W}" stroke="#fff" stroke-opacity=".12" stroke-dasharray="1 6"/>')
    for h, kind in enumerate(WX):   # blurred cloud deck behind the puffs
        if COVER[kind] >= .6:
            c = lerp((30, 36, 62), (176, 184, 200) if kind == "snow" else (122, 132, 154), sky.daylight(h + .5))
            back.append(f'<ellipse cx="{X(h + .5):.1f}" cy="56" rx="48" ry="30" fill="{rgb(c)}" opacity=".5" filter="url(#soft)"/>')
    back.append(f'<path d="M{X(SR):.0f},{GROUND} Q{X(NOON):.0f},-202 {X(SS):.0f},{GROUND}" fill="none" stroke="#fff" stroke-opacity=".2" stroke-dasharray="2 6"/>')
    sun_op = 1 - sky.cover(NOON) * .7
    back.append(f'<g opacity="{sun_op:.2f}"><circle cx="{X(NOON):.0f}" cy="44" r="46" fill="url(#sunhalo)"/><circle cx="{X(NOON):.0f}" cy="44" r="12" fill="#fff3b0"/></g>')
    mid.append(f'<g class="rays" stroke="#fff3b0" stroke-width="1.6" stroke-linecap="round" opacity="{.7 * sun_op:.2f}" style="transform-origin:{X(NOON):.0f}px 44px">'
               + "".join(f'<line x1="{X(NOON) + 17 * math.cos(a):.1f}" y1="{44 + 17 * math.sin(a):.1f}" x2="{X(NOON) + 22 * math.cos(a):.1f}" y2="{44 + 22 * math.sin(a):.1f}"/>'
                         for a in (i * math.pi / 6 for i in range(12))) + '</g>')

    # The moon sits at the dark hour closest to when it is highest; hidden when it is only up in daylight.
    age = moon_age(day)
    transit = (12 + age / SYNODIC * 24) % 24
    moon = None
    best = None
    for q in range(4, 93):
        t = q / 4
        gap = min(abs(t - transit), 24 - abs(t - transit))
        if sky.daylight(t) == 0 and gap <= 5.5 and (best is None or gap < best[0]):
            best = (gap, t)
    if best:
        moon = (X(best[1]), 112 - 70 * math.cos(best[0] / 6 * math.pi / 2))
        back.append(moon_svg(moon[0], moon[1], 14, age))

    for _ in range(260):
        x, y = rs.uniform(2, W - 2), rs.uniform(6, 200)
        h = (x - GUTTER) / COL
        dim = 1 - sky.daylight(h) * 5
        r = rs.choice([.5, .6, .8, .8, 1, 1.3])
        col = rs.choice(["#fff", "#fff", "#cfe0ff", "#ffe9c9"])
        delay = f'style="animation-delay:-{rs.uniform(0, 4):.2f}s"'
        if dim <= 0 or rs.random() < sky.cover(h) * 1.3 or (moon and math.hypot(x - moon[0], y - moon[1]) < 22):
            continue
        if r > 1.2:
            mid.append(f'<path class="tw" {delay} d="M{x:.1f},{y - 3.4:.1f} l.8,2.6 2.6,.8 -2.6,.8 -.8,2.6 -.8,-2.6 -2.6,-.8 2.6,-.8z" fill="{col}" opacity="{dim:.2f}"/>')
        else:
            mid.append(f'<circle class="tw" {delay} cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{col}" opacity="{dim * (1 - y / 320):.2f}"/>')
    if day.month in (11, 12, 1, 2, 3) and sky.daylight(21.5) == 0 and sky.cover(22) < .5 and not (moon and abs(moon[0] - 898) < 70):
        orion = [(0, 0), (22, 3), (8, 24), (12, 22), (16, 20), (4, 46), (26, 42)]   # a winter evening constellation
        mid.append('<g transform="translate(884,44) rotate(-14)"><path d="M0,0 L8,24 L4,46 M22,3 L16,20 L26,42 M8,24 L16,20 M0,0 L22,3" stroke="#cfe0ff" stroke-opacity=".16" stroke-width=".6" fill="none"/>'
                   + "".join(f'<circle class="tw" cx="{x}" cy="{y}" r="{1.3 if i in (0, 6) else .9}" fill="{"#ffc9a8" if i == 0 else "#dfe9ff"}" style="animation-delay:-{i * .5}s"/>' for i, (x, y) in enumerate(orion)) + '</g>')
    if sky.daylight(2.5) == 0:
        mid.append('<line class="shoot" x1="88" y1="40" x2="108" y2="29" stroke="#fff" stroke-width="1.2" stroke-linecap="round"/>')
        mid.append('<g class="plane"><circle cx="24" cy="150" r="1" fill="#fff"/><circle class="blink" cx="26.5" cy="150" r="1" fill="#ff5a5a"/></g>')
    if sky.daylight(8) > .6 and sky.cover(8.5) < .3:
        mid.append('<g class="birds" fill="none" stroke="#31425f" stroke-width="1" stroke-linecap="round">'
                   + "".join(f'<path d="M{X(7.4) + dx:.1f},{66 + dy} q3,-3 6,0 q3,-3 6,0"/>' for dx, dy in ((0, 0), (16, -8), (20, 7), (36, -2), (-14, 9))) + '</g>')

    # ---------- hills, the name on the hillside, distant skyline ----------
    # The sign goes where the buildings in front are lowest; the hills are slid sideways so that
    # a peak of the far ridge and a dip of the near ridge meet there.
    sign = dot_text(login).replace(" ", "")[:20]
    spx = min(1.6, 96 / (len(sign) * 6)) if sign else 1.6
    sw, sh = len(sign) * 6 * spx, 7 * spx
    probe = (0, sw / 2, sw)

    def skyline(x):
        columns = range(max(0, int((x - 10 - GUTTER) // COL)), min(23, int((x + sw + 10 - GUTTER) // COL)) + 1)
        return min(tops[h] for h in columns)

    spots = range(GUTTER + 10, int(W - sw - 14), 5)
    lowest = max(skyline(x) for x in spots)
    open_spots = [x for x in spots if skyline(x) >= lowest - 1]
    sx = open_spots[len(open_spots) // 2]
    peak = max(range(0, 1200, 5), key=lambda x: min(ridge_h(x + dx, 58, 30, 1.3) for dx in probe))
    dip = min(range(0, 1200, 5), key=lambda x: max(ridge_h(x + dx, 30, 24, 4.1) for dx in (-10, *probe, sw + 10)))
    far_shift, near_shift = sx - peak, sx - dip
    sy = GROUND - min(ridge_h(peak + dx, 58, 30, 1.3) for dx in probe) + 5
    back.append(f'<polygon points="{ridge(58, 30, 1.3, far_shift)}" fill="url(#mt1)"/>')
    if snow_cover:
        back.append(f'<polygon points="{ridge(58, 30, 1.3, far_shift)}" fill="#fff" opacity=".22"/>')
    if sign:
        back.append("".join(f'<rect x="{sx + (i * 6 + 2.1) * spx:.1f}" y="{sy + 6.2 * spx:.1f}" width=".8" height="5" fill="#fff" opacity=".35"/>' for i in range(len(sign))))
        back.append(ptext(sign, sx, sy, round(spx, 3), "#f4f7ff", 'opacity=".92"'))
    back.append(f'<polygon points="{ridge(30, 24, 4.1, near_shift)}" fill="url(#mt2)"/>')
    for i in range(70):
        x, w, hh = i * 14 + rc.uniform(-4, 4), rc.uniform(8, 15), rc.uniform(10, 58)
        if sx - 12 < x < sx + sw + 12:
            hh = min(hh, max(8, GROUND - sy - 22))
        back.append(f'<rect x="{x:.1f}" y="{GROUND - hh:.1f}" width="{w:.1f}" height="{hh:.1f}" fill="url(#far)"/>')
        lights = [(rc.uniform(1.5, w - 3), rc.uniform(4, max(5, hh - 3))) for _ in range(int(hh / 9))]
        if sky.daylight((x - GUTTER) / COL) < .35:
            back.extend(f'<rect x="{x + lx:.1f}" y="{GROUND - ly:.1f}" width="1.4" height="1.6" fill="#ffd98a" opacity=".55"/>' for lx, ly in lights)

    # ---------- clouds ----------
    clouds = []
    for h, kind in enumerate(WX):
        limit = min(84, tops[h] - 14)
        for _ in range({"partly": 1, "cloudy": 2, "rain": 2, "thunder": 3, "snow": 2}.get(kind, 0)):
            s = rs.uniform(.75, 1.05) if kind == "partly" else rs.uniform(.9, 1.35)
            clouds.append((s, X(h) + rs.uniform(4, COL - 4), rs.uniform(46, max(48, limit)), h + .5, kind))
        if kind == "clear" and sky.daylight(h + .5) > .6 and rs.random() < .5:
            mid.append(f'<ellipse cx="{X(h + .5):.1f}" cy="{rs.uniform(30, 70):.0f}" rx="{rs.uniform(24, 40):.0f}" ry="1.5" fill="#fff" opacity=".4" transform="rotate(-5 {X(h + .5):.1f} 50)"/>')
    for s, cx, cy, h, kind in sorted(clouds):
        mid.append(cloud(rs, sky, cx, cy, s, h, kind))

    # ---------- buildings ----------
    night = [h for h in range(24) if sky.daylight(h + .5) < .3 and floors[h] >= 6]
    neon_side = set(rc.sample(night, min(4, len(night))))

    for h in range(24):
        n = floors[h]
        if n == 0:
            continue
        rb = random.Random(f"{login}:{h}")      # each building keeps its look as it grows
        dl, side = sky.daylight(h + .5), 4
        bw = rb.choice([28, 30, 32, 34])
        roof_roll, awning, neon_a, neon_b, antenna = rb.random(), rb.choice(AWNING), rb.choice(NEON), rb.choice(NEON), rb.random() < .5
        if h == tallest:
            bw = 34
        x0 = X(h) + (COL - bw) / 2
        kinds = ["flat", "setback", "spire", "wedge", "dome", "garden", "tank", "billboard"] if n >= 6 else ["flat", "tank", "garden", "wedge"]
        roof = "crane" if h == tallest else kinds[int(roof_roll * len(kinds))]
        base = lerp(lerp((20, 27, 51), (72, 88, 118), dl), (150, 158, 172), dl * sky.cover(h) * .25)
        inset_from = n - 2 if roof == "setback" else n
        years = floor_years(h, n)
        prev, prev_year, glass = None, None, []
        for i, year in enumerate(years):
            e = era(year)
            ins = 3 if i >= inset_from else 0
            fx, fwid = x0 + ins, bw - 2 * ins
            fw, y = fwid - side, GROUND - (i + 1) * FLOOR
            col = add(add(base, ERA_TINT[e]), 8 if year % 2 else 0)   # alternate years differ slightly, like strata
            city.append(f'<rect x="{fx:.1f}" y="{y}" width="{fwid}" height="{FLOOR + .3}" fill="{rgb(col)}"/>'
                        f'<rect x="{fx + fw:.1f}" y="{y}" width="{side}" height="{FLOOR + .3}" fill="#000" opacity=".28"/>')
            if prev is not None and e != prev:          # a new era: heavy cornice
                city.append(f'<rect x="{x0 - 1.5:.1f}" y="{y + FLOOR - 1.2}" width="{bw + 3}" height="2.2" fill="{rgb(add(col, 46))}"/>')
            elif prev_year is not None and year != prev_year:   # a new year: thin ledge, like a growth ring
                city.append(f'<rect x="{fx - 1:.1f}" y="{y + FLOOR - .7}" width="{fwid + 2}" height="1.4" fill="{rgb(add(col, 58))}"/>')
            prev, prev_year = e, year
            unit = (fw - 3) / 4
            ww, wh, wy = [(unit - 2.4, 4.4, y + 2.2), (unit - .4, 4, y + 2.8), (unit - .9, 7.2, y + 1)][e]
            if e == 0:
                city.append(f'<rect x="{fx + 1:.1f}" y="{y + 7}" width="{fw - 2:.1f}" height=".8" fill="#fff" opacity=".13"/>')
            if e == 2:
                glass.append(y)
            for k in range(4):
                lit, roll = rb.random() < .72, rb.random()
                wx = fx + 1.5 + k * unit + (unit - ww) / 2
                if lit:
                    city.append(f'<rect x="{wx:.1f}" y="{wy}" width="{ww:.1f}" height="{wh}" fill="{colors[pick_language(h, year, roll)]}" opacity="{.92 - .12 * dl:.2f}"/>')
                else:
                    city.append(f'<rect x="{wx:.1f}" y="{wy}" width="{ww:.1f}" height="{wh}" fill="#070b1a" opacity=".45"/>')
        if len(glass) >= 3:   # reflection on the glass
            yt, yb, gw = min(glass), max(glass) + FLOOR, bw - side
            city.append(f'<polygon points="{x0 + gw * .12:.1f},{yb} {x0 + gw * .42:.1f},{yb} {x0 + gw * .9:.1f},{yt} {x0 + gw * .6:.1f},{yt}" fill="#fff" opacity=".09"/>')
        if h == tallest:   # the year this tower was founded; the crane above carries the current year
            i = 1 if n > 1 else 0
            pcx, py = x0 + (bw - side) / 2, GROUND - (i + 1) * FLOOR
            city.append(f'<rect x="{pcx - 11.4:.1f}" y="{py + .7:.1f}" width="22.8" height="8" rx="1.2" fill="#0b1022" stroke="#ffe9a8" stroke-opacity=".55" stroke-width=".5"/>'
                        + ptext(str(years[0]), pcx - 9.8, py + 1.8, .85, "#ffe9a8"))
        city.append(f'<rect x="{x0 + 1.5:.1f}" y="{GROUND - FLOOR - 1}" width="{bw - side - 3}" height="1.8" fill="{awning}" opacity=".9"/>'
                    f'<rect x="{x0 + (bw - side) / 2 - 2:.1f}" y="{GROUND - 5.5}" width="4" height="5.5" fill="{"#ffd98a" if dl < .4 else "#1b2238"}"/>')
        # rooftop
        top_y = tops[h]
        rxx, rw = (x0 + 3, bw - 6) if roof == "setback" else (x0, bw)
        cx, lite, snow = rxx + rw / 2, rgb(add(base, 34)), h in snow_cover
        cap = "#f4f8ff" if snow else rgb(add(base, 24))
        city.append(f'<rect x="{rxx - 1.5:.1f}" y="{top_y - 2}" width="{rw + 3}" height="2" fill="{lite}"/>')
        if roof == "crane":   # the tallest tower is still under construction: this year's floors
            city.append(f'<path d="M{x0 + 1},{top_y - 2} v-9 h{bw - 2} v9 M{x0 + 1},{top_y - 11} l{bw - 2},9 M{x0 + bw - 1},{top_y - 11} l-{bw - 2},9" stroke="#f2c14e" stroke-width=".9" fill="none" opacity=".85"/>')
            kx, ky = x0 + 8, top_y - 11
            city.append(f'<path d="M{kx},{ky} V{ky - 28} M{kx - 9},{ky - 24} H{kx + 30} M{kx},{ky - 28} L{kx + 30},{ky - 24} M{kx + 24},{ky - 24} V{ky - 10}" stroke="#f2c14e" stroke-width="1.6" fill="none"/>'
                        f'<rect x="{kx + 21.5}" y="{ky - 10}" width="5" height="4" fill="#f2c14e"/>')
            front.append(f'<circle class="blink" cx="{kx}" cy="{ky - 29}" r="1.3" fill="#ff4d4d"/>')
            city.append(f'<rect x="{x0 + bw / 2 - 11.4:.1f}" y="{top_y - 10.4}" width="22.8" height="7.6" rx="1" fill="#f2c14e"/>' + ptext(str(this_year), x0 + bw / 2 - 9.8, top_y - 9.5, .85, "#1b1400"))
        elif roof == "spire":
            city.append(f'<rect x="{cx - 4:.1f}" y="{top_y - 7}" width="8" height="5" fill="{rgb(add(base, 16))}"/><path d="M{cx:.1f},{top_y - 7} v-17" stroke="{lite}" stroke-width="1.2"/>')
            if dl < .5:
                front.append(f'<circle class="blink" cx="{cx:.1f}" cy="{top_y - 25}" r="1.3" fill="#ff4d4d" style="animation-delay:-{rb.uniform(0, 2):.1f}s"/>')
        elif roof == "wedge":
            city.append(f'<polygon points="{rxx:.1f},{top_y - 2} {rxx + rw:.1f},{top_y - 2} {rxx + rw:.1f},{top_y - 4} {rxx:.1f},{top_y - 11}" fill="{cap}"/>')
        elif roof == "dome":
            city.append(f'<path d="M{cx - 10:.1f},{top_y - 2} A10,8 0 0 1 {cx + 10:.1f},{top_y - 2}Z" fill="{cap}"/><path d="M{cx:.1f},{top_y - 10} v-5" stroke="{lite}" stroke-width="1"/>')
        elif roof == "garden":
            leaf = rgb(lerp(lerp((15, 42, 30), (63, 143, 90), dl), (244, 248, 255), .7 if snow else 0))
            city.append("".join(f'<circle cx="{rxx + q:.1f}" cy="{top_y - 4.5}" r="{r}" fill="{leaf}"/>' for q, r in ((6, 3.2), (12, 4), (rw - 8, 3.4))))
        elif roof == "tank":
            city.append(f'<path d="M{rxx + 6:.1f},{top_y - 2} v-3 m7,3 v-3" stroke="{lite}" stroke-width=".9"/><rect x="{rxx + 4:.1f}" y="{top_y - 11}" width="11" height="6.5" rx="1.5" fill="{rgb(add(base, 18))}"/>')
        elif roof == "billboard":
            city.append(f'<path d="M{cx - 6:.1f},{top_y - 2} v-4 m12,4 v-4" stroke="{lite}" stroke-width=".9"/>')
            front.append(f'<g class="neon" opacity="{1 - dl * .45:.2f}" style="animation-delay:-{rb.uniform(0, 4):.1f}s"><rect x="{cx - 10:.1f}" y="{top_y - 15}" width="20" height="9" rx="1" fill="#0b1022" stroke="{neon_a}" stroke-width="1" filter="url(#glow)"/>'
                         f'<path d="M{cx - 6:.1f},{top_y - 12} h12 M{cx - 6:.1f},{top_y - 9.5} h8" stroke="{neon_a}" stroke-width="1.2" stroke-linecap="round"/></g>')
        elif antenna:
            city.append(f'<path d="M{x0 + bw - 9:.1f},{top_y - 2} v-11 m-3,4 h6" stroke="{lite}" stroke-width="1" fill="none"/>')
        if snow and roof not in ("wedge", "dome", "crane"):
            city.append(f'<rect x="{rxx - 2.5:.1f}" y="{top_y - 4.5}" width="{rw + 5}" height="4" rx="2" fill="#f4f8ff"/>')
        if h in neon_side:
            front.append(f'<rect class="neon" x="{x0 - 3.4:.1f}" y="{top_y + 12}" width="3" height="{min(24, n * FLOOR - 24)}" rx="1" fill="{neon_b}" filter="url(#glow)" style="animation-delay:-{rb.uniform(0, 4):.1f}s"/>')

    # street trees and lamps
    for h in range(25):
        x, dl = X(h), sky.daylight(h)
        if h % 2 == 0:
            leaf = rgb(lerp(lerp((15, 42, 30), (63, 143, 90), dl), (244, 248, 255), .65 if (h in snow_cover or h - 1 in snow_cover) else 0))
            city.append(f'<path d="M{x},{GROUND} v-7" stroke="#3b2a22" stroke-width="1.4"/><circle cx="{x}" cy="{GROUND - 10}" r="4" fill="{leaf}"/><circle cx="{x - 2}" cy="{GROUND - 7}" r="2.8" fill="{leaf}"/>')
        else:
            city.append(f'<path d="M{x},{GROUND} v-15 h2.5" stroke="#59648c" stroke-width="1" fill="none"/>')
            if dl < .45:
                city.append(f'<polygon points="{x + 2.5},{GROUND - 15} {x - 4},{GROUND} {x + 9},{GROUND}" fill="#ffe9a8" opacity=".13"/>'
                            f'<circle cx="{x + 2.5}" cy="{GROUND - 15}" r="1.6" fill="#ffe9a8" filter="url(#glow)"/>')
    for h in sorted(snow_cover):
        city.append(f'<rect x="{X(h)}" y="{GROUND - 2.5}" width="{COL}" height="3.5" rx="1.5" fill="#f4f8ff"/>')

    # ---------- weather in front of the city ----------
    weather = ['<g clip-path="url(#above)">']
    for h, kind in enumerate(WX):
        x0 = X(h)
        if kind in ("rain", "thunder"):
            for _ in range(24 if kind == "rain" else 44):
                x, ln = x0 + rs.uniform(4, COL + 14), rs.uniform(8, 15)
                weather.append(f'<line class="drop" x1="{x:.1f}" y1="82" x2="{x - ln * .22:.1f}" y2="{82 + ln:.1f}" stroke="#d6e6ff" stroke-width="{rs.choice([.7, 1, 1.2])}" opacity="{rs.uniform(.35, .75):.2f}" style="animation-duration:{rs.uniform(.6, .95):.2f}s;animation-delay:-{rs.uniform(0, 1):.2f}s"/>')
            for _ in range(5):
                x, y = x0 + rs.uniform(0, COL), rs.choice([GROUND - 1, tops[h] - 2])
                front.append(f'<ellipse class="splash" cx="{x:.1f}" cy="{y}" rx="3" ry="1" fill="none" stroke="#d6e6ff" stroke-width=".7" style="animation-delay:-{rs.uniform(0, 1):.2f}s"/>')
        if kind == "thunder":
            bx = x0 + 14
            weather.append(f'<ellipse class="flash" cx="{bx}" cy="76" rx="85" ry="52" fill="#fff" filter="url(#soft)"/>'
                           f'<polyline class="bolt" points="{bx},70 {bx - 7},96 {bx + 2},98 {bx - 9},128 {bx - 2},130 {bx - 12},158" fill="none" stroke="#fff8c9" stroke-width="2" stroke-linejoin="round" filter="url(#glow)"/>')
        if kind == "snow":
            for _ in range(26):
                x = x0 + rs.uniform(-4, COL + 4)
                weather.append(f'<circle class="flake" cx="{x:.1f}" cy="-4" r="{rs.choice([.8, 1, 1.2, 1.6, 2])}" fill="#fff" opacity="{rs.uniform(.55, .95):.2f}" style="animation-duration:{rs.uniform(6, 11):.1f}s;animation-delay:-{rs.uniform(0, 11):.1f}s"/>')
        if kind == "fog":
            for _ in range(3):
                weather.append(f'<ellipse class="fog" cx="{x0 + rs.uniform(0, COL):.0f}" cy="{GROUND - rs.uniform(14, 120):.0f}" rx="{rs.uniform(55, 85):.0f}" ry="{rs.uniform(7, 12):.0f}" fill="#eef2f8" opacity=".34" filter="url(#soft)" style="animation-delay:-{rs.uniform(0, 20):.0f}s"/>')
    weather.append('</g>')

    # ---------- ticker ----------
    busiest = f"{tallest:02d}:00"
    top_lang = f"   TOP LANG {dot_text(shares[0][0])} {round(shares[0][1] * 100)}%" if shares and shares[0][0] != OTHER else ""
    years_active = this_year - since
    parts = [f"SINCE {since}"] + ([plural(years_active, "YEAR")] if years_active >= 1 else []) + [plural(d["total_commits"], "COMMIT")]
    ticker = ("   ".join(parts) + "   ///   "
              + f"TODAY {day:%m/%d} {day:%a}".upper() + f"   THIS WEEK {plural(d['week_commits'], 'COMMIT')}   THIS MONTH {plural(d['month_commits'], 'COMMIT')}   ///   "
              + f"BUSIEST HOUR {busiest}{top_lang}   LONGEST STREAK {plural(d['longest_streak'], 'DAY')}   ///   ")
    tick_px = 1.5
    tick_len = len(ticker) * 6 * tick_px

    # ---------- assemble ----------
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" width="{W}" height="{height}" role="img" aria-label="A city skyline drawn from {login}&#39;s commit history" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">',
         f'<title>{login}: commits by hour of day, drawn as a city</title>',
         STYLE.replace("TICKDUR", f"{tick_len / 34:.1f}").replace("TICKLEN", f"{tick_len:.1f}"), '<defs>']
    for ch, rows in FONT.items():
        path = "".join(f"M{c},{r}h.82v.82h-.82z" for r, row in enumerate(rows.split()) for c, bit in enumerate(row) if bit == "1")
        o.append(f'<path id="g{ord(ch)}" d="{path}"/>')
    o.append(hgrad("zenith", lambda h: sky.color(h, 0)))
    o.append(hgrad("horizon", lambda h: sky.color(h, 1)))
    o.append(hgrad("overcast", lambda h: lerp(lerp((22, 27, 48), (150, 158, 172), sky.daylight(h)), (190, 198, 212), .5 if sky.kind(h) == "snow" else 0),
                   opacity=lambda h: .78 * (sky.cover(h - .5) + sky.cover(h + .5)) / 2))
    o.append(hgrad("mt1", sky.timed((16, 23, 54), (132, 164, 204), (150, 110, 150))))
    o.append(hgrad("mt2", sky.timed((11, 17, 44), (100, 136, 178), (108, 78, 124))))
    o.append(hgrad("far", sky.timed((12, 18, 46), (118, 148, 186), (118, 88, 130))))
    o.append('<linearGradient id="hmg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#000"/><stop offset=".35" stop-color="#262626"/>'
             '<stop offset=".75" stop-color="#909090"/><stop offset="1" stop-color="#fff"/></linearGradient>'
             f'<mask id="hm"><rect width="{W}" height="{GROUND}" fill="url(#hmg)"/></mask>'
             '<radialGradient id="dawn"><stop offset="0" stop-color="#fff0c2" stop-opacity=".95"/><stop offset=".4" stop-color="#ffb26b" stop-opacity=".55"/><stop offset="1" stop-color="#f08a5d" stop-opacity="0"/></radialGradient>'
             '<radialGradient id="dusk"><stop offset="0" stop-color="#ffe2b0" stop-opacity=".95"/><stop offset=".4" stop-color="#ff8a5c" stop-opacity=".55"/><stop offset="1" stop-color="#c0507a" stop-opacity="0"/></radialGradient>'
             '<radialGradient id="sunhalo"><stop offset="0" stop-color="#fff8d6" stop-opacity=".75"/><stop offset=".4" stop-color="#fff3b0" stop-opacity=".22"/><stop offset="1" stop-color="#fff3b0" stop-opacity="0"/></radialGradient>'
             '<radialGradient id="moonhalo"><stop offset="0" stop-color="#dfe6ff" stop-opacity=".4"/><stop offset=".5" stop-color="#c9d3ff" stop-opacity=".1"/><stop offset="1" stop-color="#c9d3ff" stop-opacity="0"/></radialGradient>'
             '<linearGradient id="deep" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#0a1230" stop-opacity=".25"/><stop offset="1" stop-color="#050818" stop-opacity=".8"/></linearGradient>'
             '<pattern id="dots" width="1.5" height="1.5" patternUnits="userSpaceOnUse"><rect width="1.2" height="1.2" fill="#ffb000" opacity=".07"/></pattern>'
             '<filter id="glow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
             '<filter id="soft" x="-30%" y="-60%" width="160%" height="220%"><feGaussianBlur stdDeviation="6"/></filter>'
             '<filter id="ripple" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.009 0.24" numOctaves="2" seed="4" result="n"/>'
             '<feDisplacementMap in="SourceGraphic" in2="n" scale="9" xChannelSelector="R" yChannelSelector="G"/><feGaussianBlur stdDeviation="0.5 0.9"/></filter>'
             f'<clipPath id="frame"><rect width="{W}" height="{height}" rx="14"/></clipPath>'
             f'<clipPath id="above"><rect width="{W}" height="{GROUND}"/></clipPath>'
             f'<clipPath id="water"><rect y="{WATER_TOP}" width="{W}" height="{WATER_BOTTOM - WATER_TOP}"/></clipPath>'
             f'<clipPath id="led"><rect x="16" y="{WATER_BOTTOM + 8}" width="{W - 32}" height="17" rx="3"/></clipPath></defs>')
    o.append('<g clip-path="url(#frame)">')
    o.append('<g id="back">' + "".join(back) + '</g>')
    o.append("".join(mid))
    o.append('<g id="city">' + "".join(city) + '</g>')
    o.append("".join(front))
    o.append("".join(weather))

    # ruler in the left gutter: building height is the number of commits
    minor = major / 5
    o.append(f'<rect x="{GUTTER - 2}" y="{GROUND - top * pxc:.1f}" width=".8" height="{top * pxc:.1f}" fill="#c9cfea" opacity=".35"/>')
    for i in range(1, int(top * 1.02 / minor) + 1):
        y, is_major = GROUND - i * minor * pxc, i % 5 == 0
        o.append(f'<rect x="{GUTTER - (8 if is_major else 5)}" y="{y - .4:.1f}" width="{6 if is_major else 3}" height=".8" fill="#c9cfea" opacity="{.95 if is_major else .55}"/>')
        if is_major:
            o.append(f'<text x="{GUTTER - 10}" y="{y + 2.5:.1f}" font-family="{MONO}" font-size="7" fill="#c9cfea" text-anchor="end">{round(i * minor):,}</text>')
    o.append(f'<text transform="translate(9,{GROUND - major * pxc / 2:.1f}) rotate(-90)" font-family="{MONO}" font-size="7" letter-spacing=".6" fill="#8b93b8" text-anchor="middle">commits</text>')

    # quay, train and the hour axis
    o.append(f'<rect y="{GROUND}" width="{W}" height="14" fill="#0b1022"/><rect y="{GROUND}" width="{W}" height="1.4" fill="#39436b"/>')
    o.append(f'<g class="train"><rect x="0" y="{GROUND - 8}" width="62" height="7" rx="2" fill="#dfe6f5"/>'
             + "".join(f'<rect x="{4 + i * 7}" y="{GROUND - 6}" width="4" height="3" fill="#ffd166"/>' for i in range(8)) + '</g>')
    for h in range(24):
        o.append(f'<rect x="{X(h + .5) - .4:.1f}" y="{GROUND + 1.4}" width=".8" height="{2.6 if h % 3 == 0 else 1.4}" fill="#59648c"/>')
        if h % 3 == 0:
            o.append(f'<text x="{X(h + .5):.1f}" y="{GROUND + 11.4}" font-family="{MONO}" font-size="7" letter-spacing=".6" fill="#8b93b8" text-anchor="middle">{h:02d}:00</text>')

    # water with the city reflected in it
    k = (WATER_BOTTOM - WATER_TOP) / MAX_HEIGHT
    o.append(f'<g clip-path="url(#water)"><rect y="{WATER_TOP}" width="{W}" height="{WATER_BOTTOM - WATER_TOP}" fill="#0a1230"/>'
             f'<g filter="url(#ripple)"><g transform="translate(0,{WATER_TOP + GROUND * k:.1f}) scale(1,{-k:.3f})" opacity=".8"><use href="#back"/><use href="#city"/></g></g>'
             f'<rect y="{WATER_TOP}" width="{W}" height="{WATER_BOTTOM - WATER_TOP}" fill="url(#deep)"/>')
    for _ in range(34):
        x, y = rs.uniform(0, W), rs.uniform(WATER_TOP + 4, WATER_BOTTOM - 3)
        o.append(f'<rect class="shim" x="{x:.0f}" y="{y:.1f}" width="{rs.uniform(6, 18):.0f}" height=".7" rx=".35" fill="#fff" opacity=".15" style="animation-delay:-{rs.uniform(0, 5):.1f}s"/>')
    for h, kind in enumerate(WX):
        if kind in ("rain", "thunder"):
            for _ in range(7):
                o.append(f'<ellipse class="ripple" cx="{X(h) + rs.uniform(0, COL):.0f}" cy="{rs.uniform(WATER_TOP + 6, WATER_BOTTOM - 6):.0f}" rx="6" ry="1.6" fill="none" stroke="#d6e6ff" stroke-width=".6" style="animation-delay:-{rs.uniform(0, 1.6):.2f}s"/>')
    o.append('</g>')

    # ---------- bottom panel: ticker and languages ----------
    P = WATER_BOTTOM
    o.append(f'<rect y="{P}" width="{W}" height="{height - P}" fill="#070a18"/>')
    o.append(f'<rect x="16" y="{P + 8}" width="{W - 32}" height="17" rx="3" fill="#04060d" stroke="#1c2340"/><rect x="16" y="{P + 8}" width="{W - 32}" height="17" rx="3" fill="url(#dots)"/>')
    o.append('<g clip-path="url(#led)"><g class="ticker">' + ptext(ticker * max(2, math.ceil(2 * (W - 32) / tick_len) + 1), 22, P + 11.3, tick_px, "#ffb319") + '</g></g>')
    if shares:   # language share as one floor of windows
        cells = 92
        raw = [(name, share * cells) for name, share in shares]
        count = {name: int(v) for name, v in raw}
        for name, v in sorted(raw, key=lambda t: t[1] - int(t[1]), reverse=True)[:cells - sum(count.values())]:
            count[name] += 1
        o.append(f'<rect x="14" y="{P + 33}" width="932" height="11.5" rx="2" fill="#171e3c"/><rect x="12.5" y="{P + 32}" width="935" height="1.6" rx=".8" fill="#39436b"/>')
        i = 0
        for name, _ in shares:
            for _ in range(count[name]):
                o.append(f'<rect x="{17 + i * 10}" y="{P + 35.8}" width="8" height="6" rx="1" fill="{colors[name]}"/>')
                i += 1
        for r, entries in enumerate(legend):
            full = r < len(legend) - 1 or len(legend) == 1
            spare = W - 32 - sum(w for _, _, w in entries)
            gap = min(spare / (len(entries) - 1), 60) if full and len(entries) > 1 else 14
            x, y = 16.0, P + 49.5 + r * 14
            for name, pct, width in entries:
                label = name.replace("&", "&amp;").replace("<", "&lt;")
                o.append(f'<rect x="{x:.1f}" y="{y}" width="6" height="6" rx="1.5" fill="{colors[name]}"/>'
                         f'<text x="{x + 9.5:.1f}" y="{y + 5.8}" font-size="9" fill="#c9cfea">{label} <tspan font-family="{MONO}" font-size="8" fill="#7e87ad">{pct}%</tspan></text>')
                x += width + gap
    o.append('</g></svg>')
    return "\n".join(o)
