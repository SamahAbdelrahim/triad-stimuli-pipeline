"""Fetch CC0 PBR texture sets from ambientCG into data/texture_library/.

These sets plug directly into stl_material_overlay_render._resolve_pbr_maps
(base color / roughness / normal / height / metallic / AO are matched by
filename keyword). ambientCG JPG packs already use those keywords
(Color, Roughness, NormalGL, Displacement, Metalness, AmbientOcclusion).

Usage (needs internet):
  python3 scripts/fetch_cc0_textures.py            # fetch default curated list
  python3 scripts/fetch_cc0_textures.py --res 2K   # higher-res packs
  python3 scripts/fetch_cc0_textures.py --only Fabric046 Metal032

Naming keeps mode-preference keywords intact so the stimulus material picker
(fabric/leather/carpet for mode B, metal/steel/rust for mode A) still works.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

_PROJECT = Path(__file__).resolve().parents[1]
_TEXTURE_LIB = _PROJECT / "data" / "texture_library"

# Curated CC0 assets. Left group -> mode B (fabric/leather/carpet),
# right group -> mode A (metal/steel/rust). All are ambientCG asset IDs.
_DEFAULT_ASSETS = [
    # soft / cloth (mode B: fabric, cloth, carpet, leather)
    "Fabric001", "Fabric012", "Fabric030", "Fabric045", "Fabric046",
    "Fabric062", "Fabric070", "Leather011", "Leather028", "Leather033",
    "Carpet013", "Carpet014", "Wool001", "DenimFabric001",
    # hard / metallic (mode A: steel, metal, rust, corrugated)
    "Metal006", "Metal032", "Metal046", "MetalPlates006", "MetalPlates013",
    "CorrugatedSteel005", "Rust004", "Rust006", "PaintedMetal004",
    "PaintedMetal008", "ChristmasTreeOrnament001", "SheetMetal001",
]

_ACG_URL = "https://ambientcg.com/get?file={asset}_{res}-JPG.zip"


def _download(asset: str, res: str) -> bytes | None:
    url = _ACG_URL.format(asset=asset, res=res)
    req = urllib.request.Request(url, headers={"User-Agent": "shapebias-stimuli/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except Exception as exc:  # 404s and network hiccups are non-fatal
        print(f"  SKIP {asset}: {exc}")
        return None


# Only keep the PBR maps the material engine consumes. This drops preview
# thumbnails and non-image sidecars (.blend/.mtlx/.tres/.usdc) that would
# otherwise be mis-selected by the filename-keyword map loader. NormalDX is
# dropped in favor of NormalGL (Blender expects OpenGL-convention normals).
_KEEP_KEYWORDS = ("color", "roughness", "normalgl", "displacement", "metalness", "ambientocclusion")


def _wanted_map(name: str) -> bool:
    low = name.lower()
    if not low.endswith((".jpg", ".jpeg", ".png")):
        return False
    if "normaldx" in low:
        return False
    return any(k in low for k in _KEEP_KEYWORDS)


def _extract(asset: str, res: str, data: bytes) -> bool:
    dest = _TEXTURE_LIB / f"{asset}_{res}-JPG"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            members = [m for m in zf.namelist() if not m.endswith("/") and _wanted_map(Path(m).name)]
            if not members:
                print(f"  SKIP {asset}: no usable PBR maps in archive")
                return False
            dest.mkdir(parents=True, exist_ok=True)
            for m in members:
                # Flatten any nested dirs; keep basename only.
                name = Path(m).name
                if not name:
                    continue
                with zf.open(m) as src, (dest / name).open("wb") as out:
                    out.write(src.read())
    except zipfile.BadZipFile:
        print(f"  SKIP {asset}: not a zip (asset/res may not exist)")
        return False
    print(f"  OK   {asset} -> {dest.relative_to(_PROJECT)}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", default="1K", choices=["1K", "2K", "4K"])
    ap.add_argument("--only", nargs="*", default=None, help="asset IDs to fetch")
    args = ap.parse_args()

    assets = args.only if args.only else _DEFAULT_ASSETS
    _TEXTURE_LIB.mkdir(parents=True, exist_ok=True)

    ok = 0
    for asset in assets:
        print(f"Fetching {asset} ({args.res})...")
        data = _download(asset, args.res)
        if data and _extract(asset, args.res, data):
            ok += 1
        time.sleep(0.3)  # be gentle

    print(f"\nDone: {ok}/{len(assets)} sets fetched into {_TEXTURE_LIB.relative_to(_PROJECT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
