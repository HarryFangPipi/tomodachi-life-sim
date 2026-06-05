"""
Generate pixel-art sprite sheets for Tomodachi World characters.
Output: static/sprites/{id}.png  — 128×24 px, 8 frames wide
Frames 0-3: facing left-down (SW), frames 4-7: right-down (SE, mirrored)
Walk cycle: 0=stand, 1=right-foot-fwd, 2=stand, 3=left-foot-fwd
"""
from PIL import Image
import os

FRAME_W, FRAME_H = 16, 24
WALK_FRAMES = 4
TOTAL_FRAMES = 8          # 4 walk × 2 directions

CHARACTERS = [
    {"id": "alice", "hair": (204, 102, 119), "outfit": (204,  68, 170)},
    {"id": "bob",   "hair": ( 51,  68,  85), "outfit": ( 68, 102, 136)},
    {"id": "carol", "hair": (221, 170,  51), "outfit": (238, 102,  51)},
    {"id": "diana", "hair": (136,  68,  34), "outfit": (255, 255, 255)},
    {"id": "eve",   "hair": ( 85,  51, 136), "outfit": ( 51, 102,  68)},
]

SKIN  = (255, 204, 153)
PANTS = ( 44,  44,  66)
SHOES = ( 20,  16,  20)

def _a(c):
    return c + (255,) if len(c) == 3 else c

def lighten(c, f=1.25):
    return tuple(min(255, int(v * f)) for v in c[:3])

def darken(c, f=0.76):
    return tuple(max(0, int(v * f)) for v in c[:3])


def draw_frame(img: Image.Image, ox: int, hair, outfit, direction: int, walk: int, skin=SKIN):
    """
    Paint one 16×24 character frame into img at x-offset ox.
    direction 0 = left-down (SW)  |  direction 1 handled by caller (mirror)
    walk: 0=stand, 1=right-fwd, 2=stand, 3=left-fwd
    skin: RGB tuple for head/ears/hands (defaults to the shared SKIN tone)
    """
    px = img.load()
    W, H = img.size

    def put(x, y, c):
        nx = ox + x
        if 0 <= nx < W and 0 <= y < H:
            px[nx, y] = _a(c)

    def rect(x, y, w, h, c):
        c4 = _a(c)
        for dy in range(h):
            for dx in range(w):
                put(x + dx, y + dy, c4)

    # Walk leg offsets (±1 px vertical)
    if   walk == 1: r_dy, l_dy =  1, -1   # right foot forward
    elif walk == 3: r_dy, l_dy = -1,  1   # left foot forward
    else:           r_dy, l_dy =  0,  0   # standing

    # ── HAIR  y=0..3  ──────────────────────────────────────────
    # narrow top row, wide middle, narrow bottom
    rect(2,  0, 12, 1, hair)
    rect(1,  1, 14, 2, hair)
    rect(2,  3, 12, 1, hair)
    # side wisps (slightly darker)
    wdark = darken(hair, 0.80)
    put(1, 0, wdark);  put(14, 0, wdark)

    # ── HEAD  y=4..7  x=3..12 ──────────────────────────────────
    rect(3, 4, 10, 4, skin)
    # side ear hints
    put(2, 5, skin);  put(13, 5, skin)

    # Eyes  y=5  (2×1 px each, dark + highlight)
    EYE = (24, 20, 32)
    HL  = (210, 220, 240)
    # direction 0: eyes slightly left (SW facing)
    put(5, 5, EYE);   put(6, 5, HL)
    put(9, 5, EYE);   put(10, 5, HL)

    # Blush  y=6
    BL = (255, 165, 145, 160)
    put(4,  6, BL)
    put(11, 6, BL)

    # ── BODY  y=8..15  x=2..13 ─────────────────────────────────
    rect(2, 8, 12, 8, outfit)
    # Collar highlight (top row brighter)
    rect(2, 8, 12, 1, lighten(outfit, 1.20))
    # Bottom hem shadow
    rect(2, 15, 12, 1, darken(outfit, 0.88))

    # White outfit (Diana): button strip
    if outfit == (255, 255, 255):
        BTN = (190, 190, 198)
        for by in (9, 11, 13):
            rect(7, by, 2, 1, BTN)

    # ── ARMS  (1px wide, inset to x=1 / x=14 so the silhouette outline has a
    #    free column on each side) with a gentle contralateral walk swing ────
    arm_c = darken(outfit, 0.78)
    la_dy = -l_dy   # left arm swings opposite the left leg
    ra_dy = -r_dy   # right arm swings opposite the right leg
    rect(1, 9 + la_dy, 1, 5, arm_c)    # left arm  x=1
    rect(14, 9 + ra_dy, 1, 5, arm_c)   # right arm x=14
    # Hands (skin)
    rect(1, 13 + la_dy, 1, 2, skin)
    rect(14, 13 + ra_dy, 1, 2, skin)

    # ── LEGS  y=16..19 (with walk offset) ──────────────────────
    # Left leg x=4..6, Right leg x=9..11
    for dy in range(4):
        ly = 16 + dy + l_dy
        ry = 16 + dy + r_dy
        if 0 <= ly < H: rect(4, ly, 3, 1, PANTS)
        if 0 <= ry < H: rect(9, ry, 3, 1, PANTS)

    # ── SHOES  y=20..23 (follow legs, 1 px wider each side) ────
    for dy in range(4):
        ly = 20 + dy + l_dy
        ry = 20 + dy + r_dy
        if 0 <= ly < H: rect(3, ly, 4, 1, SHOES)
        if 0 <= ry < H: rect(8, ry, 4, 1, SHOES)

    # Shoe toe highlight (1 px lighter at top of shoe)
    shoe_hl = (60, 54, 64)
    sl = 20 + l_dy;  sr = 20 + r_dy
    if 0 <= sl < H: put(3, sl, shoe_hl);  put(6, sl, shoe_hl)
    if 0 <= sr < H: put(8, sr, shoe_hl);  put(11, sr, shoe_hl)


