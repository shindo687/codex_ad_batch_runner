<!-- provenance: GitLab <矩阵实验室组织>/kwant_v3_adms_xj#3, fetched 2026-09-05, state=opened -->

# Bands eigenvector derivatives are rejected, blocking Berry/QGT and BdG sensitivities

## Summary

Upstream `kwant.physics.Bands.__call__` exposes `return_eigenvectors=True` and
returns Bloch eigenvectors alongside energies and velocity/curvature. The
kwant-ad sidecar registers an analytic JVP/VJP only for the scalar-momentum
energy/velocity/curvature outputs and **explicitly rejects** any call with
`return_eigenvectors=True` via `NonDifferentiablePoint`. Eigenvector tangents
are the required ingredient for Berry connections, quantum geometric tensors,
and several bound-state/BdG sensitivity tasks in the 24-task public
benchmark, so those tasks are `partially_supported` or `cannot_implement`
purely because this derivative path is missing.

**Classification:** `upstream_parity_gap`

## Versions and scope

- Upstream software: Kwant upstream snapshot commit [`ef12fa0d78e25bd8ab5a5e6d7587c6b0d274bea6`](https://gitlab.kwant-project.org/kwant/kwant/-/tree/ef12fa0d78e25bd8ab5a5e6d7587c6b0d274bea6).
- AD package: [`kwant_v3_adms_xj`](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj), reviewed commit [`fd4470d049d01bc0486eaa96f7b76a570ea6915f`](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/commit/fd4470d049d01bc0486eaa96f7b76a570ea6915f).
- Capability review: `package-reviews/kwant/bench/public/0.1.0-fd4470d0/TASK_CAPABILITY_REVIEW.md` (public benchmark `c4e583b`, 24 tasks).

## Related tasks and papers

| Task | What it needs | Paper (doi) |
|---|---|---|
| `kwant.berry_curvature_chern_from_k_derivatives` | k-derivatives of Bloch eigenvectors for Berry connection on a finite BZ mesh | 10.1103/PhysRevB.102.165148 |
| `kwant.quantum_metric_eigenstate_derivatives` | eigenvector derivatives for the quantum geometric tensor | 10.1103/physrevb.92.201403 |
| `kwant.josephson_current_phase_derivative` | φ-derivative of BdG bound-state spectrum/current | 10.1103/PhysRevB.102.165148 |
| `kwant.majorana_splitting_parameter_sensitivity` | parameter derivative of Majorana/Andreev splittings | 10.1103/physrevb.92.201403 |

## Evidence of the gap

### Upstream operation

`upstream/src/kwant/physics/dispersion.py` in host snapshot `ef12fa0` defines
`Bands.__call__(k, derivative_order=0, return_eigenvectors=False)`; with
`return_eigenvectors=True` it also returns the Bloch eigenvectors of the
translation operator. The forward surface therefore exists at the pinned
upstream.

### AD boundary

`kwant_ad/_rules.py::_bands_state` begins with:

```python
if return_eigenvectors:
    raise NonDifferentiablePoint(function, "eigenvector derivatives are not supported")
```

and `kwant_ad/SPEC.md` documents the same boundary ("Degenerate bands and
eigenvector derivatives are rejected explicitly"). No rule touches
eigenvector output.

### Minimal reproduction

```python
import kwant
import kwant_ad
from kwant_ad import jvp, band_energies
from kwant.physics import Bands

lat = kwant.lattice.square(a=1)
lead = kwant.Builder(kwant.TranslationalSymmetry((-1, 0)))
lead[(lat(0, j) for j in range(4))] = 4
lead[lat.neighbors()] = -1
fsys = lead.finalized()
b = Bands(fsys)

jvp(band_energies, b, 0.3, tangents={"k": 1.0}, return_eigenvectors=True)
```

Observed (probe at commit `fd4470d0`): `NonDifferentiablePoint:
eigenvector derivatives are not supported`. Expected: the energies plus a
tangent for the eigenvector array on a non-degenerate band, with an explicit
boundary only where degeneracy makes the eigenbasis gauge-ambiguous.

## Expected capability

An eigenvector JVP/VJP for `Bands.__call__`/`band_energies` for
`return_eigenvectors=True`: active inputs `k` (scalar, matching the existing
Bands rules), output tangent following the band-wise eigenvector array shape,
real-linear contraction per the package's documented convention. Degenerate
bands must raise `NonDifferentiablePoint` (degenerate eigenvector derivatives
are gauge-ambiguous) rather than return silent values.

## Acceptance criteria

- jvp on a non-degenerate band matches central differences on eigenvector
  components within the package tolerance (`1e-6`…`1e-5`), and the VJP
  contracts to a real scalar for the band objective.
- Degenerate-band case raises `NonDifferentiablePoint`.
- A bounded `berry_curvature_chern_from_k_derivatives`-shaped probe (two-band
  model, finite BZ mesh, Berry curvature from band-velocity + eigenvector
  rules) assembles through the exposed surface.
- Existing Bands energy/velocity rules and the 18-test suite remain passing.

## Non-goals

- No eigenvector derivatives through the scattering solver (`smatrix`
  eigen/channel state) — tracked in the separate scattering-derivative issue.
- No gauge-fixing research for degenerate bands (explicit rejection is
  acceptable there).
- No second-order eigenvector derivatives or higher-order geometric
  response beyond first order.