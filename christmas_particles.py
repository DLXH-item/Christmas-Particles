#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
圣诞快乐 · 粒子炫酷版 v2

开场粒子拼出「圣诞快乐」→ 粒子爆散 → 汇聚成 3D 自转粒子圣诞树（发光粒子彩带缠绕）
→ 雪夜粒子场景 + 粒子烟花。音乐为程序内部重新编曲的《Jingle Bells》。

交互：
    鼠标移动        粒子避让光标
    点击 / 拖动     粒子烟花（点击可跳过开场）
    空格            音乐开关        ↑ / ↓  音量
    C               切换灯光配色     F     烟花
    R               重播             S     截图
    H               显示/隐藏提示    ESC   退出
"""

import os
import sys
import math
import random
import wave
import tempfile
import time
from array import array

TAU = math.tau

try:
    import pygame
except ImportError:
    print("首次运行，正在自动安装 pygame（约 10 秒）…")
    import subprocess
    ok = False
    for extra in (["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"], []):
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pygame",
                                   "--disable-pip-version-check", "--quiet"] + extra)
            ok = True
            break
        except Exception:
            continue
    if not ok:
        print("自动安装失败，请手动执行:  pip install pygame")
        input("按回车退出…")
        sys.exit(1)
    import pygame

VW, VH = 1200, 800
CX, CY = 600, 400
if getattr(sys, "frozen", False):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- 工具
def lerp(a, b, t):
    return a + (b - a) * t


def smooth(x):
    x = 0.0 if x < 0 else (1.0 if x > 1 else x)
    return x * x * (3 - 2 * x)


def load_font(size):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\Deng.ttf",
              r"C:\Windows\Fonts\simsun.ttc"):
        if os.path.exists(p):
            try:
                return pygame.font.Font(p, size)
            except Exception:
                pass
    return pygame.font.SysFont("microsoftyahei,simhei,arial", size)


# ---------------------------------------------------------------- 音乐合成
SR = 22050
NTAB = 2048
SIN = [math.sin(i * TAU / NTAB) for i in range(NTAB)]


def _freq(name):
    tbl = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
    midi = 12 * (int(name[1:]) + 1) + tbl[name[0]]
    return 440.0 * 2 ** ((midi - 69) / 12.0)


# 16 小节《Jingle Bells》，每小节 4 拍
BARS = [
    [("E4", 1), ("E4", 1), ("E4", 1), ("R", 1)],
    [("E4", 1), ("E4", 1), ("E4", 1), ("R", 1)],
    [("E4", 1), ("G4", 1), ("C5", 1), ("D5", 1)],
    [("E5", 3), ("R", 1)],
    [("F5", 1), ("F5", 1), ("E5", 1), ("D5", 1)],
    [("D5", 1), ("E5", 1), ("D5", 2)],
    [("G5", 1), ("G5", 1), ("F5", 1), ("D5", 1)],
    [("E5", 3), ("R", 1)],
    [("E4", 1), ("E4", 1), ("E4", 1), ("R", 1)],
    [("E4", 1), ("E4", 1), ("E4", 1), ("R", 1)],
    [("E4", 1), ("G4", 1), ("C5", 1), ("D5", 1)],
    [("E5", 3), ("R", 1)],
    [("F5", 1), ("F5", 1), ("E5", 1), ("D5", 1)],
    [("D5", 1), ("E5", 1), ("D5", 2)],
    [("G5", 1), ("G5", 1), ("F5", 1), ("D5", 1)],
    [("C5", 3), ("R", 1)],
]
CHORDS = ["C", "C", "C", "C", "F", "G", "G", "C",
          "C", "C", "C", "C", "F", "G", "G", "C"]
CHORD_TONES = {
    "C": [("C4", 1), ("E4", 1), ("G4", 1), ("E4", -1)],
    "F": [("F4", 1), ("A4", 1), ("C5", 1), ("A4", -1)],
    "G": [("G4", 1), ("B4", 1), ("D5", 1), ("B4", -1)],
}
CHORD_ROOT = {"C": "C3", "F": "F3", "G": "G3"}


def _bell(buf, i0, ns, freq, gain, decay=7.2):
    step = freq / SR * NTAB
    ph = 0.0
    pm = 0.20 * NTAB
    for i in range(ns):
        t = i / SR
        env = math.exp(-decay * t)
        if i < 26:
            env *= i / 26.0
        m = SIN[int(ph * 2) % NTAB]
        v = SIN[int(ph + pm * env * m) % NTAB]
        if t < 0.10:
            v += 0.34 * SIN[int(ph * 3) % NTAB] * math.exp(-16.0 * t)
        buf[i0 + i] += v * env * gain
        ph += step


def _soft(buf, i0, ns, freq, gain, decay=2.2, attack=0.06):
    step = freq / SR * NTAB
    ph = 0.0
    at = attack * SR
    for i in range(ns):
        t = i / SR
        env = math.exp(-decay * t) * (i / at if i < at else 1.0)
        buf[i0 + i] += SIN[int(ph) % NTAB] * env * gain
        ph += step


def build_music(path, sr=SR, beat=0.44):
    nb = len(BARS)
    total = nb * 4 * beat
    n = int(total * sr) + sr // 3
    buf = [0.0] * n
    bar_len = 4 * beat

    for b in range(nb):
        t0 = b * bar_len
        # ---- 铃铛主旋律
        beatpos = 0.0
        for note, beats in BARS[b]:
            if note != "R":
                i0 = int((t0 + beatpos * beat) * sr)
                f = _freq(note)
                ns = min(int(0.62 * sr), n - i0)
                if ns > 100:
                    _bell(buf, i0, ns, f, 0.58, 6.6)
            beatpos += beats
        # ---- 和弦琶音铺底
        ch = CHORDS[b]
        tones = CHORD_TONES[ch]
        for k in range(8):
            tone, _d = tones[k % 4]
            f = _freq(tone) * (0.86 if k % 2 else 1.0)
            i0 = int((t0 + k * beat / 2.0) * sr)
            ns = min(int(0.26 * sr), n - i0)
            if ns > 100:
                _soft(buf, i0, ns, f, 0.16, 3.4, 0.05)
        # ---- 和弦长音铺底（温暖）
        for tone, _d in tones[:3]:
            f = _freq(tone)
            i0 = int(t0 * sr)
            ns = min(int(0.94 * sr), n - i0)
            if ns > 100:
                _soft(buf, i0, ns, f, 0.105, 0.95, 0.12)
        # ---- 低音：根音 + 五度
        f = _freq(CHORD_ROOT[ch])
        i0 = int(t0 * sr)
        ns = min(int(0.85 * sr), n - i0)
        if ns > 100:
            _soft(buf, i0, ns, f, 0.17, 1.5, 0.08)
        i1 = int((t0 + 2 * beat) * sr)
        ns = min(int(0.60 * sr), n - i1)
        if ns > 100:
            _soft(buf, i1, ns, f * 1.4983, 0.12, 1.9, 0.08)
        # ---- 雪橇铃（每拍小噪声铃）
        for k in range(4):
            i0 = int((t0 + k * beat + beat * 0.5) * sr)
            ns = min(int(0.07 * sr), n - i0)
            if ns <= 10:
                continue
            ph1 = 0.0
            ph2 = 0.0
            s1 = 2350.0 / sr * NTAB
            s2 = 3300.0 / sr * NTAB
            for i in range(ns):
                t = i / sr
                env = math.exp(-42.0 * t)
                noise = random.uniform(-1, 1) * 0.34
                buf[i0 + i] += (noise + 0.55 * SIN[int(ph1) % NTAB]
                                + 0.4 * SIN[int(ph2) % NTAB]) * env * 0.03
                ph1 += s1
                ph2 += s2
        # ---- 高音闪烁
        if b % 4 == 0:
            i0 = int(t0 * sr)
            ns = min(int(0.9 * sr), n - i0)
            if ns > 100:
                _bell(buf, i0, ns, _freq("C6"), 0.16, 5.0)

    # ---- 多抽头混响
    for d, g in ((0.055, 0.45), (0.12, 0.32), (0.21, 0.22), (0.31, 0.14)):
        off = int(d * sr)
        for i in range(n - 1, off - 1, -1):
            buf[i] += g * buf[i - off]

    peak = max(abs(v) for v in buf) or 1.0
    sc = 0.88 / peak
    # 伪立体声：右声道轻微延迟，听感更温暖
    off = int(0.011 * sr)
    out = array('h', bytes(n * 4))
    for i in range(n):
        l = buf[i]
        r = buf[i - off] * 0.96 if i >= off else buf[i] * 0.96
        out[2 * i] = int(max(-1.0, min(1.0, l * sc)) * 32000)
        out[2 * i + 1] = int(max(-1.0, min(1.0, r * sc)) * 32000)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(out.tobytes())
    return path


def build_chime(path, f=1480.0, sr=SR):
    n = int(0.5 * sr)
    out = array('h')
    for i in range(n):
        t = i / sr
        env = math.exp(-9.0 * t) * min(1.0, t / 0.005)
        v = env * (0.66 * math.sin(TAU * f * t) + 0.26 * math.sin(TAU * 2.01 * f * t)
                   + 0.12 * math.sin(TAU * 3.02 * f * t))
        out.append(int(max(-1.0, min(1.0, v)) * 30000))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(out.tobytes())
    return path


# ---------------------------------------------------------------- 配色
BASE_COLORS = [
    (255, 255, 255),   # 0 白
    (255, 205, 120),   # 1 金
    (255, 92, 92),     # 2 红
    (92, 220, 130),    # 3 绿
    (110, 170, 255),   # 4 蓝
    (255, 140, 210),   # 5 粉
    (196, 138, 96),    # 6 木
    (150, 205, 255),   # 7 冰蓝
    (176, 244, 196),   # 8 浅绿
    (255, 168, 80),    # 9 橙
]
# 主题色板：0 枝叶主色 1 枝叶副色/星 2 雪白 3 彩带/主灯 4 次灯/烟花 5 点缀
PALETTES = [
    ("霓虹", [(70, 236, 160), (255, 214, 96), (232, 255, 244),
              (255, 78, 104), (96, 176, 255), (255, 110, 226)]),
    ("冰蓝", [(120, 196, 255), (215, 240, 255), (245, 252, 255),
              (92, 224, 232), (150, 190, 255), (200, 160, 255)]),
    ("暖金", [(255, 176, 92), (255, 226, 150), (255, 248, 226),
              (255, 128, 62), (255, 206, 120), (255, 96, 80)]),
    ("圣诞红", [(64, 202, 120), (250, 236, 210), (255, 255, 255),
               (255, 72, 72), (255, 168, 72), (150, 244, 190)]),
]
MAXC = 16
COLORS = list(BASE_COLORS) + list(PALETTES[0][1])

SPR_ADD = [None] * (MAXC * 5 * 4)
SPR_NRM = [None] * (MAXC * 5 * 4)
TIERS = (0.24, 0.46, 0.72, 1.0)


def build_sprites():
    for ci in range(MAXC):
        col = COLORS[ci]
        for sz in range(1, 5):
            for tier in range(4):
                g = TIERS[tier]
                idx = ((ci * 5 + sz) * 4 + tier)
                r = sz * 2

                s = pygame.Surface((r * 2, r * 2))
                for rr in range(r, 0, -1):
                    f = g * (1.0 - rr / (r + 0.55)) ** 2.0
                    pygame.draw.circle(s, (min(255, int(col[0] * f)),
                                           min(255, int(col[1] * f)),
                                           min(255, int(col[2] * f))), (r, r), rr)
                c2 = (min(255, int(col[0] * g * 1.5 + 26)),
                      min(255, int(col[1] * g * 1.5 + 26)),
                      min(255, int(col[2] * g * 1.5 + 26)))
                pygame.draw.circle(s, c2, (r, r), max(1, sz - 1))
                SPR_ADD[idx] = s

                t = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                for rr in range(r, 0, -1):
                    a = int(255 * min(1.0, g * (1.0 - rr / (r + 0.55)) ** 1.7))
                    pygame.draw.circle(t, (col[0], col[1], col[2], a), (r, r), rr)
                ta = int(min(255, 255 * g))
                t2 = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(t2, (min(255, col[0] + 40), min(255, col[1] + 40),
                                        min(255, col[2] + 40), ta), (r, r), max(1, sz - 1))
                t.blit(t2, (0, 0))
                SPR_NRM[idx] = t


def apply_palette(i):
    STATE["pal"] = i
    COLORS[10:16] = list(PALETTES[i][1])
    build_sprites()
    if STATIC_PTS:
        rebuild_scene_surf()
    if P2:
        build_text_glow()
    build_hud()


# ---------------------------------------------------------------- 场景常量
TREE_TOP_R = -252.0    # 树顶相对屏幕中心的高度
TREE_BOT_R = 248.0     # 树底
TREE_RAD = 232.0       # 底部半径
FZ = 1020.0
ROT_SPEED = 0.62

G_DUST, G_GROUND, G_MOON, G_HOUSE, G_SNOW, G_GIFT, G_TEXT = range(7)
G_TREE, G_RIBBON, G_STAR = range(3)

P2 = []
SCENE_SURF = None
SCENE_BASE = None
STATIC_PTS = []
P3 = []
FLAKE = []
SPARK = []
ROCKET = []
BUCKETS = [[] for _ in range(8)]
BG = None
HUD = None
HUD_ON = HUD_OFF = None
FW_ON = FW_OFF = None
FONT_S = None
CHIME = None
MUSIC_OK = False
TOAST_CACHE = {}

STATE = dict(t=0.0, stage=0, pal=0, music=True, help=True, vol=0.7,
             toast="", toast_t=0.0, fade_text=1.0, fade_scene=0.0,
             shots=0, next_fw=0.0, rot=0.0, auto_fw=True)


# ---------------------------------------------------------------- 2D 点云
def out_rect(x, y, w, h, ci, step=4):
    pts = []
    for i in range(0, int(w) + 1, max(1, int(step))):
        pts.append((x + i, y, ci))
        pts.append((x + i, y + h, ci))
    for j in range(0, int(h) + 1, max(1, int(step))):
        pts.append((x, y + j, ci))
        pts.append((x + w, y + j, ci))
    return pts


def out_circle(cx, cy, r, ci, n=64):
    return [(cx + math.cos(a) * r, cy + math.sin(a) * r, ci)
            for a in (i * TAU / n for i in range(n))]


def fill_circle(cx, cy, r, ci, gap=3.5):
    pts = []
    step = gap
    y = -r
    while y <= r:
        x = -r
        while x <= r:
            if x * x + y * y <= r * r:
                pts.append((cx + x, cy + y, ci))
            x += step
        y += step
    return pts


def fill_rect(x, y, w, h, ci, gap=4.0):
    pts = []
    yy = y
    while yy <= y + h:
        xx = x
        while xx <= x + w:
            pts.append((xx, yy, ci))
            xx += gap
        yy += gap
    return pts


def fill_tri(p1, p2, p3, ci, gap=4.5):
    pts = []
    minx = min(p1[0], p2[0], p3[0])
    maxx = max(p1[0], p2[0], p3[0])
    miny = min(p1[1], p2[1], p3[1])
    maxy = max(p1[1], p2[1], p3[1])

    def sign(ax, ay, bx, by, px, py):
        return (bx - ax) * (py - ay) - (by - ay) * (px - ax)

    y = miny
    while y <= maxy:
        x = minx
        while x <= maxx:
            d1 = sign(*p1, *p2, x, y)
            d2 = sign(*p2, *p3, x, y)
            d3 = sign(*p3, *p1, x, y)
            if (d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0):
                pts.append((x, y, ci))
            x += gap
        y += gap
    return pts


def sample_text(text, size, cy, want, main_ci=0, alt_ci=1):
    font = load_font(size)
    surf = font.render(text, True, (255, 255, 255))
    w, h = surf.get_size()
    bx, by = (VW - w) / 2, cy - h / 2
    core, edge = [], []
    for y in range(h):
        for x in range(w):
            if surf.get_at((x, y)).a > 60:
                core.append((x, y))
                if (x < 1 or y < 1 or x >= w - 1 or y >= h - 1
                        or not surf.get_at((x + 1, y)).a
                        or not surf.get_at((x - 1, y)).a
                        or not surf.get_at((x, y + 1)).a
                        or not surf.get_at((x, y - 1)).a):
                    edge.append((x, y))
    pts = []
    if core:
        random.shuffle(core)
        random.shuffle(edge)
        n_edge = min(len(edge), int(want * 0.30))
        for x, y in edge[:n_edge]:
            pts.append([bx + x, by + y, main_ci if random.random() < 0.72 else alt_ci,
                        3 if random.random() < 0.55 else 2])
        rest = want - len(pts)
        for x, y in core[:rest]:
            pts.append([bx + x, by + y, main_ci if random.random() < 0.68 else alt_ci,
                        3 if random.random() < 0.45 else 2])
        # 不够则补充抖动点，保证笔画有厚度
        if len(pts) < want:
            picks = (edge + core) or []
            while len(pts) < want and picks:
                x, y = random.choice(picks)
                pts.append([bx + x + random.uniform(-1.4, 1.4),
                            by + y + random.uniform(-1.4, 1.4),
                            main_ci if random.random() < 0.7 else alt_ci, 2])
    return pts


def snow_top(x):
    return 676 + 15 * math.sin(x / 96.0) + 7 * math.sin(x / 37.0 + 1.3)


def soft_disc(cx, cy, r, col, peak=210, power=2.0):
    s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
    for rr in range(r, 0, -1):
        a = int(peak * (1.0 - rr / float(r)) ** power)
        pygame.draw.circle(s, (col[0], col[1], col[2], a), (r, r), rr)
    return s, (cx - r, cy - r)


def build_scene():
    global P2, SCENE_BASE
    P2 = []
    SCENE_BASE = pygame.Surface((VW, VH), pygame.SRCALPHA)
    random.seed(20241225)

    # ---- 烘焙：雪地底色 + 月亮光晕
    if SCENE_BASE is not None:
        band = pygame.Surface((VW, VH), pygame.SRCALPHA)
        for x in range(VW):
            top = int(snow_top(x)) - 2
            for y in range(top, VH):
                f = min(1.0, (y - top) / 150.0)
                pygame.draw.line(band, (int(30 + 16 * f), int(42 + 18 * f),
                                        int(78 + 20 * f), 255), (x, y), (x, y))
        band.set_alpha(150)
        SCENE_BASE.blit(band, (0, 0))
        # 雪地边缘一圈柔光
        edge = pygame.Surface((VW, 90), pygame.SRCALPHA)
        for x in range(VW):
            top = snow_top(x)
            for k in range(0, 26):
                a = int(70 * (1 - k / 26.0) ** 1.6)
                pygame.draw.line(edge, (198, 222, 255, a), (x, top - 46 + k),
                                 (x, top - 45 + k))
        SCENE_BASE.blit(edge, (0, 0))
        s, pos = soft_disc(1012, 138, 118, (150, 190, 255), 120, 1.5)
        SCENE_BASE.blit(s, pos)
        s, pos = soft_disc(1012, 138, 44, (236, 246, 255), 235, 1.2)
        SCENE_BASE.blit(s, pos)

    def add(pts, grp, sz=2):
        for x, y, ci in pts:
            jx = random.uniform(-1.5, 1.5)
            jy = random.uniform(-1.5, 1.5)
            P2.append([x + jx, y + jy, random.uniform(-22, 22), random.uniform(-22, 22),
                       x + jx, y + jy, ci, sz, random.uniform(0, TAU), grp])

    # 雪地闪光（稀疏，避免糊成白带）
    g = []
    for x in range(0, VW, 13):
        top = snow_top(x)
        for y in range(int(top) + 4, 800, 11):
            if random.random() < 0.34:
                g.append((x + random.uniform(-4, 4), y, 7 if random.random() < 0.72 else 0))
    add(g, G_GROUND, 1)

    # 月亮：只留稀疏闪烁点，主体已烘焙
    moon = out_circle(1012, 138, 41, 0, 66)
    for _ in range(120):
        a = random.uniform(0, TAU)
        rr = 36 * random.random() ** 0.5
        moon.append((1012 + math.cos(a) * rr, 138 + math.sin(a) * rr, 0))
    add(moon, G_MOON, 1)

    # 房子
    hx, hy, hw, hh = 925, 520, 160, 168
    house = fill_rect(hx, hy, hw, hh, 6, 5.4) + out_rect(hx, hy, hw, hh, 6, 2.6)
    house += fill_tri((hx - 16, hy), (hx + hw + 16, hy), (hx + hw / 2, hy - 70), 2, 5.2)
    house += [(x, y, 0) for x, y, _c in fill_tri((hx - 16, hy), (hx + hw + 16, hy),
                                                 (hx + hw / 2, hy - 70), 0, 13)]
    # 屋顶积雪
    for i in range(0, 70):
        t = i / 69.0
        house.append((lerp(hx - 16, hx + hw / 2, t), lerp(hy - 2, hy - 70, t) - 2, 0))
        house.append((lerp(hx + hw + 16, hx + hw / 2, t), lerp(hy - 2, hy - 70, t) - 2, 0))
    # 窗（暖光）与门
    for wx in (hx + 22, hx + hw - 58):
        house += fill_rect(wx, hy + 32, 36, 40, 1, 4.4) + out_rect(wx, hy + 32, 36, 40, 1, 2.6)
    house += fill_rect(hx + hw / 2 - 20, hy + hh - 58, 40, 58, 2, 5.0)
    house += [(x, y, 2) for x, y, _ in out_rect(hx + hw / 2 - 20, hy + hh - 58, 40, 58, 2, 3)]
    house += fill_rect(hx + 56, hy - 92, 24, 38, 6, 4.4)   # 烟囱
    house += [(x, y, 6) for x, y, _ in out_rect(hx + 56, hy - 92, 24, 38, 6, 3)]
    if SCENE_BASE is not None:
        ov = pygame.Surface((VW, VH), pygame.SRCALPHA)
        pygame.draw.rect(ov, (48, 22, 26, 205), (hx, hy, hw, hh))
        pygame.draw.polygon(ov, (16, 8, 10, 205),
                            [(hx + hw / 2 - 20, hy + hh - 58), (hx + hw / 2 + 20, hy + hh - 58),
                             (hx + hw / 2 + 20, hy + hh), (hx + hw / 2 - 20, hy + hh)])
        pygame.draw.polygon(ov, (72, 26, 24, 215),
                            [(hx - 16, hy), (hx + hw + 16, hy), (hx + hw / 2, hy - 70)])
        pygame.draw.line(ov, (226, 240, 255, 205), (hx - 16, hy), (hx + hw / 2, hy - 70), 5)
        pygame.draw.line(ov, (226, 240, 255, 205), (hx + hw + 16, hy), (hx + hw / 2, hy - 70), 5)
        pygame.draw.rect(ov, (58, 30, 26, 210), (hx + 56, hy - 92, 24, 38))
        pygame.draw.line(ov, (226, 240, 255, 190),
                         (hx + 55, hy - 92), (hx + 81, hy - 92), 4)
        SCENE_BASE.blit(ov, (0, 0))
    add(house, G_HOUSE, 2)

    # 雪人
    sx, sy = 178, 648
    if SCENE_BASE is not None:
        ov = pygame.Surface((VW, VH), pygame.SRCALPHA)
        for cx, cy, rr in ((sx, sy, 50), (sx, sy - 60, 35), (sx, sy - 106, 25)):
            s, pos = soft_disc(cx, cy + 4, rr + 5, (228, 240, 255), 150, 1.1)
            ov.blit(s, pos)
        pygame.draw.circle(ov, (238, 246, 255, 165), (sx, sy - 106), 24)
        pygame.draw.rect(ov, (22, 14, 16, 210), (sx - 30, sy - 132, 60, 12))
        pygame.draw.rect(ov, (26, 16, 18, 210), (sx - 20, sy - 162, 40, 32))
        SCENE_BASE.blit(ov, (0, 0))
    snow = (fill_circle(sx, sy, 50, 0, 4.2) + out_circle(sx, sy, 50, 7, 74)
            + fill_circle(sx, sy - 60, 35, 0, 4.2) + out_circle(sx, sy - 60, 35, 7, 62)
            + fill_circle(sx, sy - 106, 25, 0, 4.0) + out_circle(sx, sy - 106, 25, 7, 52))
    snow += [((sx - 9, sy - 110, 6)), ((sx + 9, sy - 110, 6))]
    snow += [(sx, sy - 106 + i, 9) for i in range(2, 10)]          # 胡萝卜鼻
    snow += [(sx + i, sy - 82 + int(i * 0.4), 2) for i in range(-16, 18, 3)]  # 围巾
    snow += [(sx - 26, sy - 34, 6), (sx - 40, sy - 18, 6), (sx - 52, sy - 6, 6)]
    snow += [(sx + 26, sy - 34, 6), (sx + 40, sy - 18, 6), (sx + 52, sy - 6, 6)]
    snow += [(sx, sy - 44, 2), (sx, sy - 20, 2), (sx, sy + 4, 2)]
    snow += fill_rect(sx - 30, sy - 132, 60, 12, 6, 4.4)           # 帽子
    snow += fill_rect(sx - 20, sy - 162, 40, 32, 6, 4.6)
    add(snow, G_SNOW, 2)

    # 礼物
    gifts = [
        (322, 636, 96, 68, 10), (440, 650, 78, 56, 13),
        (536, 630, 108, 76, 11), (664, 648, 72, 52, 14),
    ]
    for gx, gy, gw, gh, ci in gifts:
        if SCENE_BASE is not None:
            ov = pygame.Surface((VW, VH), pygame.SRCALPHA)
            pygame.draw.rect(ov, (30, 30, 40, 200), (gx, gy, gw, gh))
            SCENE_BASE.blit(ov, (0, 0))
        gifts_pts = fill_rect(gx, gy, gw, gh, ci, 5.4) + out_rect(gx, gy, gw, gh, 1, 2.8)
        gifts_pts += fill_rect(gx + gw / 2 - 5, gy, 10, gh, 12, 4.4)
        gifts_pts += fill_rect(gx, gy + gh / 2 - 5, gw, 10, 12, 4.4)
        gifts_pts += [(gx + gw / 2 + random.uniform(-13, 13), gy - 8 + random.uniform(-6, 6), 15)
                      for _ in range(12)]
        add(gifts_pts, G_GIFT, 2)

    # 星尘背景
    dust = [(random.uniform(0, VW), random.uniform(0, VH), 12) for _ in range(320)]
    add(dust, G_DUST, 1)

    # 树与物体的落地阴影
    if SCENE_BASE is not None:
        ov = pygame.Surface((VW, VH), pygame.SRCALPHA)
        for cx, cy, rx, ry, a in ((CX, 634, 300, 44, 105), (929, 690, 120, 22, 95),
                                  (178, 700, 86, 18, 80)):
            for k in range(ry, 0, -1):
                aa = int(a * (1 - k / float(ry)) ** 1.4)
                pygame.draw.ellipse(ov, (4, 8, 18, aa),
                                    (cx - rx, cy - k, rx * 2, k * 2))
        SCENE_BASE.blit(ov, (0, 0))

    # 文字
    build_text_glow()
    tpts = sample_text("圣诞快乐", 152, 332, 2800, 0, 13)
    for x, y, ci, sz in tpts:
        P2.append([random.uniform(0, VW), random.uniform(0, VH),
                   0.0, 0.0, x, y, ci, sz, random.uniform(0, TAU), G_TEXT])
    bake_static()


def bake_static():
    """把静态场景粒子一次性烘焙成一张图，运行时只做一次贴图（大幅提速）"""
    global P2, SCENE_SURF, STATIC_PTS
    keep = []
    STATIC_PTS = []
    for p in P2:
        if p[9] == G_TEXT:
            keep.append(p)
        else:
            STATIC_PTS.append(p)
    P2 = keep
    rebuild_scene_surf()


def rebuild_scene_surf():
    global SCENE_SURF
    surf = pygame.Surface((VW, VH), pygame.SRCALPHA)
    for p in STATIC_PTS:
        if p[9] == G_DUST:
            spr = SPR_NRM[((p[6] * 5 + 1) * 4 + 1)]
        else:
            spr = SPR_NRM[((p[6] * 5 + p[7]) * 4 + 3)]
        surf.blit(spr, (p[4] - spr.get_width() // 2, p[5] - spr.get_height() // 2))
    SCENE_SURF = surf


TEXT_GLOWS = []


def build_text_glow():
    global TEXT_GLOWS
    font = load_font(152)
    raw = font.render("圣诞快乐", True, (255, 255, 255))
    raw.set_colorkey((0, 0, 0))
    w, h = raw.get_size()
    base = pygame.Surface((w, h), pygame.SRCALPHA)
    base.blit(raw, (0, 0))
    wide = pygame.transform.smoothscale(
        pygame.transform.smoothscale(base, (max(1, w // 12), max(1, h // 12))), (w, h))
    mid = pygame.transform.smoothscale(
        pygame.transform.smoothscale(base, (max(1, w // 7), max(1, h // 7))), (w, h))
    tight = pygame.transform.smoothscale(
        pygame.transform.smoothscale(base, (max(1, w // 4), max(1, h // 4))), (w, h))
    layer = pygame.Surface((w + 96, h + 96), pygame.SRCALPHA)
    p1, p2 = COLORS[13], COLORS[12]
    for s, g in ((wide, (p1[0] // 3, p1[1] // 3, p1[2] // 3, 108)),
                 (mid, (p1[0] * 4 // 5, p1[1] * 4 // 5, p1[2] * 4 // 5, 168)),
                 (tight, (min(255, (p2[0] + 255) // 2), min(255, (p2[1] + 255) // 2),
                          min(255, (p2[2] + 255) // 2), 232))):
        s.fill(g, special_flags=pygame.BLEND_RGBA_MULT)
        layer.blit(s, (48, 48))
    TEXT_GLOWS = []
    for a in (85, 120, 155, 190, 220, 250):
        c = layer.copy()
        c.set_alpha(a)
        TEXT_GLOWS.append(c)


def draw_text_glow(surf, t):
    gt = STATE["fade_text"]
    if gt < 0.03 or not TEXT_GLOWS:
        return
    pul = 0.5 + 0.5 * math.sin(t * 1.5)
    lv = min(5, int(min(1.0, gt * (0.78 + 0.22 * pul)) * 5))
    s = TEXT_GLOWS[lv]
    surf.blit(s, (CX - s.get_width() // 2, 332 - s.get_height() // 2))


def bake_glow():
    if BG is None:
        return
    halo = pygame.Surface((300, 300), pygame.SRCALPHA)
    for r in range(150, 0, -1):
        a = int(46 * (1 - r / 150) ** 1.8)
        pygame.draw.circle(halo, (110, 160, 250, a), (150, 150), r)
    BG.blit(halo, (1012 - 150, 138 - 150))
    for wx, wy in ((947, 552), (1027, 552)):
        halo2 = pygame.Surface((110, 110), pygame.SRCALPHA)
        for r in range(55, 0, -1):
            a = int(52 * (1 - r / 55) ** 1.7)
            pygame.draw.circle(halo2, (255, 186, 96, a), (55, 55), r)
        BG.blit(halo2, (wx + 18 - 55, wy + 20 - 55))


# ---------------------------------------------------------------- 3D 点云
def add3(bx, bz, yrel, ci, sz, grp):
    P3.append([bx, bz, yrel, ci, sz, random.uniform(0, TAU),
               random.uniform(0, VW), random.uniform(0, VH), 0.0, 0.0, grp])


def cone_r(f):
    return TREE_RAD * (f ** 1.06)


def build_3d():
    P3.clear()
    random.seed(777)
    tiers = 8
    # ---- 树身：贴着锥面为主，少量在内侧，形成清晰轮廓
    for _ in range(2500):
        f = random.random() ** 0.92
        base = cone_r(f)
        u = (f * tiers) % 1.0
        rr = base * (0.50 + 0.50 * u)
        r = rr * (0.92 if random.random() < 0.62 else random.uniform(0.45, 0.9))
        a = random.uniform(0, TAU)
        yrel = lerp(TREE_TOP_R, TREE_BOT_R, f)
        q = random.random()
        ci = 10 if q < 0.62 else (11 if q < 0.86 else 12)
        add3(r * math.cos(a), r * math.sin(a), yrel, ci, 2, G_TREE)
    # ---- 每层边缘一圈，强化枝叶层次
    for k in range(tiers):
        f = min(1.0, (k + 0.99) / tiers)
        base = cone_r(f)
        yrel = lerp(TREE_TOP_R, TREE_BOT_R, f)
        n = 26 + k * 9
        for i in range(n):
            a = i * TAU / n + k * 0.7
            add3(base * math.cos(a), base * math.sin(a), yrel, 12, 2, G_TREE)
            if i % 2 == 0:
                add3(base * 0.94 * math.cos(a), base * 0.94 * math.sin(a),
                     yrel + 3, 10, 2, G_TREE)
            if i % 3 == 0:
                add3(base * 0.9 * math.cos(a + 0.1), base * 0.9 * math.sin(a + 0.1),
                     yrel - 5, 12, 2, G_TREE)
    # ---- 缠绕彩灯
    for _ in range(320):
        f = random.random() ** 0.95
        base = cone_r(f)
        a = random.uniform(0, TAU)
        yrel = lerp(TREE_TOP_R, TREE_BOT_R, f)
        add3(base * math.cos(a), base * math.sin(a), yrel, 13 + random.randrange(3), 2, G_TREE)
    # ---- 发光彩带：螺旋缠绕，紧贴树面
    n1 = 620
    for i in range(n1):
        u = i / (n1 - 1)
        f = 0.06 + 0.82 * u
        ang = u * TAU * 4.4
        base = cone_r(f) * 1.01 + 2
        yrel = lerp(TREE_TOP_R, TREE_BOT_R, f)
        ci = 13 if i % 10 < 6 else 14
        add3(base * math.cos(ang), base * math.sin(ang), yrel, ci, 3, G_RIBBON)
    # ---- 第二条细彩带（反向缠绕）
    n2 = 340
    for i in range(n2):
        u = i / (n2 - 1)
        f = 0.09 + 0.77 * u
        ang = -u * TAU * 3.4 + 1.4
        base = cone_r(f) * 1.015 + 1
        yrel = lerp(TREE_TOP_R, TREE_BOT_R, f)
        add3(base * math.cos(ang), base * math.sin(ang), yrel, 15, 2, G_RIBBON)
    # ---- 树底收口：一圈暗点让树与雪地自然衔接
    for i in range(80):
        a = i * TAU / 80
        yrel = TREE_BOT_R + 2 + 3 * math.cos(a)
        add3(TREE_RAD * 0.86 * math.cos(a), TREE_RAD * 0.86 * math.sin(a),
             yrel, 11, 1, G_TREE)
    # ---- 树顶五角星：屏幕平面内的实心星形
    top = TREE_TOP_R - 34
    R_OUT, R_IN = 44.0, 18.0
    star_poly = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = R_OUT if k % 2 == 0 else R_IN
        star_poly.append((math.cos(a) * rr, math.sin(a) * rr))
    for i in range(0, 46, 2):
        fy = -R_OUT + i * (2 * R_OUT / 45.0)
        xs = []
        for j in range(10):
            x1, y1 = star_poly[j]
            x2, y2 = star_poly[(j + 1) % 10]
            if (y1 - fy) * (y2 - fy) <= 0 and y1 != y2:
                xs.append(x1 + (fy - y1) / (y2 - y1) * (x2 - x1))
        if len(xs) < 2:
            continue
        x0, x1v = min(xs), max(xs)
        for t in range(0, 5):
            px = x0 + (x1v - x0) * (t / 4.0) + random.uniform(-1.5, 1.5)
            add3(px, random.uniform(-6, 6), top + fy, 1, 2, G_STAR)
    for k in range(5):   # 五个尖角额外点，拉长星芒
        a = -math.pi / 2 + k * TAU / 5
        for j in range(10):
            d = R_OUT + 2 + random.random() * 12
            add3(math.cos(a) * d, random.uniform(-4, 4), top + math.sin(a) * d, 1, 2, G_STAR)


def scatter_3d():
    for p in P3:
        p[6] = random.uniform(-60, VW + 60)
        p[7] = random.uniform(-60, VH + 60)
        p[8] = p[9] = 0.0


# ---------------------------------------------------------------- 更新
def update_2d(dt, mx, my, t):
    for p in P2:
        tx, ty = p[4], p[5]
        vx, vy = p[2], p[3]
        vx += ((tx - p[0]) * 11.0 - vx * 3.4) * dt
        vy += ((ty - p[1]) * 11.0 - vy * 3.4) * dt
        x = p[0] + vx * dt
        y = p[1] + vy * dt
        dx, dy = x - mx, y - my
        d2 = dx * dx + dy * dy
        if d2 < 8100:
            d = math.sqrt(d2) + 1e-6
            f = (90 - d) / 90 * 340 * dt
            x += dx / d * f
            y += dy / d * f
            vx += dx / d * f * 1.6
            vy += dy / d * f * 1.6
        p[0], p[1], p[2], p[3] = x, y, vx, vy


def update_3d(dt, mx, my, t, rot):
    c, s = math.cos(rot), math.sin(rot)
    for p in P3:
        bx, bz = p[0], p[1]
        if p[10] == G_STAR:
            tx = CX + bx
            ty = CY + p[2]
        else:
            rx = bx * c - bz * s
            rz = bx * s + bz * c
            k = FZ / (FZ + rz)
            tx = CX + rx * k
            ty = CY + p[2] * k
        vx, vy = p[8], p[9]
        vx += ((tx - p[6]) * 13.0 - vx * 3.6) * dt
        vy += ((ty - p[7]) * 13.0 - vy * 3.6) * dt
        x = p[6] + vx * dt
        y = p[7] + vy * dt
        dx, dy = x - mx, y - my
        d2 = dx * dx + dy * dy
        if d2 < 8100:
            d = math.sqrt(d2) + 1e-6
            f = (90 - d) / 90 * 330 * dt
            x += dx / d * f
            y += dy / d * f
            vx += dx / d * f * 1.5
            vy += dy / d * f * 1.5
        p[6], p[7], p[8], p[9] = x, y, vx, vy


def update_flakes(dt, t, mx, my):
    for f in FLAKE:
        y = f[1] + f[3] * dt
        x = f[0] + math.sin(t * 0.55 + f[4]) * f[5] * dt * 2.2 + 6 * dt
        dx, dy = x - mx, y - my
        d2 = dx * dx + dy * dy
        if d2 < 7000:
            d = math.sqrt(d2) + 1e-6
            k = (84 - d) / 84 * 46 * dt
            x += dx / d * k
            y += dy / d * k
        if y > VH + 10:
            y, x = -10, random.uniform(0, VW)
        if x < -10:
            x = VW + 8
        elif x > VW + 10:
            x = -8
        f[0], f[1] = x, y


def update_sparks(dt):
    alive = []
    for p in SPARK:
        p[0] += p[2] * dt
        p[1] += p[3] * dt
        p[2] *= (1.0 - 1.55 * dt)
        p[3] = p[3] * (1.0 - 1.55 * dt) + 58.0 * dt
        p[4] -= dt
        if p[4] > 0:
            alive.append(p)
    SPARK[:] = alive

    alive = []
    for r in ROCKET:
        r[0] += r[2] * dt
        r[1] += r[3] * dt
        r[3] += 12 * dt
        r[4] -= dt
        r[5].append((r[0], r[1]))
        if len(r[5]) > 22:
            r[5].pop(0)
        if r[4] <= 0 or r[1] < 60:
            burst(r[0], r[1], r[7])
        else:
            alive.append(r)
    ROCKET[:] = alive


# ---------------------------------------------------------------- 烟花
FW_SHAPES = ("sphere", "ring", "willow", "double")


def launch(x=None, y=None, shape=None, height=None):
    if x is None:
        x = random.uniform(180, VW - 180)
    if y is None:
        y = VH - 40
    shape = shape or random.choice(FW_SHAPES)
    vy = -random.uniform(250, 330)
    if height:
        vy = -math.sqrt(max(1.0, 2 * 58 * (y - height)))
    ROCKET.append([x, y, random.uniform(-18, 18), vy, 0.75, [], 0, shape])


def burst(x, y, shape):
    pal = [10, 11, 12]
    # 爆心闪光
    for _ in range(26):
        a = random.uniform(0, TAU)
        sp = random.uniform(10, 60)
        SPARK.append([x, y, math.cos(a) * sp, math.sin(a) * sp, 0.42, 0, 0, 3,
                      random.uniform(0, TAU)])
    if shape == "ring":
        for i in range(260):
            a = i * TAU / 260 + random.uniform(-0.02, 0.02)
            sp = random.uniform(190, 300)
            SPARK.append([x, y, math.cos(a) * sp * 1.3, math.sin(a) * sp * 0.55,
                          random.uniform(1.4, 2.1), 0, pal[i % 3], 3, random.uniform(0, TAU)])
    elif shape == "willow":
        for i in range(340):
            a = random.uniform(0, TAU)
            sp = random.uniform(60, 205)
            SPARK.append([x, y, math.cos(a) * sp, math.sin(a) * sp,
                          random.uniform(1.9, 3.0), 0, 1 if i % 4 else 2, 2,
                          random.uniform(0, TAU)])
    elif shape == "double":
        for i in range(420):
            a = random.uniform(0, TAU)
            inner = i % 2
            sp = random.uniform(90, 165) if inner else random.uniform(225, 340)
            ci = 0 if inner else pal[random.randrange(3)]
            SPARK.append([x, y, math.cos(a) * sp, math.sin(a) * sp,
                          random.uniform(1.3, 2.2), 0, ci, 3 if inner else 2,
                          random.uniform(0, TAU)])
    else:
        for i in range(380):
            a = random.uniform(0, TAU)
            sp = min(abs(random.gauss(0, 1)) * 130, 350)
            ci = pal[random.randrange(3)] if i % 3 else 0
            SPARK.append([x, y, math.cos(a) * sp, math.sin(a) * sp,
                          random.uniform(1.2, 2.3), 0, ci, 3 if i % 4 == 0 else 2,
                          random.uniform(0, TAU)])
    if len(SPARK) > 2600:
        del SPARK[:len(SPARK) - 2600]
    if CHIME:
        CHIME.play()


# ---------------------------------------------------------------- 绘制
def draw_2d(surf, t):
    gt = STATE["fade_text"]
    gs = STATE["fade_scene"]
    a = int(255 * min(1.0, gs))
    if gs > 0.02:
        if SCENE_BASE is not None:
            SCENE_BASE.set_alpha(a)
            surf.blit(SCENE_BASE, (0, 0))
        if SCENE_SURF is not None:
            SCENE_SURF.set_alpha(a)
            surf.blit(SCENE_SURF, (0, 0))
    tier = 3 - int((1.0 - gt) * 2.2)
    tier = 0 if tier < 0 else min(3, tier)
    sa = SPR_ADD
    for p in P2:
        if gt < 0.04 and p[9] == G_TEXT:
            continue
        s = sa[((p[6] * 5 + p[7]) * 4 + tier)]
        surf.blit(s, (p[0] - s.get_width() // 2, p[1] - s.get_height() // 2),
                  special_flags=pygame.BLEND_RGB_ADD)


def draw_3d(surf, t, rot):
    for b in BUCKETS:
        b.clear()
    c, s = math.sin(rot), math.cos(rot)
    for p in P3:
        bx, bz = p[0], p[1]
        if p[10] == G_STAR:          # 树顶星始终正对镜头（不参与旋转透视）
            tx = CX + bx
            ty = CY + p[2]
            bi = 7
        else:
            rz = bx * s + bz * c
            k = FZ / (FZ + rz)
            tx = CX + (bx * c - bz * s) * k
            ty = CY + p[2] * k
            u = (rz + TREE_RAD) / (TREE_RAD * 2.0)
            u = 0.0 if u < 0 else (1.0 if u > 1 else u)
            bi = int(u * 7.99)
        u = (rz + TREE_RAD) / (TREE_RAD * 2.0) if p[10] != G_STAR else 0.5
        u = 0.0 if u < 0 else (1.0 if u > 1 else u)
        tier = 3 - int(u * 2.0)
        if p[10] == G_RIBBON:
            pulse = 0.5 + 0.5 * math.sin(t * 3.4 + p[5])
            tier = max(1, min(3, tier + (1 if pulse > 0.55 else 0)))
        elif p[10] == G_STAR:
            pulse = 0.5 + 0.5 * math.sin(t * 2.2 + p[5])
            tier = 3 if pulse > 0.3 else 2
        elif p[10] == G_TREE and p[3] >= 13:
            pulse = 0.5 + 0.5 * math.sin(t * 4.0 + p[5] * 1.6)
            tier = 2 if pulse < 0.2 else 3
        elif p[10] == G_TREE:
            tier = 2 - int(u * 1.3)
            tier = 0 if tier < 0 else tier
        idx = ((p[3] * 5 + p[4]) * 4 + tier)
        if p[10] == G_STAR:
            BUCKETS[bi].append((p[6], p[7], idx))
        else:
            BUCKETS[bi].append((p[6], p[7], idx))
    sa = SPR_ADD
    for b in BUCKETS:
        for x, y, idx in b:
            spr = sa[idx]
            surf.blit(spr, (x - spr.get_width() // 2, y - spr.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD)


def draw_sparks(surf, t, mx, my):
    sa = SPR_ADD
    for r in ROCKET:
        trail = r[5]
        for i in range(0, len(trail), 2):
            x, y = trail[i]
            f = i / max(1, len(trail))
            spr = sa[(0 * 5 + 1) * 4 + (1 if f > 0.5 else 0)]
            surf.blit(spr, (x - spr.get_width() // 2, y - spr.get_height() // 2),
                      special_flags=pygame.BLEND_RGB_ADD)
    for p in SPARK:
        x, y = p[0], p[1]
        life = p[4]
        fade = min(1.0, life / 0.6)
        tw = 0.60 + 0.40 * math.sin(t * 24.0 + p[8])
        lvl = fade * tw
        tier = 3 if lvl > 0.78 else (2 if lvl > 0.5 else (1 if lvl > 0.24 else 0))
        ci = p[6]
        sz = p[7]
        vx, vy = p[2], p[3]
        # 拖尾：沿速度方向叠三颗渐暗的粒子
        t2 = min(2, tier)
        for k, kf in ((1, 0.016), (2, 0.032), (3, 0.052)):
            tx = x - vx * kf
            ty = y - vy * kf
            spr2 = sa[((ci * 5 + 1) * 4 + max(0, t2 - k + 1))]
            surf.blit(spr2, (tx - spr2.get_width() // 2, ty - spr2.get_height() // 2),
                      special_flags=pygame.BLEND_RGB_ADD)
        spr = sa[((ci * 5 + sz) * 4 + tier)]
        surf.blit(spr, (x - spr.get_width() // 2, y - spr.get_height() // 2),
                  special_flags=pygame.BLEND_RGB_ADD)


def draw_flakes(surf):
    sa = SPR_ADD
    for x, y, r, spd, ph, drift in FLAKE:
        idx = ((0 * 5 + r) * 4 + (1 if r == 1 else 2))
        spr = sa[idx]
        surf.blit(spr, (x - spr.get_width() // 2, y - spr.get_height() // 2),
                  special_flags=pygame.BLEND_RGB_ADD)


def toggle_toast(text, sec=1.8):
    STATE["toast"] = text
    STATE["toast_t"] = sec


def toast_surf(text):
    if text not in TOAST_CACHE:
        f = load_font(27)
        txt = f.render(text, True, (255, 246, 218))
        pad = 24
        s = pygame.Surface((txt.get_width() + pad * 2, txt.get_height() + pad), pygame.SRCALPHA)
        pygame.draw.rect(s, (14, 18, 34, 205), s.get_rect(), border_radius=13)
        pygame.draw.rect(s, (255, 214, 130, 110), s.get_rect(), 1, border_radius=13)
        s.blit(txt, (pad, pad // 2))
        TOAST_CACHE[text] = s
    return TOAST_CACHE[text]


def build_hud():
    global HUD, HUD_ON, HUD_OFF, FONT_S, FW_ON, FW_OFF
    FONT_S = load_font(15)
    hints = ("点击 烟花/跳过    空格 音乐    ↑↓ 音量    C 配色    "
             "A 自动烟花    F 烟花    R 重播    S 截图    H 提示    ESC 退出")
    txt = FONT_S.render(hints, True, (208, 222, 246))
    HUD = pygame.Surface((VW, 42), pygame.SRCALPHA)
    HUD.fill((6, 10, 20, 160))
    HUD.blit(txt, (VW - txt.get_width() - 24, 13))
    HUD_ON = FONT_S.render("音乐 · 开", True, tuple(COLORS[13]))
    HUD_OFF = FONT_S.render("音乐 · 关", True, (140, 150, 172))
    FW_ON = FONT_S.render("自动烟花 · 开", True, tuple(COLORS[13]))
    FW_OFF = FONT_S.render("自动烟花 · 关", True, (140, 150, 172))


def draw_hud(surf, t):
    if STATE["help"]:
        a = 200 + 45 * math.sin(t * 1.3)
        HUD.set_alpha(int(a))
        surf.blit(HUD, (0, VH - 42))
        m = HUD_ON if STATE["music"] else HUD_OFF
        m.set_alpha(int(a))
        surf.blit(m, (22, VH - 34))
        pa = FONT_S.render("%s  %d%%" % (PALETTES[STATE["pal"]][0], int(STATE["vol"] * 100)),
                           True, tuple(COLORS[13]))
        pa.set_alpha(int(a))
        surf.blit(pa, (112, VH - 34))
        fa = FW_ON if STATE["auto_fw"] else FW_OFF
        fa.set_alpha(int(a))
        surf.blit(fa, (214, VH - 34))
    if STATE["toast_t"] > 0 and STATE["toast"]:
        s = toast_surf(STATE["toast"])
        s.set_alpha(int(255 * min(1.0, STATE["toast_t"] / 0.6)))
        surf.blit(s, (VW // 2 - s.get_width() // 2, 96))


def draw_frame(surf, t, rot):
    surf.blit(BG, (0, 0))
    draw_text_glow(surf, t)
    draw_2d(surf, t)
    if STATE["stage"] >= 2:
        draw_3d(surf, t, rot)
    draw_sparks(surf, t, 0, 0)
    draw_flakes(surf)
    draw_hud(surf, t)


def build_background():
    bg = pygame.Surface((VW, VH)).convert()
    for y in range(VH):
        f = y / (VH - 1)
        if f < 0.62:
            t = f / 0.62
            c = (int(lerp(4, 10, t)), int(lerp(8, 24, t)), int(lerp(22, 52, t)))
        else:
            t = (f - 0.62) / 0.38
            c = (int(lerp(10, 20, t)), int(lerp(24, 38, t)), int(lerp(52, 68, t)))
        pygame.draw.line(bg, c, (0, y), (VW, y))
    # 星云：几团柔光让夜空有层次
    for cx, cy, rr, col, peak in ((250, 170, 300, (44, 58, 150), 62),
                                  (860, 300, 340, (86, 44, 122), 46),
                                  (620, 90, 260, (30, 80, 150), 44)):
        s, pos = soft_disc(cx, cy, rr, col, peak, 1.9)
        bg.blit(s, pos)
    random.seed(31)
    for _ in range(230):
        x, y = random.randint(0, VW - 1), random.randint(0, 640)
        a = random.randint(70, 210)
        r = random.choice((1, 1, 2))
        pygame.draw.circle(bg, (a, min(255, a + 12), 255), (x, y), r)
    # 远景山影
    for k in range(3):
        pts = [(0, 800)]
        for x in range(0, VW + 40, 40):
            pts.append((x, 620 + 34 * math.sin(x / 210.0 + k * 1.7) + k * 12))
        pts.append((VW, 800))
        pygame.draw.polygon(bg, (8 + k * 4, 18 + k * 5, 36 + k * 6), pts)
    return bg


# ---------------------------------------------------------------- 舞台
def set_stage(s):
    STATE["stage"] = s
    if s == 0:
        STATE["fade_text"] = 1.0
        STATE["fade_scene"] = 0.0
    elif s == 1:
        cx, cy = CX, CY - 40
        for p in P2:
            if p[9] == G_TEXT:
                dx, dy = p[0] - cx, p[1] - cy
                d = math.hypot(dx, dy) + 1e-3
                sp = random.uniform(140, 330)
                p[2], p[3] = dx / d * sp, dy / d * sp - 70
                p[9] = G_DUST
                p[4], p[5] = random.uniform(0, VW), random.uniform(0, VH)
        for p in P3:
            dx, dy = p[6] - cx, p[7] - cy
            d = math.hypot(dx, dy) + 1e-3
            sp = random.uniform(120, 330)
            p[8], p[9] = dx / d * sp, dy / d * sp - 60
    elif s == 2:
        pass
    elif s == 3:
        STATE["next_fw"] = 0.4
        for i in range(3):
            launch(VW * (0.25 + 0.25 * i) + random.uniform(-60, 60), VH - 30,
                   shape=None, height=random.uniform(140, 280))


# ---------------------------------------------------------------- 音视频
def setup_audio():
    global CHIME, MUSIC_OK
    try:
        pygame.mixer.init(frequency=SR, size=-16, channels=2, buffer=512)
    except Exception:
        MUSIC_OK = False
        return
    try:
        tmp = tempfile.gettempdir()
        mp = os.path.join(tmp, "xmas_p2_music.wav")
        cp = os.path.join(tmp, "xmas_p2_chime.wav")
        if not _valid_wav(mp):
            build_music(mp)
        if not _valid_wav(cp):
            build_chime(cp)
        pygame.mixer.music.load(mp)
        pygame.mixer.music.set_volume(STATE["vol"])
        pygame.mixer.music.play(-1)
        CHIME = pygame.mixer.Sound(cp)
        CHIME.set_volume(0.45)
        MUSIC_OK = True
    except Exception:
        MUSIC_OK = False


def _valid_wav(path):
    try:
        if os.path.getsize(path) < 60000:
            return False
        with wave.open(path, "rb") as w:
            return w.getnframes() > 1000
    except Exception:
        return False


def present(screen, virt):
    sw, sh = screen.get_size()
    if (sw, sh) == (VW, VH):
        screen.blit(virt, (0, 0))
        return
    k = min(sw / VW, sh / VH)
    w, h = int(VW * k), int(VH * k)
    screen.fill((0, 0, 0))
    screen.blit(pygame.transform.smoothscale(virt, (w, h)), ((sw - w) // 2, (sh - h) // 2))


def to_virtual(pos):
    sw, sh = pygame.display.get_surface().get_size()
    k = min(sw / VW, sh / VH)
    ox, oy = (sw - VW * k) // 2, (sh - VH * k) // 2
    return (int((pos[0] - ox) / k), int((pos[1] - oy) / k))


def advance():
    s = STATE["stage"]
    if s < 3:
        set_stage(s + 1)


def reload_all():
    global BG
    STATE["t"] = 0.0
    SPARK.clear()
    ROCKET.clear()
    scatter_3d()
    BG = build_background()
    build_scene()
    bake_glow()
    set_stage(0)


# ---------------------------------------------------------------- 主循环
def main():
    pygame.init()
    pygame.display.set_caption("圣诞快乐 · 粒子炫酷版")
    info = pygame.display.Info()
    win_w = max(760, min(VW, info.current_w - 40))
    win_h = max(500, min(VH, info.current_h - 90))
    screen = pygame.display.set_mode((win_w, win_h), pygame.DOUBLEBUF | pygame.RESIZABLE)
    virt = pygame.Surface((VW, VH)).convert()

    f = load_font(24)
    txt = f.render("正在生成粒子与音乐…", True, (216, 230, 250))
    screen.fill((4, 8, 18))
    screen.blit(txt, (win_w // 2 - txt.get_width() // 2, win_h // 2 - 12))
    pygame.display.flip()

    global BG
    build_sprites()
    BG = build_background()
    build_scene()
    bake_glow()
    build_3d()
    for _ in range(170):
        FLAKE.append([random.uniform(0, VW), random.uniform(0, VH),
                      random.choice((1, 1, 2)), random.uniform(18, 58),
                      random.uniform(0, TAU), random.uniform(4, 15)])
    build_hud()
    setup_audio()
    set_stage(0)

    clock = pygame.time.Clock()
    running = True
    while running:
        dt = min(0.045, clock.tick(60) / 1000.0)
        STATE["t"] += dt
        t = STATE["t"]
        mx, my = to_virtual(pygame.mouse.get_pos())
        # 自动推进
        st = STATE["stage"]
        if st == 0 and t > 2.9:
            set_stage(1)
        elif st == 1 and t > 3.7:
            set_stage(2)
        elif st == 2 and t > 6.9:
            set_stage(3)
        if st >= 2:
            STATE["fade_scene"] = min(1.0, STATE["fade_scene"] + dt * 0.9)
            STATE["fade_text"] = max(0.0, STATE["fade_text"] - dt * 1.6)
        elif st == 1:
            STATE["fade_text"] = max(0.0, STATE["fade_text"] - dt * 2.4)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                k = e.key
                if k == pygame.K_ESCAPE:
                    running = False
                elif k == pygame.K_SPACE:
                    if MUSIC_OK:
                        if STATE["music"]:
                            pygame.mixer.music.pause()
                        else:
                            pygame.mixer.music.unpause()
                        STATE["music"] = not STATE["music"]
                        toggle_toast("音乐已" + ("打开" if STATE["music"] else "关闭"))
                    else:
                        toggle_toast("未检测到音频设备")
                elif k == pygame.K_UP:
                    STATE["vol"] = min(1.0, STATE["vol"] + 0.1)
                    if MUSIC_OK:
                        pygame.mixer.music.set_volume(STATE["vol"])
                    toggle_toast("音量 %d%%" % int(STATE["vol"] * 100))
                elif k == pygame.K_DOWN:
                    STATE["vol"] = max(0.0, STATE["vol"] - 0.1)
                    if MUSIC_OK:
                        pygame.mixer.music.set_volume(STATE["vol"])
                    toggle_toast("音量 %d%%" % int(STATE["vol"] * 100))
                elif k == pygame.K_c:
                    apply_palette((STATE["pal"] + 1) % len(PALETTES))
                    toggle_toast("灯光配色 · " + PALETTES[STATE["pal"]][0])
                elif k == pygame.K_f:
                    launch()
                elif k == pygame.K_a:
                    STATE["auto_fw"] = not STATE["auto_fw"]
                    STATE["next_fw"] = 0.6
                    toggle_toast("自动烟花已" + ("开启" if STATE["auto_fw"] else "关闭"))
                elif k == pygame.K_r:
                    reload_all()
                elif k == pygame.K_s:
                    STATE["shots"] += 1
                    p = os.path.join(SCRIPT_DIR, "粒子版截图_%s.png" % time.strftime("%H%M%S"))
                    pygame.image.save(virt, p)
                    toggle_toast("截图已保存", 2.4)
                elif k == pygame.K_h:
                    STATE["help"] = not STATE["help"]
                else:
                    if STATE["stage"] < 3:
                        advance()
            elif e.type == pygame.MOUSEBUTTONDOWN:
                vx, vy = to_virtual(e.pos)
                burst(vx, vy, random.choice(FW_SHAPES))
                if STATE["stage"] < 2 and t > 1.8:
                    advance()
                elif STATE["stage"] == 2:
                    set_stage(3)

        if pygame.mouse.get_pressed()[0] and STATE["stage"] >= 2:
            if random.random() < 0.35:
                burst(mx, my, random.choice(FW_SHAPES))

        # 自动烟花
        if STATE["stage"] == 3 and STATE["auto_fw"]:
            STATE["next_fw"] -= dt
            if STATE["next_fw"] <= 0:
                launch()
                STATE["next_fw"] = random.uniform(2.4, 4.6)

        update_2d(dt, mx, my, t)
        update_3d(dt, mx, my, t, t * ROT_SPEED)
        update_flakes(dt, t, mx, my)
        update_sparks(dt)
        if STATE["toast_t"] > 0:
            STATE["toast_t"] -= dt

        draw_frame(virt, t, t * ROT_SPEED)
        present(screen, virt)
        pygame.display.flip()

    pygame.quit()


# ---------------------------------------------------------------- 自检
def snapshot():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    scr = pygame.display.set_mode((VW, VH))
    global BG
    build_sprites()
    BG = build_background()
    build_scene()
    bake_glow()
    build_3d()
    for _ in range(170):
        FLAKE.append([random.uniform(0, VW), random.uniform(0, VH),
                      random.choice((1, 1, 2)), random.uniform(18, 58),
                      random.uniform(0, TAU), random.uniform(4, 15)])
    build_hud()
    out = []
    shots = ((0, 3.6, 0), (2, 7.6, 0), (2, 9.4, 0), (3, 11.0, 0.9))
    if "--paltest" in sys.argv:
        for pi in range(len(PALETTES)):
            apply_palette(pi)
            STATE["flash"] = 0.0
            STATE["stage"] = 2
            STATE["t"] = 7.6
            STATE["fade_text"] = 0.0
            STATE["fade_scene"] = 1.0
            for _ in range(340):
                update_2d(0.016, -500, -500, 7.6)
                update_3d(0.016, -500, -500, 7.6, 7.6 * ROT_SPEED)
            draw_frame(scr, 7.6, 7.6 * ROT_SPEED)
            p = os.path.join(tempfile.gettempdir(), "pv2_pal_%d.png" % pi)
            pygame.image.save(scr, p)
            out.append(p)
        print("\n".join(out))
        pygame.quit()
        return
    for stage, tt, spark_age in shots:
        if stage >= 1:
            set_stage(1)          # 文字转星尘
        set_stage(stage) if stage < 2 else None
        STATE["stage"] = stage
        STATE["t"] = tt
        STATE["fade_text"] = 0.0 if stage >= 2 else 1.0
        STATE["fade_scene"] = 1.0 if stage >= 3 else 0.0
        for _ in range(340):
            update_2d(0.016, -500, -500, tt)
            update_3d(0.016, -500, -500, tt, tt * ROT_SPEED)
        SPARK.clear()
        ROCKET.clear()
        if stage == 3:
            for i in range(5):
                launch(VW * (0.15 + 0.17 * i), VH - 30,
                       shape=("double", "ring", "willow", "sphere", "sphere")[i],
                       height=random.uniform(140, 300))
            for _ in range(int(spark_age / 0.016) + 34):
                update_sparks(0.016)
            burst(300, 250, "double")
            burst(760, 210, "ring")
            burst(1020, 330, "willow")
            burst(520, 300, "sphere")
            for _ in range(22):
                update_sparks(0.016)
        draw_frame(scr, tt, tt * ROT_SPEED)
        p = os.path.join(tempfile.gettempdir(), "pv2_snap_%d_%d.png" % (stage, int(tt * 10)))
        pygame.image.save(scr, p)
        out.append(p)
    print("\n".join(out))
    pygame.quit()


if __name__ == "__main__":
    if "--snapshot" in sys.argv:
        snapshot()
    else:
        main()
