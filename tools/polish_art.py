from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path("static/tiles")
TW, TH = 64, 32


def rgba(c):
    return c if len(c) == 4 else (*c, 255)


def mix(a, b, t):
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))


def lighten(c, t=0.18):
    return mix(c, (255, 248, 226), t)


def darken(c, t=0.22):
    return mix(c, (55, 42, 31), t)


def in_diamond(x, y, w=TW, h=TH):
    return abs(x - w / 2) / (w / 2) + abs(y - h / 2) / (h / 2) <= 1


def base_tile():
    return Image.new("RGBA", (TW, TH), (0, 0, 0, 0))


def fill_diamond(img, base):
    p = img.load()
    for y in range(img.height):
        for x in range(img.width):
            if in_diamond(x + 0.5, y + 0.5, img.width, img.height):
                p[x, y] = rgba(base)


def diamond_outline(draw, color):
    draw.line([(32, 0), (63, 16), (32, 31), (0, 16), (32, 0)], fill=rgba(color), width=1)


def make_grass():
    img = base_tile()
    base = (115, 178, 83)
    fill_diamond(img, base)
    p = img.load()
    for y in range(TH):
        for x in range(TW):
            if not in_diamond(x + 0.5, y + 0.5):
                continue
            n = (x * 37 + y * 61) % 17
            if n in (0, 1):
                p[x, y] = rgba(lighten(base, 0.18))
            elif n == 8:
                p[x, y] = rgba(darken(base, 0.16))
    diamond_outline(ImageDraw.Draw(img), (76, 128, 58))
    return img


def make_path():
    img = base_tile()
    base = (202, 177, 131)
    fill_diamond(img, base)
    p = img.load()
    mortar = (158, 132, 92)
    hi = (225, 205, 162)
    for y in range(TH):
        for x in range(TW):
            if not in_diamond(x + 0.5, y + 0.5):
                continue
            yy = y // 4
            off = 4 if yy % 2 else 0
            if y % 4 == 0 or (x + off) % 8 == 0:
                p[x, y] = rgba(mortar)
            elif (x + off) % 8 == 1 and y % 4 == 1:
                p[x, y] = rgba(hi)
    diamond_outline(ImageDraw.Draw(img), (138, 111, 76))
    return img


def make_water():
    img = base_tile()
    base = (88, 157, 205)
    fill_diamond(img, base)
    p = img.load()
    for y in range(TH):
        for x in range(TW):
            if not in_diamond(x + 0.5, y + 0.5):
                continue
            wave = (x + y * 2) % 19
            if wave in (0, 1):
                p[x, y] = rgba((153, 209, 234))
            elif wave in (9, 10):
                p[x, y] = rgba((70, 132, 184))
            if y > 20:
                p[x, y] = rgba(mix(p[x, y][:3], (45, 110, 170), 0.16))
    diamond_outline(ImageDraw.Draw(img), (57, 116, 169))
    return img


