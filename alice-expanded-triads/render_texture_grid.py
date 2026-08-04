"""Render the shape x texture still grid that expanded triad packages are cut from.

Every cell is a "variant 1" render: one shape carrying one PBR texture set, at a
fixed pose, in the same studio rig `render_stimuli.py` uses. One cell can then
serve as `reference`, as `shape_match`, or as `texture_match` depending on which
package it is assembled into, so no image is ever rendered twice.

The material seed is derived from the *texture set name* rather than the STL
path. That is the one deviation from `render_stimuli.py`, and it is what makes
the grid reusable: the seed drives the color tint mixed over the base-color map,
so keying it to the texture means every cell sharing a texture carries a
byte-identical material. `reference` (shape S, texture T) and `texture_match`
(shape S', texture T) therefore differ in shape alone, which is the invariant the
2AFC design depends on.

Each shape is turned about Z until its silhouette matches its ALICE photograph,
so `reference` faces the same way as the `example_image` beside it. The angle is
solved once per shape and reused for every texture, which keeps `reference` and
`shape_match` in one pose.

Cells already on disk are skipped, so an interrupted run resumes where it left off.

Run through the Blender wrapper (this is a bpy script, not plain Python) -- normally
via `expand_stimuli.py --stages grid`, which writes the plan and invokes:

  STIM_GRID_PLAN=/abs/path/grid_plan.json \
  bash ./run_blender.sh -b -P render_texture_grid.py

Env vars:
  STIM_GRID_PLAN           (required) JSON plan written by expand_stimuli.py
  STIM_RES                 square render resolution (default 1024)
  STIM_SAMPLES             Cycles samples (default 128)
  STIM_CYCLES_DEVICE       CPU | OPTIX | CUDA | HIP | ONEAPI (default CPU)
  STIM_TEXTURE_LIBRARY     optional absolute path to texture sets
"""

import json
import os
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

# Reuse the studio rig and material engine from the single-texture renderer so
# grid cells and `render_stimuli.py` output stay visually identical.
import render_stimuli as triad

scene = triad.scene
mats = triad.mats


def texture_seed(texture_set: str) -> int:
    return scene._stable_int(f"texture:{texture_set}")


def cell_path(grid_root: Path, mode: str, texture_set: str, stl_id: str) -> Path:
    return grid_root / mode / texture_set / f"{stl_id}.png"


def _prepare_shape(shape: dict):
    """Import a shape and build the scene around it, ready for any material."""
    stl_path = Path(shape["path"])
    scene.clear_scene()
    scene.bpy.ops.wm.stl_import(filepath=str(stl_path))
    selected = list(scene.bpy.context.selected_objects)
    if not selected:
        print(f"WARNING: failed to import STL: {stl_path}")
        return None

    obj = selected[0]
    object_size = scene.center_and_scale_object(obj, target_size=2.0)
    scene.setup_scene(obj, object_size, material_mode="flat", material_seed=0)
    triad._set_dark_gray_background()
    triad._set_balanced_color_management(exposure=0.20)
    triad._rebalance_lighting_soft(object_size)
    triad._configure_stimulus_render_controls()
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (0.0, 0.0, 0.0)

    photo = shape.get("photo") or ""
    if photo and Path(photo).exists():
        triad.pose_match_z(obj, stl_path, Path(photo))
    else:
        print(f"WARNING: no photograph for stl {shape['stl_id']}; pose left unmatched")
    return obj


def _render_cell(obj, out_png: Path, *, texture_set: str, mode: str) -> bool:
    prev_force = os.environ.get("STIM_FORCE_TEXTURE_SET")
    os.environ["STIM_FORCE_TEXTURE_SET"] = texture_set
    try:
        resolved = mats._pick_texture_set(0, prefer_keywords=None)
        if resolved is None or resolved.name != texture_set:
            print(f"WARNING: texture set {texture_set!r} did not resolve "
                  f"(got {resolved.name if resolved else None!r}); skipping cell")
            return False
        mats.apply_material_stimulus_variant(
            obj, texture_seed(texture_set), stimulus_mode=mode, variant_index=1
        )
        out_png.parent.mkdir(parents=True, exist_ok=True)
        scene.render_still(str(out_png))
    finally:
        if prev_force is not None:
            os.environ["STIM_FORCE_TEXTURE_SET"] = prev_force
        else:
            os.environ.pop("STIM_FORCE_TEXTURE_SET", None)
    return out_png.exists()


def main() -> None:
    plan_path = os.environ.get("STIM_GRID_PLAN", "").strip()
    if not plan_path:
        sys.exit("ERROR: STIM_GRID_PLAN is required")
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))

    grid_root = Path(plan["grid_root"])
    modes = plan["modes"]
    shapes = plan["shapes"]
    textures = plan["textures"]
    overwrite = bool(plan.get("overwrite", False))

    total = len(modes) * len(shapes) * len(textures)
    index = rendered = skipped = failed = 0
    print(f"grid: {len(modes)} modes x {len(shapes)} shapes x {len(textures)} textures "
          f"= {total} cells -> {grid_root}")

    for mode in modes:
        for shape in shapes:
            stl_id = shape["stl_id"]
            pending = [t for t in textures
                       if overwrite or not cell_path(grid_root, mode, t, stl_id).exists()]
            index += len(textures) - len(pending)
            skipped += len(textures) - len(pending)
            if not pending:
                continue

            obj = _prepare_shape(shape)
            if obj is None:
                index += len(pending)
                failed += len(pending)
                continue

            for texture_set in pending:
                index += 1
                print(f"[{index}/{total}] mode={mode} stl={stl_id} texture={texture_set}")
                if _render_cell(obj, cell_path(grid_root, mode, texture_set, stl_id),
                                texture_set=texture_set, mode=mode):
                    rendered += 1
                else:
                    failed += 1

    print(f"grid done: rendered={rendered} skipped={skipped} failed={failed} -> {grid_root}")
    if failed:
        sys.exit(f"ERROR: {failed} cells failed")


if __name__ == "__main__":
    main()
