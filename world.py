import json
import uuid
from pathlib import Path

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
# The default town is a fixed 3x4 block grid (rows 0-2, cols 0-3),
# anchored at the top-left corner (br=0, bc=0). The map editor can
# grow the grid towards the south/east by building new houses one
# block beyond the current edge — this never shifts the coordinates
# of existing blocks, so saves/agent positions never desync.
# ============================================================

N_BLOCK_COLS_DEFAULT = 4
N_BLOCK_ROWS_DEFAULT = 3
BLOCK_SIZE = 4    # interior tiles per block
ROAD_WIDTH = 2    # tiles of road between blocks
BORDER = 1        # outer road ring

TILE_GRASS = 0
TILE_PATH = 1
TILE_BUILDING = 2
TILE_TREE = 3
TILE_WATER = 4
TILE_FLOOR = 5
TILE_FLOWER = 6

OPAQUE_TILES = {TILE_BUILDING, TILE_TREE}

LAYOUT_PATH = Path(__file__).parent / "data" / "town_layout.json"

# Prefab house styles offered by the visual map editor.
HOUSE_STYLES = {
    "cabin":  {"label": "小木屋",     "color": "#8D6E63"},
    "pink":   {"label": "粉色甜屋",   "color": "#E91E63"},
    "blue":   {"label": "蓝色海景屋", "color": "#1E88E5"},
    "green":  {"label": "绿色田园屋", "color": "#43A047"},
    "yellow": {"label": "黄色暖阳屋", "color": "#FBC02D"},
    "purple": {"label": "紫色梦想屋", "color": "#8E24AA"},
}

# Block grid (row, col) -> location key. None means decorative/empty block.
#
#  row 0:  cafe     library   house_alice  house_bob
#  row 1:  park     square    office       house_carol
#  row 2:  house_eve  house_diana  grove1   apartment
_DEFAULT_BLOCK_ASSIGN = {
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

_DEFAULT_LABELS = {
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

# Mutable runtime state -----------------------------------------------------
_BLOCK_ASSIGN: dict = {}                 # (br, bc) -> key
_LABELS: dict = {}                       # key -> (label, color, kind)  kind: "fixed" | "house"
LOCATIONS: dict = {}                     # key -> {rect, center, label, color, kind}
MAP_COLS = 0
MAP_ROWS = 0


def _reset_to_defaults():
    _BLOCK_ASSIGN.clear()
    _BLOCK_ASSIGN.update(_DEFAULT_BLOCK_ASSIGN)
    _LABELS.clear()
    for k, (label, color) in _DEFAULT_LABELS.items():
        _LABELS[k] = (label, color, "fixed")


def load_layout():
    """Reset to the built-in 12-block town, then layer the saved custom
    blocks (built houses) on top, if a layout file exists on disk."""
    _reset_to_defaults()
    if LAYOUT_PATH.exists():
        try:
            data = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
            for pos, info in data.get("blocks", {}).items():
                br_s, bc_s = pos.split(",")
                br, bc = int(br_s), int(bc_s)
                key = info["key"]
                _BLOCK_ASSIGN[(br, bc)] = key
                _LABELS[key] = (info.get("label", key), info.get("color", "#888888"), "house")
        except Exception:
            pass
    recompute()


def save_layout():
    """Persist only the custom (non-default) blocks to disk."""
    blocks = {}
    for pos, key in _BLOCK_ASSIGN.items():
        if _DEFAULT_BLOCK_ASSIGN.get(pos) == key:
            continue
        label, color, kind = _LABELS.get(key, (key, "#888888", "house"))
        blocks[f"{pos[0]},{pos[1]}"] = {"key": key, "label": label, "color": color}
    LAYOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LAYOUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"blocks": blocks}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LAYOUT_PATH)


def _grid_size() -> tuple[int, int]:
    """Current (n_rows, n_cols) of the block grid, derived from whatever
    blocks are currently assigned, floored at the original town size."""
    if not _BLOCK_ASSIGN:
        return N_BLOCK_ROWS_DEFAULT, N_BLOCK_COLS_DEFAULT
    n_rows = max(br for br, bc in _BLOCK_ASSIGN) + 1
    n_cols = max(bc for br, bc in _BLOCK_ASSIGN) + 1
    return max(n_rows, N_BLOCK_ROWS_DEFAULT), max(n_cols, N_BLOCK_COLS_DEFAULT)


