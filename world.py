import random

# ============================================================
# Kairosoft-style block layout
#
# Each block is 4x4 tiles of interior content, separated by a
# 2-tile wide road. There is a 1-tile road ring around the
# entire map.
#
# Block (br, bc) interior:
#     col range = [1 + bc*6,  1 + bc*6 + 3]   (inclusive, width 4)
#     row range = [1 + br*6,  1 + br*6 + 3]   (inclusive, height 4)
#
# Total map = 1 + (4+2)*N_COLS  + ... let's compute:
#     N_BLOCK_COLS = 4  -> width  = 1 + 6*4 - 2 + 1 = 24  (drop trailing road, keep 1-tile rim)
#     N_BLOCK_ROWS = 3  -> height = 1 + 6*3 - 2 + 1 = 18
# But for symmetry we add a 1-tile road on the far side too:
#     width  = 1 + 6*4 = 25 -> use 25
#     height = 1 + 6*3 = 19 -> use 19
# Adjusted: keep simple and pretty -> 25 x 19.
# ============================================================

N_BLOCK_COLS = 4
N_BLOCK_ROWS = 3
BLOCK_SIZE = 4    # interior tiles per block
ROAD_WIDTH = 2    # tiles of road between blocks
BORDER = 1        # outer road ring

MAP_COLS = BORDER + N_BLOCK_COLS * BLOCK_SIZE + (N_BLOCK_COLS - 1) * ROAD_WIDTH + BORDER  # 1+16+6+1 = 24
MAP_ROWS = BORDER + N_BLOCK_ROWS * BLOCK_SIZE + (N_BLOCK_ROWS - 1) * ROAD_WIDTH + BORDER  # 1+12+4+1 = 18

TILE_GRASS = 0
TILE_PATH = 1
TILE_BUILDING = 2
TILE_TREE = 3
TILE_WATER = 4
TILE_FLOOR = 5
TILE_FLOWER = 6


def _block_rect(br: int, bc: int) -> tuple[int, int, int, int]:
    """Return (x0, y0, x1, y1) inclusive coords of the 4x4 interior of block (br, bc)."""
    x0 = BORDER + bc * (BLOCK_SIZE + ROAD_WIDTH)
    y0 = BORDER + br * (BLOCK_SIZE + ROAD_WIDTH)
    x1 = x0 + BLOCK_SIZE - 1
    y1 = y0 + BLOCK_SIZE - 1
    return (x0, y0, x1, y1)


