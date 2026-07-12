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

| Folder | ambientCG asset ID |
|--------|--------------------|
| Carpet013_1K-JPG | Carpet013 |
| Carpet014_1K-JPG | Carpet014 |
| CorrugatedSteel005_1K-JPG | CorrugatedSteel005 |
| Fabric001_1K-JPG | Fabric001 |
| Fabric012_1K-JPG | Fabric012 |
| Fabric030_1K-JPG | Fabric030 |
| Fabric045_1K-JPG | Fabric045 |
| Fabric046_1K-JPG | Fabric046 |
| Fabric062_1K-JPG | Fabric062 |
| Fabric070_1K-JPG | Fabric070 |
| Leather011_1K-JPG | Leather011 |
| Leather028_1K-JPG | Leather028 |
| Metal006_1K-JPG | Metal006 |
| Metal032_1K-JPG | Metal032 |
| MetalPlates006_1K-JPG | MetalPlates006 |
| MetalPlates013_1K-JPG | MetalPlates013 |
| PaintedMetal004_1K-JPG | PaintedMetal004 |
| PaintedMetal008_1K-JPG | PaintedMetal008 |
| Rust004_1K-JPG | Rust004 |
| Rust006_1K-JPG | Rust006 |
| SheetMetal001_1K-JPG | SheetMetal001 |

Additional sets fetched later via `scripts/fetch_cc0_textures.py` are also
ambientCG CC0 materials unless noted otherwise in that set's folder.

## Optional shape-generation add-on

Procedural STL generation (`generate_shapes.py`) can use the third-party
**Shape Generator** Blender add-on (Mark Kingsnorth). That add-on is **not**
bundled with this repository and remains under its own commercial license.
The STL meshes already shipped in `data/shapes/` are outputs of that tool
and may be redistributed with this pipeline; reinstalling the add-on is only
needed if you want to generate *new* shapes with `--generate`.