def make_floor_wood():
    img = base_tile()
    p = img.load()
    colors = [(184, 123, 74), (204, 145, 91), (158, 100, 59)]
    for y in range(TH):
        for x in range(TW):
            if not in_diamond(x + 0.5, y + 0.5):
                continue
            c = colors[(y // 4) % len(colors)]
            if y % 4 == 0:
                c = (111, 72, 45)
            elif (x * 3 + y) % 23 == 0:
                c = lighten(c, 0.14)
            p[x, y] = rgba(c)
    diamond_outline(ImageDraw.Draw(img), (108, 72, 48))
    return img


def make_floor_stone():
    img = base_tile()
    base = (172, 181, 178)
    fill_diamond(img, base)
    p = img.load()
    mortar = (126, 136, 136)
    for y in range(TH):
        for x in range(TW):
            if not in_diamond(x + 0.5, y + 0.5):
                continue
            off = 5 if (y // 5) % 2 else 0
            if y % 5 == 0 or (x + off) % 10 == 0:
                p[x, y] = rgba(mortar)
            elif (x + y) % 11 == 0:
                p[x, y] = rgba(lighten(base, 0.12))
    diamond_outline(ImageDraw.Draw(img), (120, 130, 128))
    return img


def make_floor_tile():
    img = base_tile()
    p = img.load()
    a, b, joint = (216, 202, 164), (190, 179, 145), (150, 132, 99)
    for y in range(TH):
        for x in range(TW):
            if not in_diamond(x + 0.5, y + 0.5):
                continue
            if x % 4 == 0 or y % 4 == 0:
                p[x, y] = rgba(joint)
            else:
                p[x, y] = rgba(a if ((x // 4 + y // 4) % 2 == 0) else b)
    diamond_outline(ImageDraw.Draw(img), (132, 113, 83))
    return img


def make_wall(base, accent=None, mode="brick"):
    img = Image.new("RGBA", (32, 32), rgba(base))
    p = img.load()
    if mode == "brick":
        mortar = darken(base, 0.30)
        hi = lighten(base, 0.18)
        for y in range(32):
            for x in range(32):
                off = 4 if (y // 4) % 2 else 0
                if y % 4 == 0 or (x + off) % 8 == 0:
                    p[x, y] = rgba(mortar)
                elif (x + off) % 8 == 1 and y % 4 == 1:
                    p[x, y] = rgba(hi)
    elif mode == "panel":
        frame = darken(base, 0.34)
        for y in range(32):
            for x in range(32):
                if x % 8 == 0 or y % 8 == 0:
                    p[x, y] = rgba(frame)
                elif (x + y) % 13 == 0:
                    p[x, y] = rgba(lighten(base, 0.22))
    elif mode == "books":
        draw = ImageDraw.Draw(img)
        shelf = darken(base, 0.36)
        book_cols = [(188, 92, 82), (91, 145, 101), (202, 170, 77), (92, 122, 182), (162, 112, 165)]
        for sy in (8, 18, 28):
            draw.line([(0, sy), (31, sy)], fill=rgba(shelf), width=1)
        for row, top in enumerate((1, 10, 20)):
            x = 2
            while x < 30:
                c = book_cols[(x + row) % len(book_cols)]
                h = 6 + ((x + row) % 3)
                draw.rectangle([x, top + (8 - h), x + 2, top + 7], fill=rgba(c))
                x += 4
    if accent:
        draw = ImageDraw.Draw(img)
        draw.rectangle([7, 7, 16, 17], fill=rgba(darken(base, 0.35)))
        draw.rectangle([8, 8, 15, 16], fill=rgba(accent))
        draw.line([(8, 12), (15, 12)], fill=rgba(lighten(accent, 0.25)))
        draw.line([(11, 8), (11, 16)], fill=rgba(lighten(accent, 0.25)))
    return img


def prop_canvas():
    return Image.new("RGBA", (16, 16), (0, 0, 0, 0))


def make_tree():
    img = prop_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle([6, 10, 9, 15], fill=rgba((124, 82, 43)))
    d.rectangle([5, 11, 10, 13], fill=rgba((156, 104, 55)))
    d.ellipse([4, 1, 12, 8], fill=rgba((82, 160, 68)))
    d.ellipse([1, 5, 14, 12], fill=rgba((65, 140, 58)))
    d.ellipse([4, 3, 9, 7], fill=rgba((122, 197, 83)))
    return img


def simple_prop(name):
    img = prop_canvas()
    d = ImageDraw.Draw(img)
    if name == "bench":
        d.rectangle([2, 5, 13, 7], fill=rgba((166, 112, 63)))
        d.rectangle([2, 8, 13, 10], fill=rgba((189, 131, 73)))
        d.rectangle([3, 10, 4, 15], fill=rgba((94, 86, 78)))
        d.rectangle([11, 10, 12, 15], fill=rgba((94, 86, 78)))
    elif name == "table_cafe":
        d.ellipse([2, 3, 14, 8], fill=rgba((206, 151, 91)))
        d.rectangle([7, 7, 9, 14], fill=rgba((142, 91, 54)))
        d.rectangle([4, 13, 12, 15], fill=rgba((105, 75, 54)))
        d.rectangle([5, 1, 8, 4], fill=rgba((248, 241, 219)))
    elif name == "fountain":
        d.ellipse([1, 8, 15, 15], fill=rgba((142, 149, 160)))
        d.ellipse([3, 9, 13, 13], fill=rgba((91, 166, 213)))
        d.rectangle([6, 4, 10, 10], fill=rgba((172, 178, 185)))
        d.line([8, 0, 8, 5], fill=rgba((182, 224, 242)), width=1)
    elif name == "bookshelf":
        d.rectangle([1, 1, 14, 15], fill=rgba((111, 73, 42)))
        for y in (5, 10):
            d.line([1, y, 14, y], fill=rgba((77, 48, 31)))
        colors = [(185, 77, 70), (75, 137, 94), (71, 103, 170), (199, 162, 66)]
        for y in (2, 6, 11):
            for i, x in enumerate(range(2, 13, 3)):
                d.rectangle([x, y, x + 1, y + 3], fill=rgba(colors[(i + y) % 4]))
    elif name == "computer":
        d.rectangle([2, 1, 14, 10], fill=rgba((55, 64, 72)))
        d.rectangle([3, 2, 13, 8], fill=rgba((103, 183, 213)))
        d.rectangle([6, 10, 10, 12], fill=rgba((84, 90, 96)))
        d.rectangle([3, 13, 13, 15], fill=rgba((177, 183, 184)))
    elif name == "easel":
        d.rectangle([3, 1, 12, 9], fill=rgba((235, 224, 194)))
        d.rectangle([5, 3, 7, 5], fill=rgba((196, 92, 82)))
        d.rectangle([8, 5, 10, 7], fill=rgba((82, 152, 111)))
        d.line([4, 9, 2, 15], fill=rgba((142, 95, 55)), width=2)
        d.line([11, 9, 14, 15], fill=rgba((142, 95, 55)), width=2)
    elif name == "stove":
        d.rectangle([1, 3, 14, 15], fill=rgba((89, 90, 94)))
        d.rectangle([2, 4, 13, 6], fill=rgba((124, 126, 131)))
        for x in (4, 9):
            d.ellipse([x, 4, x + 3, 7], fill=rgba((42, 42, 45)))
        d.rectangle([3, 9, 12, 13], fill=rgba((55, 55, 60)))
    elif name == "lamp":
        d.rectangle([7, 4, 8, 14], fill=rgba((141, 136, 126)))
        d.rectangle([4, 2, 12, 5], fill=rgba((220, 180, 82)))
        d.rectangle([4, 13, 12, 15], fill=rgba((94, 88, 82)))
    elif name == "blackboard":
        d.rectangle([0, 0, 15, 15], fill=rgba((116, 78, 43)))
        d.rectangle([2, 2, 13, 12], fill=rgba((42, 92, 60)))
        for y in (4, 7, 10):
            d.line([4, y, 11, y], fill=rgba((225, 225, 208)))
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assets = {
        "grass": make_grass(),
        "path": make_path(),
        "water": make_water(),
        "floor_wood": make_floor_wood(),
        "floor_stone": make_floor_stone(),
        "floor_tile": make_floor_tile(),
        "wall_cafe": make_wall((190, 104, 77), (156, 205, 226), "brick"),
        "wall_library": make_wall((94, 112, 172), None, "books"),
        "wall_office": make_wall((102, 151, 169), None, "panel"),
        "wall_home": make_wall((213, 185, 134), (166, 204, 224), "brick"),
        "tree": make_tree(),
    }
    for name in ["bench", "table_cafe", "fountain", "bookshelf", "computer", "easel", "stove", "lamp", "blackboard"]:
        assets[name] = simple_prop(name)
    for name, img in assets.items():
        path = OUT / f"{name}.png"
        img.save(path)
        print(f"wrote {path} {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
