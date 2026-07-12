"""Render 2AFC cue-conflict triad stimuli from an arbitrary set of STL shapes.

For each base STL it writes one benchmark-ready package:
  <out>/<mode>/<stem>/example_image.png   copy of reference
  <out>/<mode>/<stem>/reference.png       shape S + texture T   (variant 1)
  <out>/<mode>/<stem>/shape_match.png     shape S + texture T'  (variant 2)
  <out>/<mode>/<stem>/texture_match.png   shape S' + texture T  (distractor, variant 1)
plus a per-mode manifest.csv.

reference and texture_match share the exact same material (same forced texture
set + color seed), so only shape differs; shape_match keeps the shape but swaps
to a contrasting material. This is the cue-conflict triad used in the
developmental shape-bias / word-extension task.

Run through the Blender wrapper (this is a bpy script, not plain Python):
  STIM_INPUT_DIR=data/generated_stimuli/base \
  STIM_DISTRACTOR_DIR=data/generated_stimuli/distractors \
  STIM_OUT_DIR=data/generated_stimuli/stimuli_per_stl_packages \
  STIM_MODE=B_controlled_simple STIM_RES=1024 STIM_SAMPLES=128 \
  bash ./run_blender.sh -b -P render_stimuli.py

Env vars:
  STIM_INPUT_DIR        (required) dir of base STLs; each file = one object
  STIM_DISTRACTOR_DIR   (required) dir of STLs used as the texture_match shape
  STIM_OUT_DIR          (required) packages root (mode subfolders created here)
  STIM_MODE             B_controlled_simple | A_auto_contrast (default B)
  STIM_RES              square render resolution (default 1024)
  STIM_SAMPLES          Cycles samples (default 128)
  STIM_ONLY_STEMS       optional comma list to render a subset (e.g. 1,2,3)
  STIM_USE_IMAGE_TEXTURES  1/0 use PBR image textures (default 1)
  STIM_TEXTURE_LIBRARY  optional absolute path to texture sets (default data/texture_library)
"""

import csv
import os
import shutil
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent
_SCRIPTS = _PROJECT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import stl_spin_render as scene
import stl_material_overlay_render as mats

_VALID_MODES = {"B_controlled_simple", "A_auto_contrast"}


# --------------------------------------------------------------------------- #
# env helpers
# --------------------------------------------------------------------------- #
def _parse_positive_int(raw: str, default: int) -> int:
    try:
        value = int(raw)
    except Exception:
        return default
    return value if value > 0 else default


def _require_dir(env_name: str) -> Path:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        sys.exit(f"ERROR: {env_name} is required")
    path = Path(raw)
    if not path.is_absolute():
        path = _PROJECT / path
    return path


def _mode_from_env() -> str:
    mode = os.environ.get("STIM_MODE", "B_controlled_simple").strip() or "B_controlled_simple"
    if mode not in _VALID_MODES:
        sys.exit(f"ERROR: STIM_MODE must be one of {sorted(_VALID_MODES)}, got {mode!r}")
    return mode


def _only_stems_from_env():
    raw = os.environ.get("STIM_ONLY_STEMS", "").strip()
    if not raw:
        return None
    return {x.strip() for x in raw.split(",") if x.strip()}


def _list_stls(base: Path):
    return sorted(base.glob("*.stl"),
                  key=lambda p: (int(p.stem) if p.stem.isdigit() else 1 << 30, p.name.lower()))


# --------------------------------------------------------------------------- #
# scene / material rig (studio look; no dependency on any reference photo)
# --------------------------------------------------------------------------- #
def _set_dark_gray_background() -> None:
    world = scene.bpy.context.scene.world
    if world is None:
        world = scene.bpy.data.worlds.new("World")
        scene.bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    bg = nodes.new(type="ShaderNodeBackground")
    out = nodes.new(type="ShaderNodeOutputWorld")
    bg.inputs[0].default_value = (0.08, 0.08, 0.08, 1.0)
    bg.inputs[1].default_value = 0.55
    links.new(bg.outputs[0], out.inputs[0])