OUTLINE = (44, 34, 50, 255)   # Kairosoft-style dark silhouette outline

def add_outline(frame: Image.Image, color=OUTLINE):
    """Trace a 1px dark outline around the opaque silhouette of a single frame.
    Operates on a standalone FRAME_W×FRAME_H image so it never reads across
    into a neighbouring frame on the sheet."""
    px = frame.load()
    W, H = frame.size
    opaque = [[px[x, y][3] > 0 for y in range(H)] for x in range(W)]
    for x in range(W):
        for y in range(H):
            if opaque[x][y]:
                continue
            # 8-neighbour test → smoother corners than 4-neighbour
            hit = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H and opaque[nx][ny]:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                px[x, y] = color


def generate_sheet(char: dict) -> Image.Image:
    img = Image.new("RGBA", (FRAME_W * TOTAL_FRAMES, FRAME_H), (0, 0, 0, 0))
    hair, outfit = char["hair"], char["outfit"]
    skin = char.get("skin", SKIN)

    for w in range(WALK_FRAMES):
        # Build the SW frame on its own canvas, outline it, then place both the
        # SW frame and its mirrored SE copy (outline mirrors with the art).
        tmp = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
        draw_frame(tmp, 0, hair, outfit, 0, w, skin)
        add_outline(tmp)
        img.paste(tmp, (w * FRAME_W, 0))
        img.paste(tmp.transpose(Image.FLIP_LEFT_RIGHT), ((w + WALK_FRAMES) * FRAME_W, 0))

    return img


def hex_to_rgb(h):
    """'#FF6B6B' / 'FF6B6B' / '#F66' → (r, g, b). Falls back to grey."""
    h = (h or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return (160, 160, 160)


def save_sprite_for(agent_id, hair, outfit, skin=None, out_dir="static/sprites"):
    """Generate + save a sprite sheet for a dynamically-added resident.
    hair / outfit / skin are hex strings (e.g. '#FF6B6B'). Returns the path."""
    char = {
        "id": agent_id,
        "hair": hex_to_rgb(hair),
        "outfit": hex_to_rgb(outfit),
        "skin": hex_to_rgb(skin) if skin else SKIN,
    }
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{agent_id}.png")
    generate_sheet(char).save(path)
    return path


if __name__ == "__main__":
    os.makedirs("static/sprites", exist_ok=True)
    for char in CHARACTERS:
        sheet = generate_sheet(char)
        path = f"static/sprites/{char['id']}.png"
        sheet.save(path)
        print(f"  Saved {path}  ({sheet.size[0]}×{sheet.size[1]} px)")
    print("Done — all sprites generated.")
