"""One-command pipeline: N novel shapes -> textured triads -> benchmark manifest.

Stages (any subset via flags):
  1. select    pick N base shapes + a disjoint distractor pool, copy as 1..N.stl
               (source = the bundled STL pool in data/shapes/ by default;
                or --generate to create fresh shapes via the Shape Generator add-on)
  2. render    run Blender (render_stimuli_generic.py) for each mode
  3. manifest  merge per-mode manifests into combined_benchmark_manifest.csv
  4. sync      copy the packages into the benchmark repo (optional)

Examples:
  # Reuse existing STLs, 200 objects, both modes, into default out dir:
  python3 automate_stimuli.py --n 200 --modes B_controlled_simple,A_auto_contrast

  # Quick 5-object low-res smoke test:
  python3 automate_stimuli.py --n 5 --modes B_controlled_simple --res 384 --samples 24

  # Generate brand-new shapes (needs the add-on installed / zip provided):
  python3 automate_stimuli.py --n 200 --generate --addon-zip /path/shape_generator.zip

  # Also sync into the benchmark repo:
  python3 automate_stimuli.py --n 200 --sync-to \
      "../../shapebias-bench-2/stimuli_pipe/stimuli_per_stl_packages"
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
DEFAULT_SOURCE = PROJECT / "data" / "shapes"
DEFAULT_OUT = PROJECT / "data" / "generated_stimuli"


def _evenly_spaced(items: list, k: int) -> list:
    if k <= 0 or not items:
        return []
    if k >= len(items):
        return list(items)
    n = len(items)
    return [items[round(i * (n - 1) / (k - 1))] for i in range(k)] if k > 1 else [items[n // 2]]


def stage_select(source: Path, n: int, distractors: int, out: Path) -> None:
    all_stls = sorted(source.glob("*.stl"), key=lambda p: p.name.lower())
    if not all_stls:
        sys.exit(f"ERROR: no .stl files under {source}")
    if n + distractors > len(all_stls):
        print(f"WARNING: requested {n}+{distractors} but only {len(all_stls)} available; clamping.")

    base_dir = out / "base"
    dist_dir = out / "distractors"
    for d in (base_dir, dist_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    base_pick = _evenly_spaced(all_stls, min(n, len(all_stls)))
    base_set = {p for p in base_pick}
    remaining = [p for p in all_stls if p not in base_set]
    dist_pick = _evenly_spaced(remaining, min(distractors, len(remaining))) or base_pick[: min(distractors, len(base_pick))]

    for i, src in enumerate(base_pick, start=1):
        shutil.copyfile(src, base_dir / f"{i}.stl")
        (base_dir / f"{i}.source.txt").write_text(src.name)
    for i, src in enumerate(dist_pick, start=1):
        shutil.copyfile(src, dist_dir / f"{i}.stl")

    print(f"select: {len(base_pick)} base -> {base_dir}, {len(dist_pick)} distractors -> {dist_dir}")


def stage_generate(n: int, out: Path, addon_zip: str | None, seed_base: int) -> None:
    base_dir = out / "base"
    dist_dir = out / "distractors"
    base_dir.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Generate N base + a distractor pool (~20% of N, min 8) with a disjoint seed range.
    n_dist = max(8, n // 5)
    _run_blender("generate_shapes.py", {
        "GEN_COUNT": str(n), "GEN_OUT_DIR": str(base_dir), "GEN_SEED_BASE": str(seed_base),
        **({"GEN_ADDON_ZIP": addon_zip} if addon_zip else {}),
    })
    _run_blender("generate_shapes.py", {
        "GEN_COUNT": str(n_dist), "GEN_OUT_DIR": str(dist_dir), "GEN_SEED_BASE": str(seed_base + 100000),
        **({"GEN_ADDON_ZIP": addon_zip} if addon_zip else {}),
    })


def _run_blender(script: str, env_extra: dict) -> None:
    env = os.environ.copy()
    env.update(env_extra)
    cmd = ["bash", "./run_blender.sh", "-b", "-P", script]
    print(f"\n$ {' '.join(f'{k}={v}' for k, v in env_extra.items())} {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT, env=env)
    if result.returncode != 0:
        sys.exit(f"ERROR: Blender step failed ({script}), exit {result.returncode}")


def stage_render(out: Path, modes: list[str], res: int, samples: int, use_textures: bool) -> None:
    base_dir = out / "base"
    dist_dir = out / "distractors"
    pkg_root = out / "stimuli_per_stl_packages"
    for mode in modes:
        _run_blender("render_stimuli.py", {
            "STIM_INPUT_DIR": str(base_dir),
            "STIM_DISTRACTOR_DIR": str(dist_dir),
            "STIM_OUT_DIR": str(pkg_root),
            "STIM_MODE": mode,
            "STIM_RES": str(res),
            "STIM_SAMPLES": str(samples),
            "STIM_USE_IMAGE_TEXTURES": "1" if use_textures else "0",
        })


def _mode_tag(mode: str) -> str:
    return "A" if "A_auto" in mode else ("B" if "B_" in mode else "U")


def stage_manifest(out: Path, modes: list[str]) -> None:
    pkg_root = out / "stimuli_per_stl_packages"
    rows = []
    for mode in modes:
        manifest = pkg_root / mode / "manifest.csv"
        if not manifest.exists():
            print(f"WARNING: missing {manifest}")
            continue
        with manifest.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sid = r.get("stl_id", "").strip()
                if not sid:
                    continue
                sid_num = int(sid) if sid.isdigit() else 0
                rows.append({
                    "trial_id": f"{_mode_tag(mode)}_{sid_num:03d}",
                    "mode": mode,
                    "stl_id": sid,
                    "example_image": r.get("example_image", ""),
                    "target": r.get("reference", ""),
                    "shape_match": r.get("shape_match", ""),
                    "texture_match": r.get("texture_match", ""),
                    "forced_texture_set": r.get("forced_texture_set", ""),
                    "shape_stl": r.get("shape_stl", ""),
                    "distractor_stl": r.get("distractor_stl", ""),
                })
    rows.sort(key=lambda r: (r["mode"], int(r["stl_id"]) if r["stl_id"].isdigit() else 0))
    out_csv = pkg_root / "combined_benchmark_manifest.csv"
    fields = ["trial_id", "mode", "stl_id", "example_image", "target", "shape_match",
              "texture_match", "forced_texture_set", "shape_stl", "distractor_stl"]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"manifest: {len(rows)} rows -> {out_csv}")


def stage_sync(out: Path, dest: str) -> None:
    src = out / "stimuli_per_stl_packages"
    dest_path = Path(dest)
    if not dest_path.is_absolute():
        dest_path = (PROJECT / dest).resolve()
    dest_path.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dest_path / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copyfile(child, target)
    print(f"sync: {src} -> {dest_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=200, help="number of base objects")
    ap.add_argument("--distractors", type=int, default=40, help="distractor pool size (reuse mode)")
    ap.add_argument("--source", default=str(DEFAULT_SOURCE), help="dir of pre-generated STLs to sample")
    ap.add_argument("--generate", action="store_true", help="generate fresh shapes via add-on instead of sampling")
    ap.add_argument("--addon-zip", default=None, help="Shape Generator add-on zip (first-time install)")
    ap.add_argument("--seed-base", type=int, default=1000, help="base seed for --generate")
    ap.add_argument("--modes", default="B_controlled_simple,A_auto_contrast")
    ap.add_argument("--res", type=int, default=1024)
    ap.add_argument("--samples", type=int, default=128)
    ap.add_argument("--no-image-textures", action="store_true", help="use procedural materials only")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output root")
    ap.add_argument("--sync-to", default=None, help="also copy packages into this benchmark dir")
    ap.add_argument("--stages", default="select,render,manifest",
                    help="comma subset of: select,render,manifest,sync")
    args = ap.parse_args()

    out = Path(args.out)
    if not out.is_absolute():
        out = PROJECT / out
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    if args.sync_to and "sync" not in stages:
        stages.append("sync")

    if "select" in stages:
        if args.generate:
            stage_generate(args.n, out, args.addon_zip, args.seed_base)
        else:
            stage_select(Path(args.source), args.n, args.distractors, out)
    if "render" in stages:
        stage_render(out, modes, args.res, args.samples, not args.no_image_textures)
    if "manifest" in stages:
        stage_manifest(out, modes)
    if "sync" in stages and args.sync_to:
        stage_sync(out, args.sync_to)

    print("\nAll requested stages complete.")


if __name__ == "__main__":
    main()