def _set_balanced_color_management(*, exposure: float) -> None:
    view = scene.bpy.context.scene.view_settings
    try:
        view.view_transform = "Filmic"
        view.look = "None"
    except Exception:
        pass
    view.exposure = exposure
    view.gamma = 1.0


def _rebalance_lighting_soft(object_size: float) -> None:
    bpy = scene.bpy
    for obj in list(bpy.data.objects):
        if obj.type == "LIGHT":
            bpy.data.objects.remove(obj, do_unlink=True)

    distance = object_size * 4.0
    area_specs = [
        ("FrontKey", 1200.0, (0, -distance * 1.45, object_size * 0.80), (90, 0, 0), object_size * 3.2),
        ("BackFill", 950.0, (0, distance * 1.45, object_size * 0.80), (90, 0, 180), object_size * 3.2),
        ("LeftFill", 750.0, (-distance * 1.25, 0, object_size * 0.70), (90, 0, -90), object_size * 2.9),
        ("RightFill", 750.0, (distance * 1.25, 0, object_size * 0.70), (90, 0, 90), object_size * 2.9),
        ("TopSoft", 850.0, (0, 0, distance * 1.70), (180, 0, 0), object_size * 4.0),
    ]
    for name, energy, location, rotation_deg, size in area_specs:
        light_data = bpy.data.lights.new(name=name, type="AREA")
        light_data.energy = energy
        light_data.shape = "SQUARE"
        light_data.size = size
        light_obj = bpy.data.objects.new(name=name, object_data=light_data)
        bpy.context.collection.objects.link(light_obj)
        light_obj.location = location
        light_obj.rotation_euler = tuple(scene.radians(v) for v in rotation_deg)


def _configure_stimulus_render_controls() -> None:
    render = scene.bpy.context.scene.render
    cycles = scene.bpy.context.scene.cycles
    res = _parse_positive_int(os.environ.get("STIM_RES", "").strip(), 1024)
    samples = _parse_positive_int(os.environ.get("STIM_SAMPLES", "").strip(), 128)
    render.resolution_x = res
    render.resolution_y = res
    cycles.samples = samples


def _texture_preferences_for_mode(stimulus_mode: str):
    if stimulus_mode == "B_controlled_simple":
        return ["fabric", "cloth", "carpet", "leather"]
    return ["steel", "metal", "rust", "corrugated"]


def _forced_texture_set_name(seed: int, stimulus_mode: str) -> str:
    picker_seed = seed if stimulus_mode == "B_controlled_simple" else (seed ^ 0x5A5A)
    tex_set = mats._pick_texture_set(picker_seed, prefer_keywords=_texture_preferences_for_mode(stimulus_mode))
    return tex_set.name if tex_set is not None else ""


def _render_variant_png(stl_path: Path, out_png: Path, *, seed: int, stimulus_mode: str, variant_index: int) -> bool:
    scene.clear_scene()
    scene.bpy.ops.wm.stl_import(filepath=str(stl_path))
    selected = list(scene.bpy.context.selected_objects)
    if not selected:
        print(f"WARNING: failed to import STL: {stl_path}")
        return False

    obj = selected[0]
    object_size = scene.center_and_scale_object(obj, target_size=2.0)
    scene.setup_scene(obj, object_size, material_mode="flat", material_seed=seed)
    _set_dark_gray_background()
    _set_balanced_color_management(exposure=0.20)
    _rebalance_lighting_soft(object_size)
    _configure_stimulus_render_controls()
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (0.0, 0.0, 0.0)
    mats.apply_material_stimulus_variant(obj, seed, stimulus_mode=stimulus_mode, variant_index=variant_index)
    scene.render_still(str(out_png))
    return True


