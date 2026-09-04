#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import os
from collections import namedtuple
from random import choice, randint, uniform

from PIL import Image, ImageDraw, ImageFont, ImageOps
from specktre.colors import RGBColor
from specktre.tilings import generate_hexagons, generate_squares, generate_triangles

Color = namedtuple("Color", ["red", "green", "blue"])


def random_colors(color1, color2):
    d_red = color1.red - color2.red
    d_green = color1.green - color2.green
    d_blue = color1.blue - color2.blue

    while True:
        proportion = uniform(0, 1)

        yield Color(
            red=color1.red - int(d_red * proportion),
            green=color1.green - int(d_green * proportion),
            blue=color1.blue - int(d_blue * proportion),
        )


def draw_tiling(coord_generator):
    im = Image.new(mode="RGB", size=(480, 248))
    shapes = coord_generator(480, 248, side_length=15)
    color1 = Color(randint(128, 255), randint(128, 255), randint(128, 255))
    color2 = Color(randint(128, 255), randint(128, 255), randint(128, 255))
    for shape, color in zip(shapes, random_colors(color1, color2)):
        ImageDraw.Draw(im).polygon(shape, fill=color)
    return im


MAX_LINES = 4
TEXT_MARGIN = 0.9
MAX_FONT_SIZE = 88
MIN_FONT_SIZE = 16

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",  # Debian / Ubuntu
    "/usr/share/fonts/liberation/LiberationMono-Bold.ttf",  # Alpine
    "/usr/share/fonts/ttf-liberation/LiberationMono-Bold.ttf",  # Alpine (legacy path)
    "/usr/share/fonts/liberation-mono/LiberationMono-Bold.ttf",  # Fedora / RHEL
)


def _load_font(size):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size, encoding="utf-8")
    # Sized fallback: the unsized default is a bitmap font that renders unreadably small.
    return ImageFont.load_default(size)


def _wrap(text, font, max_width):
    """Wrap on measured width: the fallback font is proportional, so no column count fits."""
    lines = []
    for word in text.split() or [text]:
        if lines and font.getlength(f"{lines[-1]} {word}") <= max_width:
            lines[-1] = f"{lines[-1]} {word}"
            continue
        while len(word) > 1 and font.getlength(word) > max_width:
            cut = len(word) - 1
            while cut > 1 and font.getlength(word[:cut]) > max_width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        lines.append(word)
    return lines or [text]


def fit_text(text, image_size):
    """Biggest font size whose wrapped text still fits inside the card."""
    max_width = image_size[0] * TEXT_MARGIN
    max_height = image_size[1] * TEXT_MARGIN
    for size in range(MAX_FONT_SIZE, MIN_FONT_SIZE - 1, -2):
        font = _load_font(size)
        lines = _wrap(text, font, max_width)
        if (
            len(lines) <= MAX_LINES
            and len(lines) * sum(font.getmetrics()) <= max_height
        ):
            return font, lines
    return font, lines[:MAX_LINES]


def draw_multiple_line_text(image, text, text_color):
    draw = ImageDraw.Draw(image)
    image_width, image_height = image.size
    font, lines = fit_text(text, image.size)
    line_height = sum(font.getmetrics())
    y_text = (image_height - len(lines) * line_height) / 2
    for line in lines:
        draw.text(
            ((image_width - font.getlength(line)) / 2, y_text),
            line,
            font=font,
            fill=text_color,
        )
        y_text += line_height


def overlay_text(bgr_img, text="IsardVDI"):
    text_color = (randint(0, 99), randint(0, 99), randint(0, 99))
    draw_multiple_line_text(bgr_img, text, text_color)

    fgr_img = Image.new("RGBA", bgr_img.size, color=(0, 0, 0, 0))
    mask_img = Image.new("L", bgr_img.size, color=0)
    return Image.composite(fgr_img, bgr_img, mask_img)


def gen_img_from_name(desktop_name):
    generators = [generate_squares, generate_triangles, generate_hexagons]
    return overlay_text(bgr_img=draw_tiling(choice(generators)), text=desktop_name)
