"""
TIENDAS-BUILD — íconos y splash de las apps nativas desde el logo vigente.

El logo vigente es el de `icon-512.svg` (manifest PWA): "LX" itálico serif
(L ámbar, X naranja) + flor sobre fondo #04080F. Este script lo redibuja con
Pillow a cualquier tamaño (sin rasterizar un PNG de 512 hacia arriba) y escribe:

  * Android: mipmap-*/ic_launcher{,_round,_foreground}.png, color de fondo
    adaptativo, drawable*/splash.png (todas las densidades/orientaciones).
  * iOS: AppIcon 1024 opaco y sin esquinas redondeadas (Apple las aplica),
    Splash.imageset 2732x2732 (x3 escalas).
  * store-assets/: ícono Play 512x512 y gráfico de funciones 1024x500.

Ningún activo contiene datos personales (solo la marca). Fuentes de Windows
(Georgia Bold Italic + Segoe UI Emoji); si faltan, el script aborta en vez de
generar algo distinto del logo.

Uso: python scripts/build_store_assets.py
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "android" / "app" / "src" / "main" / "res"
IOS_ASSETS = ROOT / "ios" / "App" / "App" / "Assets.xcassets"
STORE = ROOT / "store-assets"

BG = (4, 8, 15)          # #04080F
L_COLOR = (240, 165, 0)  # #F0A500
X_COLOR = (255, 101, 53)  # #FF6535

_FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
_GEORGIA = _FONT_DIR / "georgiaz.ttf"   # Georgia Bold Italic
_EMOJI = _FONT_DIR / "seguiemj.ttf"
FLOWER = "\U0001F33A"


def _fonts(unit: float):
    """Fuentes escaladas a `unit` px por cada 512 px de lienzo."""
    for p in (_GEORGIA, _EMOJI):
        if not p.exists():
            raise SystemExit(f"Falta la fuente {p}; no se genera un logo distinto del vigente.")
    k = unit / 512.0
    return (ImageFont.truetype(str(_GEORGIA), round(220 * k)),
            ImageFont.truetype(str(_EMOJI), round(70 * k)))


def draw_mark(size: int, *, content: float = 1.0, bg: bool = True,
              rounded: bool = False, circle: bool = False) -> Image.Image:
    """Dibuja el logo en un lienzo `size`x`size`. `content` escala solo la marca
    (adaptive icons usan ~0.61 por la zona segura). bg=False => transparente."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if bg:
        if circle:
            d.ellipse([0, 0, size - 1, size - 1], fill=BG + (255,))
        elif rounded:
            d.rounded_rectangle([0, 0, size - 1, size - 1], radius=round(size * 96 / 512), fill=BG + (255,))
        else:
            d.rectangle([0, 0, size, size], fill=BG + (255,))

    unit = size * content          # px por 512 lógicos
    off = (size - unit) / 2
    f_text, f_emoji = _fonts(unit)

    def at(x, y):
        return off + x * unit / 512, off + y * unit / 512

    d.text(at(130, 330), "L", font=f_text, fill=L_COLOR + (255,), anchor="ms")
    d.text(at(330, 330), "X", font=f_text, fill=X_COLOR + (255,), anchor="ms")
    d.text(at(358, 175), FLOWER, font=f_emoji, embedded_color=True, anchor="ms")
    return img


def _save(img: Image.Image, path: Path, opaque: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if opaque:
        flat = Image.new("RGB", img.size, BG)
        flat.paste(img, mask=img.getchannel("A"))
        flat.save(path, "PNG", optimize=True)
    else:
        img.save(path, "PNG", optimize=True)


def splash(w: int, h: int, mark_frac: float = 0.34) -> Image.Image:
    """Fondo liso de marca con la marca (sin fondo propio) centrada."""
    img = Image.new("RGB", (w, h), BG)
    side = round(min(w, h) * mark_frac)
    mark = draw_mark(side, bg=False)
    img.paste(mark, ((w - side) // 2, (h - side) // 2), mark)
    return img


def build_android() -> int:
    n = 0
    densities = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for dens, px in densities.items():
        d = RES / f"mipmap-{dens}"
        _save(draw_mark(px, rounded=True), d / "ic_launcher.png"); n += 1
        _save(draw_mark(px, circle=True), d / "ic_launcher_round.png"); n += 1
        fg = round(px * 108 / 48)
        # Zona segura adaptativa: 66/108 del lienzo => marca al ~61%.
        _save(draw_mark(fg, content=66 / 108, bg=False), d / "ic_launcher_foreground.png"); n += 1
    (RES / "values" / "ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        '    <color name="ic_launcher_background">#04080F</color>\n</resources>\n', encoding="utf-8")
    n += 1
    for p in RES.glob("drawable*/splash.png"):
        w, h = Image.open(p).size
        splash(w, h).save(p, "PNG", optimize=True); n += 1
    return n


def build_ios() -> int:
    n = 0
    # iOS exige 1024x1024 opaco, sin esquinas redondeadas.
    _save(draw_mark(1024), IOS_ASSETS / "AppIcon.appiconset" / "AppIcon-512@2x.png", opaque=True); n += 1
    for name in ("splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"):
        splash(2732, 2732, 0.22).save(IOS_ASSETS / "Splash.imageset" / name, "PNG", optimize=True); n += 1
    return n


def build_store() -> int:
    STORE.mkdir(exist_ok=True)
    _save(draw_mark(512), STORE / "play-icon-512.png", opaque=True)
    fg = Image.new("RGB", (1024, 500), BG)
    mark = draw_mark(380, bg=False)
    fg.paste(mark, ((1024 - 380) // 2, (500 - 380) // 2), mark)
    fg.save(STORE / "play-feature-graphic-1024x500.png", "PNG", optimize=True)
    return 2


if __name__ == "__main__":
    a, i, s = build_android(), build_ios(), build_store()
    print(f"Android: {a} archivos | iOS: {i} | store-assets: {s}")
