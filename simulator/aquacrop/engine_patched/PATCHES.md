# Patches to the official FAO AquaCrop 7.3 Python engine

Base: `python.source.code.zip` from https://github.com/un-fao/fao-AquaCrop/releases/tag/v7.3
(SHA-256 `1eebc1b29f639cfba4528f515f38556482852009342937d64606332867e37cfc`). The official extraction in
`simulator/aquacrop/official_src/` is left untouched. GeoCrop runs this patched copy, which differs only as listed below.

## Patch 1: missing argument in `DetermineCCxAdjusted_Days` (`modules/simul.py`)

* **Symptom:** `TypeError: RequiredTimeNew() missing 1 required positional argument: 'VirtualTimeCC'`. The run aborts on the first day the canopy develops under water stress.
* **Cause:** in the Fortran original, `VirtualTimeCC` is a module-level variable. The Python port made it a parameter of `RequiredTimeNew(CCiToFind, CCo, CCx, CGCadjusted, VirtualTimeCC)`. One call site, in `DetermineCCxAdjusted_Days`, was not updated, while the other call (in `DetermineCCi`) passes it correctly.
* **Fix:** pass the enclosing function's own `VirtualTimeCC` parameter. This is a one-line change; see `patch1_RequiredTimeNew.diff`.
* **Scope:** this behaviour is only reached under canopy stress, so the official example (no project file shipped) does not exercise it.
* **Status:** should be reported upstream at https://github.com/un-fao/fao-AquaCrop/issues.
