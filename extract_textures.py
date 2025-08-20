#!/usr/bin/env python3
"""
extract_textures.py
Scanne un dossier 'mods' ( tout modpack Forge/Fabric)
et extrait toutes les textures de blocs/items dans un dossier de sortie,
classées par type (blocks/items) et par modid.

Usage:
  python3 extract_atm10_textures.py <mods_dir> <output_dir>

Exemple:
  python3 extract_atm10_textures.py ~/atm10-server/mods ~/atm10-textures
"""

import sys
import re
import zipfile
import shutil
from pathlib import Path

# --- Helpers -----------------------------------------------------------------

def sanitize(name: str) -> str:
    """
    Nettoie un chemin relatif de ressource pour un usage en FS.
    Conserve lettres/chiffres, '.', '_', '/', '-'.
    IMPORTANT: '-' placé en fin d'ensemble pour éviter une plage.
    """
    return re.sub(r"[^A-Za-z0-9._/-]+", "_", name)

def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

# --- Entrées -----------------------------------------------------------------

if len(sys.argv) < 3:
    print("Usage: python3 extract_atm10_textures.py <mods_dir> <output_dir>")
    sys.exit(1)

mods_dir = Path(sys.argv[1]).expanduser().resolve()
out_dir  = Path(sys.argv[2]).expanduser().resolve()

if not mods_dir.exists():
    print(f"[ERREUR] Dossier mods introuvable: {mods_dir}")
    sys.exit(2)

# --- Sortie ------------------------------------------------------------------

out_blocks = ensure_dir(out_dir / "blocks")
out_items  = ensure_dir(out_dir / "items")

# Certains mods utilisent block/item OU blocks/items
BLOCK_DIRS = ("textures/block/", "textures/blocks/")
ITEM_DIRS  = ("textures/item/",  "textures/items/")

# Conserver les animations .png.mcmeta également
VALID_EXTS = (".png", ".png.mcmeta")

scanned = 0
total_blocks = 0
total_items = 0
skipped_archives = 0

# --- Parcours des .jar (et .zip au cas où) -----------------------------------

archives = list(mods_dir.glob("*.jar")) + list(mods_dir.glob("*.zip"))
archives.sort()

for jar_path in archives:
    scanned += 1
    try:
        with zipfile.ZipFile(jar_path) as z:
            # Détecter les modid présents (assets/<modid>/...)
            modids = set()
            for name in z.namelist():
                if not name.startswith("assets/"):
                    continue
                parts = name.split("/")
                # assets/<modid>/...
                if len(parts) >= 3 and parts[1]:
                    modids.add(parts[1])

            if not modids:
                continue

            for modid in sorted(modids):
                mod_blocks_dir = ensure_dir(out_blocks / modid)
                mod_items_dir  = ensure_dir(out_items  / modid)

                for info in z.infolist():
                    fn = info.filename
                    if not fn.startswith(f"assets/{modid}/textures/"):
                        continue

                    lower = fn.lower()
                    if not lower.endswith(VALID_EXTS):
                        continue

                    is_block = any(f"assets/{modid}/{d}" in lower for d in BLOCK_DIRS)
                    is_item  = any(f"assets/{modid}/{d}" in lower for d in ITEM_DIRS)
                    if not (is_block or is_item):
                        continue

                    # Chemin relatif après "textures/"
                    try:
                        rel = fn.split("textures/", 1)[1]  # ex: block/stone.png
                    except IndexError:
                        # sécurité, ne devrait pas arriver si startswith passe
                        rel = Path(fn).name

                    rel = sanitize(rel)
                    dest_dir = mod_blocks_dir if is_block else mod_items_dir
                    dest_path = dest_dir / rel
                    ensure_dir(dest_path.parent)

                    with z.open(info) as src, open(dest_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)

                    if is_block:
                        total_blocks += 1
                    else:
                        total_items += 1

    except zipfile.BadZipFile:
        skipped_archives += 1
        print(f"[WARN] Archive corrompue/illisible: {jar_path}")

print("---- RÉSULTAT ----")
print(f"Archives scannées : {scanned}  (ignorées: {skipped_archives})")
print(f"Textures blocs    : {total_blocks}")
print(f"Textures items    : {total_items}")
print(f"Sortie            : {out_dir}")
print(f" - {out_dir / 'blocks'}")
print(f" - {out_dir / 'items'}")
