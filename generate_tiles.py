"""
Generate pixel-art tile/prop PNGs for Tomodachi World.
Output: static/tiles/*.png

Ground/floor tiles: 64×32 px, diamond-clipped (isometric top face)
Facade textures:    32×32 px, rectangular
Props:              16×16 px, transparent background
"""
from PIL import Image, ImageDraw
import math, os

TW, TH = 64, 32   # tile bounding box

# ── helpers ────────────────────────────────────────────────────────────────

def _a(c):
    return c + (255,) if len(c) == 3 else c

def lighten(c, f=1.20):
    return tuple(min(255, int(v * f)) for v in c[:3])

def darken(c, f=0.78):
    return tuple(max(0, int(v * f)) for v in c[:3])

def blend(c1, c2, t=0.5):
    return tuple(int(c1[i]*(1-t)+c2[i]*t) for i in range(3))

def in_diamond(x, y, w=TW, h=TH):
    """True if pixel (x,y) is inside the isometric diamond."""
    cx, cy = w/2, h/2
    return abs(x - cx)/cx + abs(y - cy)/cy <= 1.0

def diamond_mask(w=TW, h=TH):
    """Return an RGBA Image that's white inside the diamond, transparent outside."""
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = mask.load()
    for y in range(h):
        for x in range(w):
            if in_diamond(x + 0.5, y + 0.5, w, h):
                px[x, y] = (255, 255, 255, 255)
    return mask

def new_tile(w=TW, h=TH):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))

def apply_diamond_clip(img):
    """Zero out alpha outside the isometric diamond."""
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            if not in_diamond(x + 0.5, y + 0.5, w, h):
                px[x, y] = (0, 0, 0, 0)

def rect(img, x, y, w, h, c):
    px = img.load()
    iw, ih = img.size
    c4 = _a(c)
    for dy in range(h):
        for dx in range(w):
            nx, ny = x+dx, y+dy
            if 0 <= nx < iw and 0 <= ny < ih:
                px[nx, ny] = c4

def hline(img, x0, x1, y, c):
    px = img.load()
    iw, ih = img.size
    c4 = _a(c)
    for x in range(x0, x1+1):
        if 0 <= x < iw and 0 <= y < ih:
            px[x, y] = c4

def put(img, x, y, c):
    px = img.load()
    iw, ih = img.size
    if 0 <= x < iw and 0 <= y < ih:
        px[x, y] = _a(c)


# ══════════════════════════════════════════════════════════════════════════
# GROUND TILES  (64×32, diamond-clipped)
# ══════════════════════════════════════════════════════════════════════════

def make_grass():
    img = new_tile()
    BASE  = (126, 200,  80)
    D1    = ( 96, 160,  56)   # darker blade shadow
    L1    = (160, 224, 100)   # lighter highlight
    px = img.load()
    # Fill base
    for y in range(TH):
        for x in range(TW):
            if in_diamond(x+.5, y+.5):
                px[x, y] = _a(BASE)
    # Grass strokes — short vertical dashes, scattered
    import random; rng = random.Random(42)
    for _ in range(120):
        gx = rng.randint(1, TW-2)
        gy = rng.randint(1, TH-2)
        if not in_diamond(gx+.5, gy+.5): continue
        c = D1 if rng.random() < 0.5 else L1
        if in_diamond(gx+.5, gy-.5):
            px[gx, gy-1] = _a(c)
        px[gx, gy] = _a(darken(c, 0.85))
    apply_diamond_clip(img)
    return img