def _pick_distractor(index: int, base_stem: str, distractors):
    n = len(distractors)
    for off in range(n):
        cand = distractors[(index + off) % n]
        if cand.stem != base_stem:
            return cand
    return distractors[index % n]


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    input_dir = _require_dir("STIM_INPUT_DIR")
    distractor_dir = _require_dir("STIM_DISTRACTOR_DIR")
    out_root = _require_dir("STIM_OUT_DIR")
    mode = _mode_from_env()

    base_stls = _list_stls(input_dir)
    distractors = _list_stls(distractor_dir)
    if not base_stls:
        sys.exit(f"ERROR: no .stl files in {input_dir}")
    if not distractors:
        sys.exit(f"ERROR: no .stl files in {distractor_dir}")

    only = _only_stems_from_env()
    mode_dir = out_root / mode
    mode_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for idx, base_stl in enumerate(base_stls):
        stem = base_stl.stem
        if only is not None and stem not in only:
            continue

        stem_dir = mode_dir / stem
        stem_dir.mkdir(parents=True, exist_ok=True)
        ref_png = stem_dir / "reference.png"
        shape_png = stem_dir / "shape_match.png"
        tex_png = stem_dir / "texture_match.png"
        example_png = stem_dir / "example_image.png"

        seed = scene._stable_int(str(base_stl))
        forced_set = _forced_texture_set_name(seed, mode)
        distractor = _pick_distractor(idx, stem, distractors)

        print(f"[{idx + 1}/{len(base_stls)}] stem={stem} seed={seed} "
              f"texture_set={forced_set or 'auto'} distractor={distractor.name}")

        prev_force = os.environ.get("STIM_FORCE_TEXTURE_SET")
        if forced_set:
            os.environ["STIM_FORCE_TEXTURE_SET"] = forced_set
        try:
            ok = _render_variant_png(base_stl, ref_png, seed=seed, stimulus_mode=mode, variant_index=1)
            ok = _render_variant_png(base_stl, shape_png, seed=seed, stimulus_mode=mode, variant_index=2) and ok
            ok = _render_variant_png(distractor, tex_png, seed=seed, stimulus_mode=mode, variant_index=1) and ok
        finally:
            if prev_force is not None:
                os.environ["STIM_FORCE_TEXTURE_SET"] = prev_force
            else:
                os.environ.pop("STIM_FORCE_TEXTURE_SET", None)

        if not ok:
            print(f"  WARNING: render incomplete for stem {stem}; skipping package")
            continue

        shutil.copyfile(ref_png, example_png)

        def rel(p):
            return str(p.relative_to(out_root))

        records.append({
            "mode": mode,
            "stl_id": stem,
            "example_image": rel(example_png),
            "reference": rel(ref_png),
            "shape_match": rel(shape_png),
            "texture_match": rel(tex_png),
            "shape_stl": base_stl.name,
            "distractor_stl": distractor.name,
            "forced_texture_set": forced_set,
        })

    _write_manifest(mode_dir, records)
    print(f"Done: {len(records)} packages -> {mode_dir}")


def _write_manifest(mode_dir: Path, records) -> None:
    manifest = mode_dir / "manifest.csv"
    fields = ["mode", "stl_id", "example_image", "reference", "shape_match",
              "texture_match", "shape_stl", "distractor_stl", "forced_texture_set"]

    # Merge with existing rows so a subset re-render (STIM_ONLY_STEMS) does not
    # discard packages produced by earlier runs.
    merged = {}
    if manifest.exists():
        with manifest.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sid = row.get("stl_id", "").strip()
                if sid:
                    merged[sid] = {k: row.get(k, "") for k in fields}
    for rec in records:
        merged[rec["stl_id"]] = rec

    ordered = sorted(merged.values(),
                     key=lambda r: (int(r["stl_id"]) if str(r["stl_id"]).isdigit() else 1 << 30, r["stl_id"]))
    with manifest.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(ordered)
    print(f"Manifest -> {manifest}")


if __name__ == "__main__":
    main()