def _block_center(br: int, bc: int) -> tuple[int, int]:
    x0, y0, x1, y1 = _block_rect(br, bc)
    return ((x0 + x1) // 2, (y0 + y1) // 2)


# Block grid (row, col) -> location key. None means decorative/empty block.
#
#  row 0:  cafe     library   house_alice  house_bob
#  row 1:  park     square    office       house_carol
#  row 2:  house_eve  house_diana  grove1   apartment
_BLOCK_ASSIGN = {
    (0, 0): "cafe",
    (0, 1): "library",
    (0, 2): "house_alice",
    (0, 3): "house_bob",
    (1, 0): "park",
    (1, 1): "town_square",
    (1, 2): "office",
    (1, 3): "house_carol",
    (2, 0): "house_eve",
    (2, 1): "house_diana",
    (2, 2): "grove_a",   # decorative tree block
    (2, 3): "apartment",
}

_LABELS = {
    "cafe":        ("咖啡馆",    "#8B4513"),
    "library":     ("图书馆",    "#4682B4"),
    "house_alice": ("Alice家",  "#C71585"),
    "house_bob":   ("Bob家",    "#2196F3"),
    "park":        ("公园",      "#2E7D32"),
    "town_square": ("广场",      "#FFC107"),
    "office":      ("办公室",    "#607D8B"),
    "house_carol": ("Carol家",  "#FF9800"),
    "house_eve":   ("Eve家",    "#009688"),
    "house_diana": ("Diana家",  "#9C27B0"),
    "apartment":   ("公寓",      "#7E8AA2"),
}

# Build LOCATIONS dict from block assignments (only real locations, not groves)
LOCATIONS: dict = {}
for (br, bc), key in _BLOCK_ASSIGN.items():
    if key not in _LABELS:
        continue
    x0, y0, x1, y1 = _block_rect(br, bc)
    label, color = _LABELS[key]
    LOCATIONS[key] = {
        "rect": (x0, y0, x1, y1),
        "center": _block_center(br, bc),
        "label": label,
        "color": color,
    }


def build_map() -> list[list[int]]:
    """Build a Kairosoft-style block map.

    Every tile not inside a 4x4 block interior is a road (TILE_PATH).
    Block interiors are filled by type:
      - park       -> grass + trees + water pond
      - grove_*    -> grass + dense trees (decorative)
      - all others -> outline of TILE_BUILDING with TILE_FLOOR inside
    """
    # Start with everything as road.
    grid = [[TILE_PATH] * MAP_COLS for _ in range(MAP_ROWS)]

    # Carve out each block interior.
    for (br, bc), key in _BLOCK_ASSIGN.items():
        x0, y0, x1, y1 = _block_rect(br, bc)

        if key == "park":
            # Grass base, sprinkle trees on the edges, water pond in center.
            for r in range(y0, y1 + 1):
                for c in range(x0, x1 + 1):
                    grid[r][c] = TILE_GRASS
            # Trees on the four corners
            for (cc, rr) in [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]:
                grid[rr][cc] = TILE_TREE
            # Water pond in the middle 2x2
            cx0, cx1 = x0 + 1, x0 + 2
            cy0, cy1 = y0 + 1, y0 + 2
            grid[cy0][cx0] = TILE_WATER
            grid[cy0][cx1] = TILE_WATER
            grid[cy1][cx0] = TILE_WATER
            grid[cy1][cx1] = TILE_WATER

        elif key.startswith("grove"):
            # Decorative tree block: grass + checkerboard trees
            for r in range(y0, y1 + 1):
                for c in range(x0, x1 + 1):
                    if (r + c) % 2 == 0:
                        grid[r][c] = TILE_TREE
                    else:
                        grid[r][c] = TILE_GRASS

        elif key == "town_square":
            # Plaza: floor tiles all over, a flower bed in the center.
            for r in range(y0, y1 + 1):
                for c in range(x0, x1 + 1):
                    grid[r][c] = TILE_FLOOR
            # Flower decorations in middle
            grid[y0 + 1][x0 + 1] = TILE_FLOWER
            grid[y0 + 1][x0 + 2] = TILE_FLOWER
            grid[y0 + 2][x0 + 1] = TILE_FLOWER
            grid[y0 + 2][x0 + 2] = TILE_FLOWER

        else:
            # Regular building: outline = TILE_BUILDING, interior = TILE_FLOOR
            for r in range(y0, y1 + 1):
                for c in range(x0, x1 + 1):
                    if r == y0 or r == y1 or c == x0 or c == x1:
                        grid[r][c] = TILE_BUILDING
                    else:
                        grid[r][c] = TILE_FLOOR

    return grid


def is_walkable(grid: list[list[int]], c: int, r: int) -> bool:
    if c < 0 or c >= MAP_COLS or r < 0 or r >= MAP_ROWS:
        return False
    return grid[r][c] in (TILE_PATH, TILE_FLOOR, TILE_GRASS, TILE_FLOWER)


def step_toward(grid, fc: float, fr: float, tc: int, tr: int) -> tuple[float, float]:
    """Move one step (0.18 tile/tick) from (fc,fr) toward (tc,tr)."""
    dc = tc - fc
    dr = tr - fr
    dist = (dc**2 + dr**2) ** 0.5
    if dist < 0.2:
        return float(tc), float(tr)
    speed = 0.18
    nc = fc + dc / dist * speed
    nr = fr + dr / dist * speed
    return nc, nr


def location_for_pos(c: float, r: float):
    for name, loc in LOCATIONS.items():
        x0, y0, x1, y1 = loc["rect"]
        if x0 <= c <= x1 and y0 <= r <= y1:
            return name
    return None