def make_path():
    img = new_tile()
    BASE  = (200, 168, 120)
    DARK  = (160, 128,  88)
    LIGHT = (220, 196, 156)
    MORTAR= (140, 108,  72)
    px = img.load()
    # Fill base
    for y in range(TH):
        for x in range(TW):
            if in_diamond(x+.5, y+.5):
                px[x, y] = _a(BASE)
    # Staggered brick pattern: bricks 8px wide × 4px tall in screen space
    BW, BH2 = 8, 4
    for row2 in range(TH // BH2 + 1):
        off = (row2 % 2) * (BW // 2)
        # mortar horizontal line
        my = row2 * BH2
        for x in range(TW):
            if in_diamond(x+.5, my+.5):
                px[x, min(my, TH-1)] = _a(MORTAR)
        # mortar vertical lines
        for bx in range(-(BW//2), TW, BW):
            vx = bx + off
            for dy in range(BH2):
                ny = my + dy
                if 0<=vx<TW and 0<=ny<TH and in_diamond(vx+.5, ny+.5):
                    px[vx, ny] = _a(MORTAR)
        # brick face highlight top-left
        for bx in range(-(BW//2), TW, BW):
            vx = bx + off + 1
            hy = my + 1
            if 0<=vx<TW-1 and 0<=hy<TH and in_diamond(vx+.5, hy+.5):
                px[vx, hy] = _a(LIGHT)
    apply_diamond_clip(img)
    return img

def make_water():
    img = new_tile()
    BASE  = ( 68, 136, 204)
    DARK  = ( 44,  96, 164)
    LIGHT = (120, 188, 240)
    FOAM  = (180, 220, 255)
    px = img.load()
    for y in range(TH):
        for x in range(TW):
            if in_diamond(x+.5, y+.5):
                px[x, y] = _a(BASE)
    # Sine-wave ripples across x, 3 waves
    for wave in range(3):
        phase = wave * 8
        for x in range(TW):
            wy = int(TH//2 + (TH//4)*math.sin((x + phase) * math.pi / 10))
            for dy in range(-1, 2):
                ny = wy + dy
                c = FOAM if dy == 0 else LIGHT
                if 0<=ny<TH and in_diamond(x+.5, ny+.5):
                    px[x, ny] = _a(c)
    # Darker depth below center
    for y in range(TH//2+2, TH):
        for x in range(TW):
            if in_diamond(x+.5, y+.5):
                old = px[x, y]
                px[x, y] = _a(darken(old[:3], 0.88))
    apply_diamond_clip(img)
    return img


# ══════════════════════════════════════════════════════════════════════════
# FLOOR / ROOF TILES  (64×32, diamond-clipped)
# ══════════════════════════════════════════════════════════════════════════

def make_floor_wood():
    img = new_tile()
    BASE  = (200, 120,  64)
    LIGHT = (224, 152,  88)
    DARK  = (160,  88,  40)
    GRAIN = (176, 104,  52)
    px = img.load()
    for y in range(TH):
        for x in range(TW):
            if in_diamond(x+.5, y+.5):
                px[x, y] = _a(BASE)
    # Plank stripes: diagonal lines parallel to isometric x-axis (slope -1/2)
    # In screen space, isometric planks run along row direction (top-left→bottom-right: slope +0.5)
    # We'll draw horizontal bands of planks 4px high, alternating light/dark
    for y in range(TH):
        band = (y // 4) % 3
        c = LIGHT if band == 0 else (GRAIN if band == 1 else DARK)
        for x in range(TW):
            if in_diamond(x+.5, y+.5):
                px[x, y] = _a(c)
    # Grain lines within each plank (single-pixel darker line)
    for y in range(0, TH, 4):
        gy = y + 2
        if gy < TH:
            for x in range(TW):
                if in_diamond(x+.5, gy+.5):
                    old = px[x, gy]
                    px[x, gy] = _a(darken(old[:3], 0.82))
    # Plank seams (horizontal, every 4 rows)
    for y in range(0, TH, 4):
        for x in range(TW):
            if in_diamond(x+.5, y+.5):
                px[x, y] = _a(DARK)
    apply_diamond_clip(img)
    return img

def make_floor_stone():
    img = new_tile()
    BASE   = (160, 160, 176)
    LIGHT  = (192, 192, 208)
    MORTAR = (112, 112, 128)
    DARK   = (128, 128, 144)
    px = img.load()
    for y in range(TH):
        for x in range(TW):
            if in_diamond(x+.5, y+.5):
                px[x, y] = _a(BASE)
    # Offset stone blocks 8×5 px
    BW, BH2 = 8, 5
    for row2 in range(TH // BH2 + 2):
        off = (row2 % 2) * (BW // 2)
        my = row2 * BH2
        for x in range(TW):
            if in_diamond(x+.5, min(my,TH-1)+.5):
                px[x, min(my, TH-1)] = _a(MORTAR)
        for bx in range(-(BW//2), TW+BW, BW):
            vx = bx + off
            for dy in range(1, BH2):
                ny = my + dy
                if 0<=vx<TW and 0<=ny<TH and in_diamond(vx+.5, ny+.5):
                    px[vx, ny] = _a(MORTAR)
            # Stone face shading: top-left lighter, bottom-right darker
            for dy in range(1, BH2):
                ny = my + dy
                hx = vx + 1
                if 0<=hx<TW and 0<=ny<TH and in_diamond(hx+.5, ny+.5):
                    px[hx, ny] = _a(LIGHT if dy <= BH2//2 else DARK)
    apply_diamond_clip(img)
    return img

def make_floor_tile():
    img = new_tile()
    C1 = (216, 208, 184)
    C2 = (184, 176, 152)
    JOINT = (152, 144, 120)
    px = img.load()
    # Checkerboard 4×4 tiles with joints
    SZ = 4
    for y in range(TH):
        for x in range(TW):
            if not in_diamond(x+.5, y+.5): continue
            # joint lines every SZ px
            if x % SZ == 0 or y % SZ == 0:
                px[x, y] = _a(JOINT)
            else:
                c = C1 if ((x//SZ)+(y//SZ)) % 2 == 0 else C2
                # Slight highlight top-left within each cell
                xi, yi = x % SZ, y % SZ
                if xi == 1 and yi == 1:
                    c = lighten(c, 1.12)
                px[x, y] = _a(c)
    apply_diamond_clip(img)
    return img


# ══════════════════════════════════════════════════════════════════════════
# FACADE TEXTURES  (32×32, rectangular — used as wall texture)
# ══════════════════════════════════════════════════════════════════════════

def make_wall_cafe():
    """Terracotta brick wall with arched window."""
    img = new_tile(32, 32)
    BASE   = (204,  85,  51)
    MORTAR = (140,  56,  32)
    LIGHT  = (224, 120,  80)
    BW, BH2 = 8, 4
    for y in range(32):
        for x in range(32):
            if y % BH2 == 0 or x % BW == ((y//BH2)%2)*(BW//2):
                img.load()[x,y] = _a(MORTAR)
            else:
                c = LIGHT if (x % BW == 1 and y % BH2 == 1) else BASE
                img.load()[x,y] = _a(c)
    # Simple window: white rect with blue pane
    rect(img,  8,  6, 8, 10, (220, 200, 170))  # frame
    rect(img,  9,  7, 6,  8, (140, 180, 220))  # glass
    hline(img, 9, 14, 11, (100, 140, 180))     # horizontal divider
    return img

def make_wall_library():
    """Blue wall with colorful book spines."""
    img = new_tile(32, 32)
    BASE = ( 68,  85, 187)
    DARK = ( 44,  56, 140)
    px = img.load()
    for y in range(32):
        for x in range(32):
            px[x,y] = _a(BASE)
    # Shelf lines
    for sy in (8, 18, 28):
        hline(img, 0, 31, sy, DARK)
    # Book spines (4px wide, various heights)
    BOOK_COLORS = [
        (220, 60, 60), (60, 180, 60), (220, 200, 60),
        (200, 80, 200), (60, 200, 200), (240, 140, 40),
        (180, 220, 80), (100, 100, 220),
    ]
    for shelf_top, shelf_bot in [(0,8),(9,18),(19,28)]:
        bh = shelf_bot - shelf_top - 1
        bx = 1
        bi = 0
        while bx < 30:
            bw = 3 + (bi % 2)
            c = BOOK_COLORS[bi % len(BOOK_COLORS)]
            rect(img, bx, shelf_top+1, bw, bh-1, c)
            # spine title stripe
            hline(img, bx+1, bx+bw-2, shelf_top+2, lighten(c,1.3))
            bx += bw + 1
            bi += 1
    return img

def make_wall_office():
    """Glass curtain wall — reflective blue panels."""
    img = new_tile(32, 32)
    BASE   = ( 68, 136, 170)
    FRAME  = ( 32,  64,  96)
    GLASS1 = ( 96, 172, 216)
    GLASS2 = ( 52, 108, 164)
    REFL   = (180, 220, 240)
    px = img.load()
    for y in range(32):
        for x in range(32):
            px[x,y] = _a(BASE)
    # Panel grid: 8×8 panels with 2px frames
    PW, PH2 = 8, 8
    for y in range(32):
        for x in range(32):
            lx = x % PW; ly = y % PH2
            if lx == 0 or ly == 0:
                px[x,y] = _a(FRAME)
            else:
                c = GLASS1 if (lx+ly < PW//2+PH2//2) else GLASS2
                if lx == 1 and ly == 1:
                    c = REFL
                px[x,y] = _a(c)
    return img

def make_wall_home():
    """Cream brick wall with small window."""
    img = new_tile(32, 32)
    BASE   = (221, 204, 153)
    MORTAR = (176, 152, 104)
    LIGHT  = (240, 224, 180)
    BW, BH2 = 8, 4
    px = img.load()
    for y in range(32):
        for x in range(32):
            off = ((y//BH2) % 2) * (BW//2)
            if y % BH2 == 0 or (x + off) % BW == 0:
                px[x,y] = _a(MORTAR)
            else:
                c = LIGHT if ((x+off)%BW == 1 and y%BH2 == 1) else BASE
                px[x,y] = _a(c)
    # Window
    rect(img, 6, 6, 10, 12, (200, 180, 140))   # frame
    rect(img, 7, 7,  8, 10, (160, 200, 230))   # glass
    hline(img, 7, 14, 12, (120, 160, 190))     # horizontal bar
    put(img, 11, 7, (200, 230, 250))            # reflection dot
    return img


# ══════════════════════════════════════════════════════════════════════════
# PROPS  (16×16, transparent background)
# ══════════════════════════════════════════════════════════════════════════

def make_tree():
    img = new_tile(16, 16)
    TRUNK = (120,  72,  32)
    G1    = ( 48, 160,  48)
    G2    = ( 32, 120,  32)
    G3    = ( 72, 200,  72)
    # Trunk
    rect(img, 6, 11, 4, 5, TRUNK)
    # Three canopy layers (triangular)
    for row2, (y0, x0, xw) in enumerate([(0,5,6),(3,3,10),(6,1,14)]):
        c = G1 if row2==0 else (G2 if row2==1 else G3)
        for dy in range(4):
            w2 = max(1, xw - dy*2)
            xst = x0 + dy
            rect(img, xst, y0+dy, w2, 1, c)
    # Highlight blobs
    put(img, 6, 1, G3); put(img, 9, 2, G3)
    return img

def make_bench():
    img = new_tile(16, 16)
    WOOD  = (160, 100,  48)
    DARK  = (100,  60,  24)
    METAL = (140, 140, 160)
    # Seat planks (isometric top)
    rect(img,  2, 7, 12, 2, WOOD)
    hline(img, 2, 13, 7, lighten(WOOD, 1.2))
    # Back rest
    rect(img,  2, 4, 12, 2, WOOD)
    # Legs
    rect(img,  2,  9, 2, 5, METAL)
    rect(img, 12,  9, 2, 5, METAL)
    # Feet
    rect(img,  1, 13, 3, 2, DARK)
    rect(img, 12, 13, 3, 2, DARK)
    return img

def make_table_cafe():
    img = new_tile(16, 16)
    TOP  = (200, 160, 120)
    LEG  = (160, 120,  80)
    ITEM = (220,  80,  60)   # tiny coffee cup
    # Table top
    rect(img, 2, 4, 12, 3, TOP)
    hline(img, 2, 13, 4, lighten(TOP, 1.2))
    # Single center leg
    rect(img, 7, 7, 2, 7, LEG)
    # Base
    rect(img, 4, 13, 8, 2, darken(LEG, 0.8))
    # Coffee mug on top
    rect(img, 5, 2, 3, 3, (240, 240, 235))
    rect(img, 5, 2, 3, 1, (200, 200, 200))
    put(img, 6, 3, ITEM)
    return img

def make_fountain():
    img = new_tile(16, 16)
    STONE = (160, 160, 180)
    WATER_F = ( 80, 160, 220)
    SPLASH = (180, 220, 255)
    DARK  = (100, 100, 120)
    # Basin outer
    rect(img, 1, 8, 14, 6, STONE)
    # Basin inner water
    rect(img, 3, 9, 10, 4, WATER_F)
    # Center pedestal
    rect(img, 6, 4, 4, 5, STONE)
    rect(img, 7, 4, 2, 5, lighten(STONE, 1.15))
    # Spray
    put(img, 8, 2, SPLASH); put(img, 7, 1, SPLASH); put(img, 9, 1, SPLASH)
    put(img, 6, 3, SPLASH); put(img, 10, 3, SPLASH)
    put(img, 8, 0, WATER_F)
    # Shadow
    hline(img, 2, 13, 13, DARK)
    return img

def make_bookshelf():
    img = new_tile(16, 16)
    SHELF = (140,  90,  40)
    DARK  = ( 90,  55,  20)
    COLORS = [(220,60,60),(60,180,60),(60,60,220),(220,200,60),(180,60,200)]
    # Shelf unit outline
    rect(img, 1, 1, 14, 14, SHELF)
    rect(img, 2, 2, 12, 12, (30, 20, 10))  # dark back
    # Horizontal shelves
    for sy in (6, 10):
        hline(img, 1, 14, sy, DARK)
    # Books on 3 shelves
    for shelf_y in (2, 7, 11):
        bx = 2; bi = 0
        while bx < 14:
            bw = 2 + bi%2
            rect(img, bx, shelf_y+1, bw, 3, COLORS[bi%len(COLORS)])
            bx += bw; bi += 1
    return img

def make_computer():
    img = new_tile(16, 16)
    CASE  = ( 80,  88, 100)
    SCRN  = ( 20, 180, 220)
    DARK  = ( 40,  44,  52)
    LIGHT = (160, 172, 190)
    # Monitor
    rect(img, 2, 1, 12, 9, DARK)
    rect(img, 3, 2, 10, 7, SCRN)
    # Screen content (simple window)
    rect(img, 4, 3, 8, 1, (40,120,220))
    rect(img, 4, 4, 8, 4, (200,220,240))
    # Stand
    rect(img, 6, 10, 4, 2, CASE)
    # Base
    rect(img, 3, 12, 10, 2, CASE)
    hline(img, 3, 12, 12, LIGHT)
    # Keyboard
    rect(img, 3, 14, 10, 2, LIGHT)
    hline(img, 4, 11, 14, DARK)
    return img

def make_easel():
    img = new_tile(16, 16)
    WOOD  = (160, 120,  72)
    CANVAS= (245, 240, 225)
    PAINT = [(220,60,60),(60,160,220),(80,200,80),(220,200,60)]
    # Canvas board
    rect(img, 3, 1, 10, 9, (200, 190, 170))
    rect(img, 4, 2,  8, 7, CANVAS)
    # Simple painting on canvas
    rect(img, 5, 3, 2, 2, PAINT[0])
    rect(img, 8, 3, 2, 2, PAINT[1])
    rect(img, 5, 6, 2, 2, PAINT[2])
    rect(img, 8, 6, 2, 2, PAINT[3])
    # Legs
    rect(img,  3, 9, 2, 7, WOOD)
    rect(img, 11, 9, 2, 7, WOOD)
    rect(img,  7,10, 2, 4, WOOD)   # back support
    # Foot spread
    put(img,  1, 15, WOOD); put(img,  2, 15, WOOD)
    put(img, 13, 15, WOOD); put(img, 14, 15, WOOD)
    return img

def make_stove():
    img = new_tile(16, 16)
    BODY  = ( 80,  80,  90)
    TOP   = (100, 100, 112)
    BURNER= ( 40,  40,  48)
    HOT   = (220, 100,  40)
    KNOB  = (200, 200, 210)
    # Body
    rect(img, 1, 3, 14, 12, BODY)
    # Top surface
    rect(img, 1, 3, 14,  3, TOP)
    # Four burners
    for bx, by in ((3,4),(9,4),(3,7),(9,7)):
        rect(img, bx, by, 3, 3, BURNER)
        put(img, bx+1, by+1, HOT)
    # Front panel — oven door
    rect(img, 2, 8, 12, 6, darken(BODY, 0.85))
    rect(img, 3, 9, 10, 4, (50,50,60))
    # Knobs
    for kx in (3, 7, 11):
        put(img, kx, 6, KNOB)
    return img

def make_lamp():
    img = new_tile(16, 16)
    GOLD  = (220, 180,  60)
    METAL = (160, 160, 176)
    GLOW  = (255, 240, 180, 200)
    DARK  = ( 80,  80,  96)
    # Pole
    rect(img, 7, 3, 2, 12, METAL)
    # Base
    rect(img, 4, 13, 8, 3, DARK)
    hline(img, 4, 11, 13, METAL)
    # Lamp shade
    rect(img, 4, 1, 8, 4, GOLD)
    hline(img, 4, 11, 1, lighten(GOLD, 1.3))
    hline(img, 4, 11, 4, darken(GOLD, 0.7))
    # Glow (semi-transparent ellipse suggestion)
    for gx, gy in ((6,2),(7,2),(8,2),(7,3)):
        put(img, gx, gy, GLOW)
    return img

def make_blackboard():
    img = new_tile(16, 16)
    FRAME = (120,  80,  40)
    BOARD = ( 28,  72,  44)
    CHALK = (230, 230, 220)
    LEDGE = (100,  64,  28)
    # Frame border
    rect(img, 0, 0, 16, 16, FRAME)
    # Board surface
    rect(img, 2, 2, 12, 11, BOARD)
    # Chalk text lines (squiggly)
    for cy in (4, 7, 10):
        hline(img, 3, 12, cy, CHALK)
        # erase some pixels for squiggle effect
        for ex in (5, 8, 11):
            if 3<=ex<=12:
                put(img, ex, cy, BOARD)
    # Chalk tray
    rect(img, 2, 13, 12, 2, LEDGE)
    # Chalk pieces on tray
    put(img, 4, 13, (240,240,230))
    put(img, 7, 13, (240,220,180))
    put(img, 10,13, (220,240,230))
    return img


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

GENERATORS = [
    # ground tiles
    ("grass",        make_grass),
    ("path",         make_path),
    ("water",        make_water),
    # floor/roof tiles
    ("floor_wood",   make_floor_wood),
    ("floor_stone",  make_floor_stone),
    ("floor_tile",   make_floor_tile),
    # facade textures
    ("wall_cafe",    make_wall_cafe),
    ("wall_library", make_wall_library),
    ("wall_office",  make_wall_office),
    ("wall_home",    make_wall_home),
    # props
    ("tree",         make_tree),
    ("bench",        make_bench),
    ("table_cafe",   make_table_cafe),
    ("fountain",     make_fountain),
    ("bookshelf",    make_bookshelf),
    ("computer",     make_computer),
    ("easel",        make_easel),
    ("stove",        make_stove),
    ("lamp",         make_lamp),
    ("blackboard",   make_blackboard),
]

if __name__ == "__main__":
    os.makedirs("static/tiles", exist_ok=True)
    for name, fn in GENERATORS:
        img = fn()
        path = f"static/tiles/{name}.png"
        img.save(path)
        print(f"  {path}  {img.size[0]}×{img.size[1]}")
    print(f"Done — {len(GENERATORS)} assets generated.")
