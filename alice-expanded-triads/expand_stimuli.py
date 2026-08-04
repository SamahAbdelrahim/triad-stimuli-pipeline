"""Build the expanded unique-texture stimulus packages: every texture on every shape.

The single-texture pipeline (`automate_stimuli.py`) gives each STL one texture,
so 30 ALICE shapes yield 30 trials per mode. This script instead crosses the
whole texture library with the whole shape set: each shape gets one package per
texture, which turns 30 shapes x N textures into 30*N trials per mode.

Package layout (`<stl_id>/<texture_set>/` holds the same four images the
single-texture packages hold, so downstream code sees a familiar folder):

    stimuli_unique_texture_per_stl_v1/
    └── stimuli_B_controlled_simple/
        ├── 1/
        │   ├── Carpet013_1K-JPG/
        │   │   ├── example_image.png    photograph of object 1
        │   │   ├── reference.png        shape 1, texture Carpet013
        │   │   ├── shape_match.png      shape 1, a different texture
        │   │   └── texture_match.png    a different shape, texture Carpet013
        │   └── ... one folder per texture ...
        ├── 2/ ...
        └── manifest.csv

Rules preserved from the original stimuli:
  - `reference` and `texture_match` share one material and differ only in shape;
  - `shape_match` keeps the shape and swaps the texture;
  - `example_image` is the photograph of the real object (`data/alice/images/`).

Everything is cut from one render grid (see `render_texture_grid.py`), so a
package costs no renders of its own: `reference`, `shape_match` and
`texture_match` are three different cells of that grid, placed as hardlinks.
v1 and v2 contain the same trials but pair them differently -- they rotate the
texture list and the shape list by different offsets when choosing which texture
`shape_match` gets and which shape `texture_match` gets.

Stages (any subset via --stages):
  plan      inventory shapes + usable texture sets, report the trial count
  grid      render the (mode x shape x texture) still grid via Blender
  assemble  place grid cells into the v1 and v2 package trees
  manifest  write per-mode manifest.csv + combined_benchmark_manifest.csv
  sync      mirror the version trees into a benchmark repo

Examples:
  # what would be built, no rendering
  python3 expand_stimuli.py --stages plan

  # smoke test: 2 shapes x 3 textures, one mode, low quality
  python3 expand_stimuli.py --only-stems 1,2 --max-textures 3 \
      --modes B_controlled_simple --res 384 --samples 24

  # full build, then mirror into the benchmark repo
  python3 expand_stimuli.py --res 1024 --samples 128 \
      --sync-to ../../shapebias-bench2/stimuli_pipe
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

# `_run_blender` already resolves the bundled/system Blender the same way every
# other stage does; reuse it rather than growing a second copy.
from automate_stimuli import _run_blender

PROJECT = Path(__file__).resolve().parent
ALICE_STL = PROJECT / "data" / "alice" / "stl"
ALICE_IMAGES = PROJECT / "data" / "alice" / "images"
TEXTURE_LIBRARY = PROJECT / "data" / "texture_library"
DEFAULT_OUT = PROJECT / "data" / "generated_stimuli"
GRID_DIRNAME = "texture_grid"

# Output folder name -> render-engine mode name. The folder names are fixed by
# what shapebias-bench2 already loads.
STIM_SETS = {
    "stimuli_B_controlled_simple": "B_controlled_simple",
    "stimuli_A_auto_contrast": "A_auto_contrast",
}

# Both versions hold the same trials; they differ in how those trials are paired.
# A version rotates the texture list (to choose `shape_match`'s texture) and the
# shape list (to choose `texture_match`'s shape) by a fraction of their length.
# Rotating is a bijection, so a foil is never the original and every texture and
# shape serves as a foil equally often. The two versions use different fractions,
# which repairs every trial.
VERSIONS = {
    "stimuli_unique_texture_per_stl_v1": {"texture_rotation": 0.50, "shape_rotation": 0.50},
    "stimuli_unique_texture_per_stl_v2": {"texture_rotation": 0.30, "shape_rotation": 0.30},
}
VERSION_ALIASES = {"v1": "stimuli_unique_texture_per_stl_v1",
                   "v2": "stimuli_unique_texture_per_stl_v2"}

PACKAGE_IMAGES = ("example_image.png", "reference.png", "shape_match.png", "texture_match.png")

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".exr"}
# Mirrors stl_material_overlay_render._resolve_pbr_maps: a set is only usable if
# the engine can find a base-color map in it.
_BASECOLOR_KEYWORDS = ("basecolor", "albedo", "color", "diffuse", "diff")


# --------------------------------------------------------------------------- #
# inventory
# --------------------------------------------------------------------------- #
def discover_shapes(stl_dir: Path, only_stems: set[str] | None) -> list[dict]:
    shapes = []
    for p in sorted(stl_dir.glob("*.stl"),
                    key=lambda p: (int(p.stem) if p.stem.isdigit() else 1 << 30, p.name.lower())):
        if only_stems is not None and p.stem not in only_stems:
            continue
        shapes.append({"stl_id": p.stem, "path": str(p)})
    return shapes


def _has_basecolor(set_dir: Path) -> bool:
    for p in sorted(set_dir.rglob("*"), key=lambda p: str(p).lower()):
        if not p.is_file() or p.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        name = p.name.lower()
        if "preview" in name:
            continue
        if any(k in name for k in _BASECOLOR_KEYWORDS):
            return True
    return False


def discover_textures(library: Path, limit: int | None) -> list[str]:
    """Texture sets the render engine can use, in the order it lists them.

    Folders prefixed `NO - ` are the library's opt-out convention.
    """
    names = []
    for d in sorted(library.iterdir(), key=lambda p: p.name.lower()):
        if not d.is_dir() or d.name.lower().startswith(("no -", "no-", "no_")):
            continue
        if _has_basecolor(d):
            names.append(d.name)
    return names[:limit] if limit else names


def alice_photo(stl_id: str) -> Path | None:
    for suffix in (".PNG", ".png"):
        p = ALICE_IMAGES / f"{stl_id}{suffix}"
        if p.exists():
            return p
    return None


def cell_path(grid_root: Path, mode: str, texture_set: str, stl_id: str) -> Path:
    return grid_root / mode / texture_set / f"{stl_id}.png"


# --------------------------------------------------------------------------- #
# pairing
# --------------------------------------------------------------------------- #
def _rotation(fraction: float, n: int) -> int:
    """Rotate a list of length n by `fraction` of its length, clamped to [1, n-1].

    Clamping away from 0 keeps a foil from being the original. Rotating by a
    large step also keeps the foil far from the original in the library's
    alphabetical order, which in practice means the `shape_match` texture comes
    from a different material family rather than being the neighbouring variant
    of the same one (Fabric002 -> Metal009, not Fabric002 -> Fabric004).
    """
    return min(max(round(fraction * n), 1), n - 1)


def iter_packages(version: str, stim_set: str, shape_ids: list[str], textures: list[str]):
    """Yield one record per (shape, texture) package.

    Both `assemble` and `manifest` walk this, so the files on disk and the rows
    in the manifest cannot drift apart.
    """
    tex_rot = _rotation(VERSIONS[version]["texture_rotation"], len(textures))
    shape_rot = _rotation(VERSIONS[version]["shape_rotation"], len(shape_ids))
    for i, stl_id in enumerate(shape_ids):
        for j, texture_set in enumerate(textures):
            yield {
                "mode": stim_set,
                "stl_id": stl_id,
                "texture_set": texture_set,
                "stim_id": f"{stl_id}/{texture_set}",
                "shape_match_texture_set": textures[(j + tex_rot) % len(textures)],
                "texture_match_stl_id": shape_ids[(i + shape_rot) % len(shape_ids)],
            }


def package_sources(rec: dict, grid_root: Path, engine_mode: str) -> dict[str, Path]:
    stl_id = rec["stl_id"]
    texture = rec["texture_set"]
    return {
        "reference.png": cell_path(grid_root, engine_mode, texture, stl_id),
        "shape_match.png": cell_path(grid_root, engine_mode, rec["shape_match_texture_set"], stl_id),
        "texture_match.png": cell_path(grid_root, engine_mode, texture, rec["texture_match_stl_id"]),
        "example_image.png": alice_photo(stl_id),
    }


# --------------------------------------------------------------------------- #
# stages
# --------------------------------------------------------------------------- #
def stage_plan(out: Path, stim_sets: dict, shapes: list[dict], textures: list[str],
               versions: list[str], overwrite: bool) -> Path:
    grid_root = out / GRID_DIRNAME
    plan = {
        "grid_root": str(grid_root),
        "modes": list(stim_sets.values()),
        # The photograph travels with the shape: the grid renderer matches each
        # render's pose to it so `reference` faces the way `example_image` does.
        "shapes": [{**s, "photo": str(alice_photo(s["stl_id"]) or "")} for s in shapes],
        "textures": textures,
        "overwrite": overwrite,
    }
    out.mkdir(parents=True, exist_ok=True)
    plan_path = out / "grid_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    cells = len(stim_sets) * len(shapes) * len(textures)
    existing = sum(1 for mode in stim_sets.values() for s in shapes for t in textures
                   if cell_path(grid_root, mode, t, s["stl_id"]).exists())
    packages = cells * len(versions)
    print(f"plan: {len(shapes)} shapes x {len(textures)} textures x {len(stim_sets)} modes")
    print(f"      {cells} grid cells to render ({existing} already on disk)")
    print(f"      {packages} packages across {len(versions)} versions "
          f"= {cells // max(len(stim_sets), 1)} trials per mode per version")
    print(f"      plan -> {plan_path}")
    return plan_path


def stage_grid(plan_path: Path, res: int, samples: int, device: str) -> None:
    _run_blender("render_texture_grid.py", {
        "STIM_GRID_PLAN": str(plan_path),
        "STIM_RES": str(res),
        "STIM_SAMPLES": str(samples),
        "STIM_CYCLES_DEVICE": device,
        "STIM_USE_IMAGE_TEXTURES": "1",
    })


def _place(src: Path, dst: Path, link_mode: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if link_mode == "copy":
        shutil.copyfile(src, dst)
    elif link_mode == "symlink":
        dst.symlink_to(os.path.relpath(src, dst.parent))
    else:
        try:
            os.link(src, dst)
        except OSError:
            shutil.copyfile(src, dst)


def stage_assemble(out: Path, versions: list[str], stim_sets: dict, shapes: list[dict],
                   textures: list[str], link_mode: str) -> None:
    grid_root = out / GRID_DIRNAME
    shape_ids = [s["stl_id"] for s in shapes]
    for version in versions:
        for stim_set, engine_mode in stim_sets.items():
            placed = incomplete = 0
            for rec in iter_packages(version, stim_set, shape_ids, textures):
                sources = package_sources(rec, grid_root, engine_mode)
                if any(p is None or not p.exists() for p in sources.values()):
                    incomplete += 1
                    continue
                pkg = out / version / stim_set / rec["stl_id"] / rec["texture_set"]
                for name, src in sources.items():
                    _place(src, pkg / name, link_mode)
                placed += 1
            note = f", {incomplete} skipped (missing grid cells)" if incomplete else ""
            print(f"assemble: {placed} packages -> {version}/{stim_set}{note}")


def stage_manifest(out: Path, versions: list[str], stim_sets: dict, shapes: list[dict],
                   textures: list[str]) -> None:
    shape_ids = [s["stl_id"] for s in shapes]
    per_mode_fields = ["mode", "stl_id", "texture_set", "stim_id", "example_image", "reference",
                       "shape_match", "texture_match", "shape_match_texture_set",
                       "texture_match_stl_id"]
    combined_fields = ["trial_id", "mode", "stl_id", "texture_set", "stim_id", "example_image",
                       "target", "shape_match", "texture_match", "shape_match_texture_set",
                       "texture_match_stl_id"]

    for version in versions:
        combined = []
        for stim_set in stim_sets:
            rows = []
            for rec in iter_packages(version, stim_set, shape_ids, textures):
                pkg = out / version / stim_set / rec["stl_id"] / rec["texture_set"]
                if not (pkg / "reference.png").exists():
                    continue
                paths = {name: f"{stim_set}/{rec['stim_id']}/{name}" for name in PACKAGE_IMAGES}
                row = {
                    **{k: rec[k] for k in ("mode", "stl_id", "texture_set", "stim_id",
                                           "shape_match_texture_set", "texture_match_stl_id")},
                    "example_image": paths["example_image.png"],
                    "reference": paths["reference.png"],
                    "shape_match": paths["shape_match.png"],
                    "texture_match": paths["texture_match.png"],
                }
                rows.append(row)
                tag = "A" if "A_auto" in stim_set else "B"
                stl_num = int(row["stl_id"]) if row["stl_id"].isdigit() else 0
                tex_num = textures.index(row["texture_set"]) + 1
                combined.append({
                    "trial_id": f"{tag}_{stl_num:03d}_{tex_num:02d}",
                    **{k: row[k] for k in ("mode", "stl_id", "texture_set", "stim_id",
                                           "example_image")},
                    "target": row["reference"],
                    **{k: row[k] for k in ("shape_match", "texture_match",
                                           "shape_match_texture_set", "texture_match_stl_id")},
                })

            manifest = out / version / stim_set / "manifest.csv"
            _write_csv(manifest, per_mode_fields, rows)
            print(f"manifest: {len(rows)} rows -> {manifest.relative_to(out)}")

        combined_path = out / version / "combined_benchmark_manifest.csv"
        _write_csv(combined_path, combined_fields, combined)
        print(f"manifest: {len(combined)} rows -> {combined_path.relative_to(out)}")


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def stage_sync(out: Path, versions: list[str], dest: str, link_mode: str) -> None:
    dest_root = Path(dest)
    if not dest_root.is_absolute():
        dest_root = (PROJECT / dest).resolve()
    for version in versions:
        src_root = out / version
        if not src_root.exists():
            print(f"WARNING: nothing to sync for {version}")
            continue
        count = 0
        for src in sorted(src_root.rglob("*")):
            if src.is_file():
                _place(src, dest_root / version / src.relative_to(src_root), link_mode)
                count += 1
        print(f"sync: {count} files -> {dest_root / version}")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output root")
    ap.add_argument("--stages", default="plan,grid,assemble,manifest",
                    help="comma subset of: plan,grid,assemble,manifest,sync")
    ap.add_argument("--modes", default=",".join(STIM_SETS.values()),
                    help="comma list of render modes to build")
    ap.add_argument("--versions", default=",".join(VERSIONS),
                    help="comma list of version package names to build")
    ap.add_argument("--only-stems", default=None,
                    help="comma list of STL ids to restrict to (e.g. 1,2,3)")
    ap.add_argument("--max-textures", type=int, default=None,
                    help="use only the first N texture sets (smoke tests)")
    ap.add_argument("--res", type=int, default=1024, help="square render resolution")
    ap.add_argument("--samples", type=int, default=128, help="Cycles samples")
    ap.add_argument("--device", default="CPU",
                    choices=["CPU", "OPTIX", "CUDA", "HIP", "ONEAPI"],
                    help="Cycles device (use OPTIX on farmshare gpu/oat nodes)")
    ap.add_argument("--link-mode", default="hardlink", choices=["hardlink", "copy", "symlink"],
                    help="how grid cells are placed into packages (hardlink keeps one copy on disk)")
    ap.add_argument("--overwrite", action="store_true", help="re-render grid cells that exist")
    ap.add_argument("--sync-to", default=None, help="also mirror version trees into this dir")
    args = ap.parse_args()

    out = Path(args.out)
    if not out.is_absolute():
        out = PROJECT / out
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    if args.sync_to and "sync" not in stages:
        stages.append("sync")

    wanted_modes = {m.strip() for m in args.modes.split(",") if m.strip()}
    stim_sets = {k: v for k, v in STIM_SETS.items() if v in wanted_modes or k in wanted_modes}
    if not stim_sets:
        sys.exit(f"ERROR: --modes must name some of {sorted(STIM_SETS.values())}")

    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    versions = [VERSION_ALIASES.get(v, v) for v in versions]
    unknown = [v for v in versions if v not in VERSIONS]
    if unknown:
        sys.exit(f"ERROR: unknown --versions {unknown}; expected some of {sorted(VERSIONS)}")

    only_stems = {s.strip() for s in args.only_stems.split(",")} if args.only_stems else None
    shapes = discover_shapes(ALICE_STL, only_stems)
    if not shapes:
        sys.exit(f"ERROR: no .stl files under {ALICE_STL}")
    textures = discover_textures(TEXTURE_LIBRARY, args.max_textures)
    if len(textures) < 2:
        sys.exit(f"ERROR: need at least 2 usable texture sets in {TEXTURE_LIBRARY}, found {len(textures)}")

    missing_photos = [s["stl_id"] for s in shapes if alice_photo(s["stl_id"]) is None]
    if missing_photos:
        print(f"WARNING: no photograph for stl ids {missing_photos}; "
              "their packages will be skipped")

    plan_path = stage_plan(out, stim_sets, shapes, textures, versions, args.overwrite)
    if "grid" in stages:
        stage_grid(plan_path, args.res, args.samples, args.device)
    if "assemble" in stages:
        stage_assemble(out, versions, stim_sets, shapes, textures, args.link_mode)
    if "manifest" in stages:
        stage_manifest(out, versions, stim_sets, shapes, textures)
    if "sync" in stages and args.sync_to:
        stage_sync(out, versions, args.sync_to, args.link_mode)

    print("\nAll requested stages complete.")


if __name__ == "__main__":
    main()
