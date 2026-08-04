# ALICE expanded triads

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

There are two entry points. `automate_stimuli.py` gives each shape one texture,
which is the right shape of output when the shape pool is what you are growing.
[`expand_stimuli.py`](#expanded-stimuli-every-texture-on-every-shape) instead
puts *every* texture on *every* shape, which multiplies a fixed shape set into
far more trials; `example_image.png` there is the photograph of the real object
rather than a copy of `reference.png`.

Run all commands in this document from `alice-expanded-triads/`.

## Project layout

```
alice-expanded-triads/
├── automate_stimuli.py          # one-command orchestrator: one texture per shape
├── expand_stimuli.py            # orchestrator: every texture on every shape
├── render_stimuli.py            # Blender: renders triad packages  (bpy)
├── render_texture_grid.py       # Blender: renders the shape x texture grid (bpy)
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
    ├── alice/                   # fixed 30-object ALICE set: stl/ + images/
    ├── texture_library/         # bundled CC0 PBR sets (38, fabric/leather + metal/steel)
    └── generated_stimuli/       # OUTPUT (git-ignored): base/, distractors/, packages
```

## Prerequisites

1. **Blender 4.5** (headless). Either:
   - place a portable build at `blender-4.5.0-linux-x64/blender` in this project folder, or
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

## Expanded stimuli: every texture on every shape

`automate_stimuli.py` gives each shape a single hash-picked texture, so 30 shapes
means 30 trials per mode. `expand_stimuli.py` instead crosses the whole texture
library with the whole shape set, giving each shape one package per texture:

```bash
python3 expand_stimuli.py --stages plan          # inventory + trial count, no rendering
python3 expand_stimuli.py --res 1024 --samples 128
```

With the bundled 38 textures and the 30-object ALICE set in `data/alice/`, that
is **1140 trials per mode per version** instead of 30. Output keeps the folder
names `shapebias-bench2` already loads, with the texture as one extra level:

```
stimuli_unique_texture_per_stl_v1/
├── stimuli_B_controlled_simple/
│   ├── 1/
│   │   ├── Carpet008_1K-JPG/{example_image,reference,shape_match,texture_match}.png
│   │   └── ... one folder per texture ...
│   ├── 2/ ...
│   └── manifest.csv
├── stimuli_A_auto_contrast/ ...
└── combined_benchmark_manifest.csv
```

Each package obeys the usual rules: `reference` and `texture_match` share one
material and differ only in shape, `shape_match` keeps the shape and swaps the
texture, and `example_image` is the photograph of the real object.

Two things make this cheap. Every image comes from a single
(mode x shape x texture) render grid, so a package costs no renders of its own
and is placed as a hardlink — 38x30x2 = 2280 renders back the whole set, and the
packages add almost nothing on disk. And `v1` and `v2` are assembled from that
same grid, differing only in which texture `shape_match` gets and which shape
`texture_match` gets, so the second version is free.

The grid is resumable: cells already on disk are skipped, so an interrupted run
picks up where it stopped, and the work shards across machines with
`--only-stems`. Budget roughly 45 s per cell at `--res 1024 --samples 128` on a
CPU-only box (about 28 h for the full grid); `--res 512 --samples 64` is far
faster for pilots.

```
--stages          comma subset of: plan,grid,assemble,manifest,sync
--modes           render modes to build (default both)
--versions        v1,v2 (or the full package names)
--only-stems      restrict to some STL ids, e.g. 1,2,3
--max-textures N  use only the first N texture sets (smoke tests)
--res / --samples render resolution / Cycles samples
--link-mode       hardlink (default) | copy | symlink
--overwrite       re-render grid cells that already exist
--sync-to DIR     also mirror the version trees into a benchmark repo
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

The bundled library covers both modes. Every set you add is one more trial per
shape per mode in `expand_stimuli.py`, so growing the library is the cheapest way
to grow the expanded stimulus set. To add more CC0 PBR sets from ambientCG:
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