def _block_rect(br: int, bc: int) -> tuple[int, int, int, int]:
    """Return (x0, y0, x1, y1) inclusive coords of the 4x4 interior of block (br, bc).

    Anchored at (0,0) — growing the grid south/east never changes the
    coordinates of existing blocks.
    """
    x0 = BORDER + bc * (BLOCK_SIZE + ROAD_WIDTH)
    y0 = BORDER + br * (BLOCK_SIZE + ROAD_WIDTH)
    x1 = x0 + BLOCK_SIZE - 1
    y1 = y0 + BLOCK_SIZE - 1
    return (x0, y0, x1, y1)


def _block_center(br: int, bc: int) -> tuple[int, int]:
    x0, y0, x1, y1 = _block_rect(br, bc)
    return ((x0 + x1) // 2, (y0 + y1) // 2)


def recompute():
    """Rebuild MAP_COLS/MAP_ROWS and the LOCATIONS dict from _BLOCK_ASSIGN.

    Mutates LOCATIONS in place (clear + repopulate) rather than rebinding it,
    so the shared reference already imported by agents.py/game.py/persistence.py
    stays valid.
    """
    global MAP_COLS, MAP_ROWS
    n_rows, n_cols = _grid_size()
    MAP_COLS = BORDER + n_cols * BLOCK_SIZE + (n_cols - 1) * ROAD_WIDTH + BORDER
    MAP_ROWS = BORDER + n_rows * BLOCK_SIZE + (n_rows - 1) * ROAD_WIDTH + BORDER

    LOCATIONS.clear()
    for (br, bc), key in _BLOCK_ASSIGN.items():
        if key not in _LABELS:
            continue
        label, color, kind = _LABELS[key]
        x0, y0, x1, y1 = _block_rect(br, bc)
        LOCATIONS[key] = {
            "rect": (x0, y0, x1, y1),
            "center": _block_center(br, bc),
            "label": label,
            "color": color,
            "kind": kind,
        }


def build_map() -> list[list[int]]:
    """Build a Kairosoft-style block map.

    Every tile not inside a 4x4 block interior is a road (TILE_PATH).
    Block interiors are filled by type:
      - park       -> grass + trees + water pond
      - grove_*    -> grass + dense trees (decorative)
      - town_square-> floor + flower bed
      - house_*    -> outline of TILE_BUILDING with TILE_FLOOR inside
      - vacant lot (in-bounds, unassigned) -> grass (buildable)
    """
    recompute()
    n_rows, n_cols = _grid_size()
    grid = [[TILE_PATH] * MAP_COLS for _ in range(MAP_ROWS)]

    for br in range(n_rows):
        for bc in range(n_cols):
            key = _BLOCK_ASSIGN.get((br, bc))
            x0, y0, x1, y1 = _block_rect(br, bc)

            if key is None:
                # Vacant lot inside current bounds: plain buildable grass.
                for r in range(y0, y1 + 1):
                    for c in range(x0, x1 + 1):
                        grid[r][c] = TILE_GRASS
                continue

            if key == "park":
                for r in range(y0, y1 + 1):
                    for c in range(x0, x1 + 1):
                        grid[r][c] = TILE_GRASS
                for (cc, rr) in [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]:
                    grid[rr][cc] = TILE_TREE
                cx0, cx1 = x0 + 1, x0 + 2
                cy0, cy1 = y0 + 1, y0 + 2
                grid[cy0][cx0] = TILE_WATER
                grid[cy0][cx1] = TILE_WATER
                grid[cy1][cx0] = TILE_WATER
                grid[cy1][cx1] = TILE_WATER

            elif key.startswith("grove"):
                for r in range(y0, y1 + 1):
                    for c in range(x0, x1 + 1):
                        if (r + c) % 2 == 0:
                            grid[r][c] = TILE_TREE
                        else:
                            grid[r][c] = TILE_GRASS

            elif key == "town_square":
                for r in range(y0, y1 + 1):
                    for c in range(x0, x1 + 1):
                        grid[r][c] = TILE_FLOOR
                grid[y0 + 1][x0 + 1] = TILE_FLOWER
                grid[y0 + 1][x0 + 2] = TILE_FLOWER
                grid[y0 + 2][x0 + 1] = TILE_FLOWER
                grid[y0 + 2][x0 + 2] = TILE_FLOWER

            else:
                # Regular building (default or custom prefab house):
                # outline = TILE_BUILDING, interior = TILE_FLOOR
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


def is_opaque(grid: list[list[int]], c: int, r: int) -> bool:
    if c < 0 or c >= MAP_COLS or r < 0 or r >= MAP_ROWS:
        return True
    return grid[r][c] in OPAQUE_TILES


def has_line_of_sight(grid: list[list[int]], fc: float, fr: float, tc: float, tr: float) -> bool:
    """Return True when a straight sight line does not pass through opaque tiles."""
    if is_opaque(grid, int(round(fc)), int(round(fr))):
        return False
    if is_opaque(grid, int(round(tc)), int(round(tr))):
        return False

    dc = tc - fc
    dr = tr - fr
    dist = (dc**2 + dr**2) ** 0.5
    if dist == 0:
        return True

    steps = max(1, int(dist / 0.1))
    for i in range(1, steps):
        t = i / steps
        c = int(round(fc + dc * t))
        r = int(round(fr + dr * t))
        if is_opaque(grid, c, r):
            return False
    return True


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


# ============================================================
# MAP EDITOR API
# ============================================================

def block_grid_payload() -> tuple[dict, dict]:
    """Snapshot of every block (current bounds) plus a one-block "ghost" ring
    along the south & east edges marking where the town can expand to.
    Frontend uses this to render buildable/vacant overlays without needing
    to know the block-math itself."""
    n_rows, n_cols = _grid_size()
    payload = {}
    for br in range(n_rows):
        for bc in range(n_cols):
            key = _BLOCK_ASSIGN.get((br, bc))
            x0, y0, x1, y1 = _block_rect(br, bc)
            payload[f"{br},{bc}"] = {"key": key, "rect": [x0, y0, x1, y1], "ghost": False}
    for bc in range(n_cols):
        x0, y0, x1, y1 = _block_rect(n_rows, bc)
        payload[f"{n_rows},{bc}"] = {"key": None, "rect": [x0, y0, x1, y1], "ghost": True}
    for br in range(n_rows + 1):
        x0, y0, x1, y1 = _block_rect(br, n_cols)
        payload[f"{br},{n_cols}"] = {"key": None, "rect": [x0, y0, x1, y1], "ghost": True}
    return payload, {"n_rows": n_rows, "n_cols": n_cols}


def get_kind(key: str) -> str | None:
    info = _LABELS.get(key)
    return info[2] if info else None


def can_build_at(br: int, bc: int) -> bool:
    if br < 0 or bc < 0:
        return False
    n_rows, n_cols = _grid_size()
    if br > n_rows or bc > n_cols:
        return False
    if br == n_rows or bc == n_cols:
        return True  # exactly one ring beyond the edge -> auto-expand
    return _BLOCK_ASSIGN.get((br, bc)) is None  # vacant lot inside current bounds


def build_house(br: int, bc: int, style: str, label: str) -> str:
    if not can_build_at(br, bc):
        raise ValueError("not buildable")
    sty = HOUSE_STYLES.get(style, HOUSE_STYLES["cabin"])
    key = "house_" + uuid.uuid4().hex[:8]
    _BLOCK_ASSIGN[(br, bc)] = key
    _LABELS[key] = (label, sty["color"], "house")
    recompute()
    save_layout()
    return key


def remove_house(house_key: str) -> tuple[int, int] | None:
    info = _LABELS.get(house_key)
    if info is None or info[2] != "house":
        raise ValueError("not removable")
    pos = next((p for p, k in _BLOCK_ASSIGN.items() if k == house_key), None)
    if pos is None:
        return None
    del _BLOCK_ASSIGN[pos]
    del _LABELS[house_key]
    recompute()
    save_layout()
    return pos


def set_house_label(house_key: str, label: str):
    info = _LABELS.get(house_key)
    if info is None:
        raise KeyError(house_key)
    _, color, kind = info
    if kind != "house":
        raise ValueError("not a custom house")
    _LABELS[house_key] = (label, color, kind)
    recompute()
    save_layout()


load_layout()
