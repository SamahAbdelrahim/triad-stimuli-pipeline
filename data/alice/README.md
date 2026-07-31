# ALICE shape set

The 30 novel-object meshes and their photographs from the ALICE stimulus set
(Xu & Sandhofer, 2024). See [`LICENSE.txt`](LICENSE.txt) for the terms they are
distributed under.

```
alice/
├── stl/       1.stl … 30.stl    meshes rendered by the pipeline
└── images/    1.PNG … 30.PNG    photographs of the physical objects
```

`stl/<id>.stl` and `images/<id>.PNG` are the same object, so the id is the join
key. `expand_stimuli.py` renders the meshes and copies the matching photograph
into each package as `example_image.png`.

This set is fixed at 30 objects. The rest of the pipeline (`automate_stimuli.py`,
`data/shapes/`) works on arbitrary STL pools and is the path for growing beyond
these 30.
