#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import textwrap
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
    im = Image.new(mode="RGB", size=(240, 124))
    shapes = coord_generator(240, 124, side_length=15)
    color1 = Color(randint(128, 255), randint(128, 255), randint(128, 255))
    color2 = Color(randint(128, 255), randint(128, 255), randint(128, 255))
    for shape, color in zip(shapes, random_colors(color1, color2)):
        ImageDraw.Draw(im).polygon(shape, fill=color)
    return im


def draw_multiple_line_text(image, text, font, text_color):
    draw = ImageDraw.Draw(image)
    image_width, image_height = image.size
    lines = textwrap.wrap(text, width=12)
    _, _, lw, lh = font.getbbox(lines[0])
    nlines = len(lines) if len(lines) <= 4 else 4
    y_text = int(image_height / (2**nlines)) if nlines < 4 else 0
    for line in lines:
        _, _, line_width, line_height = font.getbbox(line)
        draw.text(
            ((image_width - line_width) / 2, y_text), line, font=font, fill=text_color
        )
        y_text += line_height


def overlay_text(bgr_img, text="IsardVDI"):
    font = ImageFont.truetype(
        "/usr/share/fonts/ttf-liberation/LiberationMono-Bold.ttf", 33, encoding="utf-8"
    )
    text_color = (randint(0, 99), randint(0, 99), randint(0, 99))
    draw_multiple_line_text(bgr_img, text, font, text_color)

    fgr_img = Image.new("RGBA", bgr_img.size, color=(0, 0, 0, 0))
    mask_img = Image.new("L", bgr_img.size, color=0)
    return Image.composite(fgr_img, bgr_img, mask_img)


def gen_img_from_name(desktop_name):
    generators = [generate_squares, generate_triangles, generate_hexagons]
    return overlay_text(bgr_img=draw_tiling(choice(generators)), text=desktop_name)
