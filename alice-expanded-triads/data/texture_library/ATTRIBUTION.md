# Texture library attribution

Bundled PBR texture sets under `data/texture_library/` come from
[ambientCG](https://ambientcg.com/) (formerly CC0 Textures).

## License

All of these assets are released under **Creative Commons CC0 1.0 Universal**
(public domain dedication):

- https://creativecommons.org/publicdomain/zero/1.0/
- ambientCG license summary: https://ambientcg.com/list?type=Material&sort=Popular

You may use, modify, and redistribute them without attribution. Attribution
is still appreciated and is recorded here for provenance.

## Bundled sets (1K JPG packs)

Every folder is `<ambientCG asset ID>_1K-JPG`, so the asset ID is the folder name
with the `_1K-JPG` suffix removed.

Soft / cloth: Carpet008, Carpet013, Carpet014, Fabric001, Fabric002, Fabric004,
Fabric005, Fabric012, Fabric020, Fabric030, Fabric031, Fabric045, Fabric046,
Fabric047, Fabric062, Fabric070, Leather008, Leather010, Leather011, Leather028.

Hard / metallic / mineral: CorrugatedSteel005, CorrugatedSteel007B, Ground054,
Metal006, Metal007, Metal009, Metal022, Metal032, MetalPlates006, MetalPlates013,
PaintedMetal004, PaintedMetal005, PaintedMetal007, PaintedMetal008, Rust004,
Rust006, Rust008, SheetMetal001.

That is 38 sets. `expand_stimuli.py` crosses all of them with every shape, so
adding a set here grows the expanded stimulus set by one trial per shape per mode.

Additional sets fetched later via `scripts/fetch_cc0_textures.py` are also
ambientCG CC0 materials unless noted otherwise in that set's folder.

## Optional shape-generation add-on

Procedural STL generation (`generate_shapes.py`) can use the third-party
**Shape Generator** Blender add-on (Mark Kingsnorth). That add-on is **not**
bundled with this repository and remains under its own commercial license.
The STL meshes already shipped in `data/shapes/` are outputs of that tool
and may be redistributed with this pipeline; reinstalling the add-on is only
needed if you want to generate *new* shapes with `--generate`.
