"""Procedurally generate N novel STL shapes via the 'Shape Generator' add-on.

This generalizes scripts/add-on7-stl.py: instead of a fixed parameter grid it
produces exactly GEN_COUNT shapes into GEN_OUT_DIR as 1.stl .. N.stl (+ a
_params.json per shape), each from a distinct seed so the set is reproducible.

REQUIREMENT: the third-party 'Shape Generator' add-on (Mark Kingsnorth) must be
available to the bundled Blender. It is NOT installed by default. Provide the
add-on zip once via GEN_ADDON_ZIP and it will be installed + enabled, e.g.:

  GEN_COUNT=200 GEN_OUT_DIR=data/generated_stimuli/base \
  GEN_ADDON_ZIP=/path/to/shape_generator.1.7.12.zip \
  bash ./run_blender.sh -b -P generate_shapes.py

After the first install you can omit GEN_ADDON_ZIP.

Env vars:
  GEN_COUNT      number of shapes to create (default 200)
  GEN_OUT_DIR    output dir for STLs (default data/generated_stimuli/base)
  GEN_SEED_BASE  base random seed (default 1000); shape i uses GEN_SEED_BASE+i
  GEN_ADDON_ZIP  optional path to the Shape Generator add-on zip to install
"""

import json
import os
import sys
from pathlib import Path

import bpy

_PROJECT = Path(__file__).resolve().parent


def _enable_shape_generator() -> bool:
    zip_path = os.environ.get("GEN_ADDON_ZIP", "").strip()
    if zip_path:
        try:
            bpy.ops.preferences.addon_install(filepath=zip_path, overwrite=True)
            print(f"Installed add-on from {zip_path}")
        except Exception as exc:
            print(f"WARNING: addon_install failed for {zip_path}: {exc}")

    # The add-on registers under one of these module names across versions.
    for module in ("shape_generator", "ShapeGenerator", "shape-generator"):
        try:
            bpy.ops.preferences.addon_enable(module=module)
            if hasattr(bpy.ops.mesh, "shape_generator"):
                print(f"Enabled Shape Generator add-on (module={module})")
                return True
        except Exception:
            continue
    return hasattr(bpy.ops.mesh, "shape_generator")


def _generate_one(out_dir: Path, index: int, seed: int) -> bool:
    before = set(bpy.data.objects)

    # Vary complexity so the set spans simple->complex shapes.
    num_extrusions = 2 + (index % 9)          # 2..10
    extrusion_range = [0.05, 0.1, 0.15, 0.2, 0.3][index % 5]
    max_rotation = [30, 45, 90, 180, 360][index % 5]

    params = {
        "index": index,
        "random_seed": seed,
        "num_extrusions": num_extrusions,
        "min_extrude": 0.1,
        "max_extrude": 0.1 + extrusion_range,
        "min_rotation": 0,
        "max_rotation": max_rotation,
        "scale": [2, 2, 2],
    }

    bpy.ops.mesh.shape_generator(
        random_seed=seed,
        min_extrude=params["min_extrude"],
        max_extrude=params["max_extrude"],
        min_rotation=params["min_rotation"],
        max_rotation=params["max_rotation"],
        number_to_create=num_extrusions,
        auto_update=True,
    )
    bpy.ops.mesh.shape_generator_bake()

    new_objs = [o for o in (set(bpy.data.objects) - before) if o.type == "MESH"]
    if not new_objs:
        print(f"  WARNING: no mesh produced for index {index}")
        return False
    obj = new_objs[0]
    obj.location = (0, 0, 0)
    obj.scale = (2, 2, 2)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    stl_path = out_dir / f"{index + 1}.stl"
    # Blender 4.5 uses the built-in wm.stl_export operator.
    try:
        bpy.ops.wm.stl_export(filepath=str(stl_path), export_selected_objects=True)
    except Exception:
        bpy.ops.export_mesh.stl(filepath=str(stl_path), use_selection=True)

    (out_dir / f"{index + 1}_params.json").write_text(json.dumps(params, indent=2))
    print(f"  wrote {stl_path.name}")
    return True


def main() -> None:
    count = int(os.environ.get("GEN_COUNT", "200"))
    seed_base = int(os.environ.get("GEN_SEED_BASE", "1000"))
    out_raw = os.environ.get("GEN_OUT_DIR", "data/generated_stimuli/base").strip()
    out_dir = Path(out_raw)
    if not out_dir.is_absolute():
        out_dir = _PROJECT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if not _enable_shape_generator():
        sys.exit(
            "ERROR: 'Shape Generator' add-on not available. Install it once by "
            "passing GEN_ADDON_ZIP=/path/to/shape_generator.<version>.zip. "
            "This is a third-party add-on and is not bundled with this repo."
        )

    made = 0
    for i in range(count):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()
        if _generate_one(out_dir, i, seed_base + i):
            made += 1

    print(f"Done: generated {made}/{count} shapes -> {out_dir}")


if __name__ == "__main__":
    main()
