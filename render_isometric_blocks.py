#!/usr/bin/env python3
"""
render_isometric_blocks.py  —  rendu isométrique + progression

Usage :
  python3 render_isometric_blocks.py <blocks_dir> <out_dir> [--size 128]

Exemples :
  python3 render_isometric_blocks.py ~/atm10-textures/blocks ~/atm10-iso --size 160
"""

import argparse
from pathlib import Path
import re
from PIL import Image, ImageEnhance
# ------------------ Utils ------------------

PNG_EXTS = (".png",)

TOP_KEYS = ("top", "up", "upper")
BOTTOM_KEYS = ("bottom", "down", "lower")
SIDE_KEYS = ("side", "sides")
FACE_KEYS = {
    "north": ("north",),
    "south": ("south",),
    "east":  ("east",),
    "west":  ("west",),
}

def load_png(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")

def nearest_resize(img: Image.Image, w: int, h: int) -> Image.Image:
    return img.resize((w, h), resample=Image.NEAREST)

def brighten(img: Image.Image, factor: float) -> Image.Image:
    return ImageEnhance.Brightness(img).enhance(factor) if factor != 1.0 else img

def alpha_composite(dest: Image.Image, src: Image.Image, offset):
    tmp = Image.new("RGBA", dest.size, (0,0,0,0))
    tmp.paste(src, offset, src)
    return Image.alpha_composite(dest, tmp)

def pick_by_keys(base_stem_to_path, keys):
    for stem, p in base_stem_to_path.items():
        for k in keys:
            if re.search(rf"(^|[_\-]){k}([_\-]|$)", stem):
                return p
    return None

def find_faces(textures):
    """textures: dict[stem -> Path]  → retourne dict top/bottom/left/right"""
    faces = {"top": None, "bottom": None, "left": None, "right": None}
    top_tex    = pick_by_keys(textures, TOP_KEYS)
    bottom_tex = pick_by_keys(textures, BOTTOM_KEYS)
    side_tex   = pick_by_keys(textures, SIDE_KEYS)

    north = pick_by_keys(textures, FACE_KEYS["north"])
    south = pick_by_keys(textures, FACE_KEYS["south"])
    east  = pick_by_keys(textures, FACE_KEYS["east"])
    west  = pick_by_keys(textures, FACE_KEYS["west"])

    faces["top"] = top_tex
    faces["bottom"] = bottom_tex

    if side_tex:
        faces["left"]  = side_tex
        faces["right"] = side_tex
    else:
        faces["left"]  = west or south or east or north
        faces["right"] = east or north or west or south

    if not any(faces.values()):
        any_tex = next(iter(textures.values()))
        faces = {"top": any_tex, "bottom": any_tex, "left": any_tex, "right": any_tex}

    base_tex = faces["top"] or faces["left"] or faces["right"] or faces["bottom"]
    for k in faces:
        if faces[k] is None:
            faces[k] = base_tex
    return faces

def make_iso_cube(top_img, left_img, right_img, size=128):
    top = nearest_resize(top_img, size, size)
    left = nearest_resize(left_img, size, size)
    right = nearest_resize(right_img, size, size)

    top_rot = top.rotate(45, resample=Image.NEAREST, expand=True)
    top_w, top_h = top_rot.size
    top_iso = nearest_resize(top_rot, top_w, max(1, int(top_h * 0.5)))

    shear_left = -0.5
    scale_y = 0.5
    left_w, left_h = left.size
    new_w = int(left_w + abs(shear_left) * left_h)
    new_h = int(left_h * scale_y)
    left_iso = left.transform((new_w, new_h), Image.AFFINE,
                              (1, shear_left, 0, 0, scale_y, 0),
                              resample=Image.NEAREST)
    left_iso = brighten(left_iso, 0.92)

    shear_right = +0.5
    right_w, right_h = right.size
    new_w = int(right_w + abs(shear_right) * right_h)
    new_h = int(right_h * scale_y)
    right_iso = right.transform((new_w, new_h), Image.AFFINE,
                                (1, shear_right, 0, 0, scale_y, 0),
                                resample=Image.NEAREST)
    right_iso = brighten(right_iso, 0.82)

    canvas_w = top_iso.width + left_iso.width + right_iso.width
    canvas_h = top_iso.height + max(left_iso.height, right_iso.height)
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0,0,0,0))

    top_x = (canvas_w - top_iso.width) // 2
    top_y = 0
    left_x = top_x - left_iso.width // 2
    left_y = top_iso.height - 1
    right_x = top_x + top_iso.width - right_iso.width // 2
    right_y = top_iso.height - 1

    canvas = alpha_composite(canvas, left_iso, (left_x, left_y))
    canvas = alpha_composite(canvas, right_iso, (right_x, right_y))
    canvas = alpha_composite(canvas, top_iso, (top_x, top_y))

    bbox = canvas.getbbox()
    if bbox:
        canvas = canvas.crop(bbox)
    return canvas

def collect_textures_in_moddir(moddir: Path):
    """Retourne {stem -> Path} pour toutes les PNG d'un mod, sans *.png.mcmeta."""
    textures = {}
    for p in sorted(moddir.rglob("*.png")):
        if p.name.endswith(".png.mcmeta"):
            continue
        textures[p.stem.lower()] = p
    return textures

# ------------------ Main ------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("blocks_dir", help="Dossier racine des textures blocs (ex: ~/atm10-textures/blocks)")
    ap.add_argument("out_dir", help="Dossier de sortie pour les rendus isométriques .png")
    ap.add_argument("--size", type=int, default=128, help="Taille de base de la texture (défaut: 128)")
    args = ap.parse_args()

    blocks_root = Path(args.blocks_dir).expanduser().resolve()
    out_root = Path(args.out_dir).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    if not blocks_root.exists():
        print(f"[ERREUR] Dossier introuvable: {blocks_root}")
        return

    mod_dirs = [p for p in blocks_root.iterdir() if p.is_dir()]
    if not mod_dirs:
        mod_dirs = [blocks_root]

    # 1) Pré-compter le nombre total de rendus à produire (progression)
    jobs = []
    for moddir in mod_dirs:
        textures = collect_textures_in_moddir(moddir)
        if not textures:
            continue
        groups = {}
        for stem, path in textures.items():
            base = re.sub(r"(_(top|bottom|side|north|south|east|west))$", "", stem)
            groups.setdefault(base, {})[stem] = path
        for base, texmap in groups.items():
            jobs.append((moddir.name, base, texmap))

    total = len(jobs)
    if total == 0:
        print("Aucun rendu à produire (pas de textures trouvées).")
        return

    # 2) Rendu avec compteur
    done = 0
    for modid, base, texmap in jobs:
        faces = find_faces(texmap)
        try:
            top_img   = load_png(faces["top"])
            left_img  = load_png(faces["left"])
            right_img = load_png(faces["right"])
        except Exception as e:
            print(f"\n[WARN] Chargement textures échoué pour {modid}:{base} -> {e}")
            done += 1
            continue

        iso = make_iso_cube(top_img, left_img, right_img, size=args.size)
        out_mod = (out_root / modid)
        out_mod.mkdir(parents=True, exist_ok=True)
        out_path = out_mod / f"{base}.png"
        iso.save(out_path)

        done += 1
        pct = int(done * 100 / total)
        print(f"\rProgression: {done}/{total} ({pct}%)  -  {modid}:{base}     ", end="", flush=True)

    print(f"\nRendus générés: {done}/{total}")
    print(f"Sortie: {out_root}")

if __name__ == "__main__":
    main()
