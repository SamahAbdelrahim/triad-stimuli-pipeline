# triad-stimuli-pipeline

A self-contained pipeline for generating **2AFC triad stimuli** for
shape-bias / word-extension benchmarks. Given a set of 3D shapes and a texture
library, it renders, for every object, a benchmark-ready package:

| file | shape | texture | role |
|------|-------|---------|------|
| `reference.png` | S | T | the standard / example object |
| `shape_match.png` | **S** (same) | T′ (different) | matches on **shape** |
| `texture_match.png` | S′ (different) | **T** (same) | matches on **texture** |
| `example_image.png` | — | — | copy of `reference.png` (the object shown first) |

`reference` and `texture_match` share the *exact* same material, so only shape
differs between them; `shape_match` keeps the shape but swaps to a contrasting
material. This is the classic Landau/Smith forced-choice format.

Two texture "modes" are supported:
- `B_controlled_simple` — soft materials (fabric / leather / carpet), same color
  family, matte-vs-patterned.
- `A_auto_contrast` — hard materials (metal / steel / rust), high color/finish
  separation.

Everything is deterministic: the material for an object is a hash of its STL
path, so re-running reproduces identical stimuli.

## Repository layout

```
triad-stimuli-pipeline/
├── automate_stimuli.py          # one-command orchestrator (plain python3)
├── render_stimuli.py            # Blender: renders triad packages  (bpy)
├── generate_shapes.py           # Blender: optional shape generation via add-on (bpy)
├── run_blender.sh               # locates + launches the bundled/system Blender
├── requirements.txt
├── scripts/
│   ├── stl_spin_render.py               # scene: import/center/scale/lighting/render
│   ├── stl_material_overlay_render.py   # material + PBR texture engine
│   ├── fetch_cc0_textures.py            # download more CC0 PBR sets (ambientCG)
│   └── install_libxkbcommon_user.sh     # Linux-only Blender lib helper (no sudo)
└── data/
    ├── shapes/                  # bundled STL pool (540 procedural shapes)
    ├── texture_library/         # bundled CC0 PBR sets (fabric/leather + metal/steel)
    └── generated_stimuli/       # OUTPUT (git-ignored): base/, distractors/, packages
```

## Prerequisites

1. **Blender 4.5** (headless). Either:
   - place a portable build at `blender-4.5.0-linux-x64/blender` in the repo root, or
   - have `blender` on your `PATH`.
   `run_blender.sh` finds whichever is available.
2. **Linux without sudo:** if Blender fails with `libxkbcommon.so.0`, run once:
   ```bash
   bash scripts/install_libxkbcommon_user.sh
   ```
   `run_blender.sh` then picks the user-local libs automatically.
3. **Python 3.9+** for the orchestrator (standard library only — see `requirements.txt`).
4. `ffmpeg` is **not** required (stimuli are PNG stills).

## Quickstart

Smoke test (5 objects, low res, fast):
```bash
python3 automate_stimuli.py --n 5 --modes B_controlled_simple --res 384 --samples 24
```

Full run — 200 objects, both modes, high quality:
```bash
python3 automate_stimuli.py --n 200 \
  --modes B_controlled_simple,A_auto_contrast \
  --res 1024 --samples 128
```

Output lands in `data/generated_stimuli/stimuli_per_stl_packages/<mode>/<id>/`
plus per-mode `manifest.csv` and a top-level `combined_benchmark_manifest.csv`.

Point stimuli at a downstream benchmark repo with `--sync-to`:
```bash
python3 automate_stimuli.py --n 200 --sync-to /path/to/benchmark/stimuli_per_stl_packages
```

## Where the shapes come from

- **Bundled pool (default):** `data/shapes/` ships 540 procedurally generated
  shapes. `automate_stimuli.py` samples an evenly-spread subset for the base
  objects and a disjoint subset for the texture-match distractors.
- **Generate brand-new shapes (unlimited):** uses the third-party *Shape
  Generator* Blender add-on (Mark Kingsnorth), which is **not bundled**. Install
  it once by passing its zip, then generate:
  ```bash
  python3 automate_stimuli.py --n 300 --generate \
    --addon-zip /path/to/shape_generator.<version>.zip
  ```
  Add your own STLs simply by dropping `.stl` files into a folder and passing
  `--source /that/folder`.

## Expanding the texture library

The bundled library covers both modes. To add more CC0 PBR sets from ambientCG:
```bash
python3 scripts/fetch_cc0_textures.py --res 1K            # curated default list
python3 scripts/fetch_cc0_textures.py --only Fabric055 Metal017
```
Rules for a set to be usable by the engine:
- one folder per set under `data/texture_library/<name>/`;
- filenames contain a base-color keyword (`color`/`basecolor`/`albedo`/`diffuse`);
- optional `roughness`, `normalgl`, `displacement`, `metalness` maps improve realism;
- prefix a folder with `NO - ` to exclude it from selection;
- for mode selection, put `fabric`/`leather`/`carpet` (mode B) or
  `metal`/`steel`/`rust`/`corrugated` (mode A) in the folder name.

## Orchestrator options

```
--n N                 number of base objects (default 200)
--distractors M       distractor pool size when sampling (default 40)
--source DIR          STL pool to sample (default data/shapes)
--generate            create fresh shapes via the add-on instead of sampling
--addon-zip PATH      Shape Generator add-on zip (first-time install)
--modes A,B           comma list (B_controlled_simple, A_auto_contrast)
--res / --samples     render resolution / Cycles samples
--no-image-textures   procedural materials only (skip PBR image maps)
--out DIR             output root (default data/generated_stimuli)
--sync-to DIR         also copy packages into a benchmark repo
--stages ...          subset of: select,render,manifest,sync
```

## Notes

- **Render time** scales with objects × modes × 3 images × resolution × samples,
  and Cycles is CPU-bound without a GPU. For 200 objects at 1024/128 expect a
  long run — prefer a GPU box / cluster; tune `--res`/`--samples` for previews.
- `data/generated_stimuli/` is git-ignored; commit only inputs + code.
- Large 4K texture packs are heavy for git — prefer Git LFS or re-fetching them.

## License and attribution

- **Code and pipeline scripts:** MIT — see [`LICENSE`](LICENSE).
- **Bundled textures** (`data/texture_library/`): [ambientCG](https://ambientcg.com/)
  materials under **CC0 1.0** — see [`data/texture_library/ATTRIBUTION.md`](data/texture_library/ATTRIBUTION.md)
  for the full asset list and notes on the optional Shape Generator add-on.
