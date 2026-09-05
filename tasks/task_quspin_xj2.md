<!-- provenance: GitLab <矩阵实验室组织>/quspin_v3_adms_xj issue #2 by <作者>, fetched 2026-09-05, state=opened -->
<!-- ======== ISSUE 1/1 · quspin_v3_adms_xj#2 · Add differentiable Floquet eigensystems and quasienergy branches ======== -->

<!-- generated from <内部草稿文档>; edit the source draft and regenerate -->
<!-- classification: upstream_parity_gap; submit_enabled: true -->
# Add differentiable Floquet eigensystems and quasienergy branches

## Summary

QuSpin exposes a Floquet forward object that constructs one-period evolution
and diagonalizes its Floquet operator. The reviewed `quspin-ad` v0.1.0 sidecar
has no derivative rule for that existing eigensystem: it cannot return
quasienergy or eigenvector tangents with respect to drive phase, gauge, or
momentum. This is one reusable upstream-parity gap across the listed Floquet
tasks; it is not a request for a new physical observable.

**Classification:** `upstream_parity_gap`

## Versions and scope

- Upstream software: QuSpin 1.0.1; sidecar upstream snapshot commit [`5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f`](https://github.com/QuSpin/QuSpin/tree/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f).
- AD package: [`quspin_v3_adms_xj`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj), reviewed commit [`3fd649035b1d46d7657be011b3266a8520ef8103`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj/-/tree/3fd649035b1d46d7657be011b3266a8520ef8103).
- Private benchmark ledger: [`quspin-task-ledger.json`](<内部基准台账URL已脱敏>).
- Capability review: [`TASK_CAPABILITY_REVIEW.md`](TASK_CAPABILITY_REVIEW.md).

## Related tasks and papers

| Task | What it needs | Paper |
|---|---|---|
| `quspin.floquet_quasienergy_power_derivative` | Drive-phase derivative of Floquet quasienergies | [10.48550/arXiv.2307.02639](https://doi.org/10.48550/arXiv.2307.02639) |
| `quspin.floquet_gauge_current_derivative` | Floquet Hellmann–Feynman derivative with respect to synthetic gauge | [10.48550/arXiv.2012.09677](https://doi.org/10.48550/arXiv.2012.09677) |
| `quspin.floquet_quasienergy_velocity` | Momentum derivative of a Floquet quasienergy branch | [10.1140/epjb/e2020-10133-3](https://doi.org/10.1140/epjb/e2020-10133-3) |

## Evidence of the gap

### Upstream operation

The pinned QuSpin source contains the public `Floquet` and `Floquet_t_vec`
tools for building a period propagator, extracting Floquet eigenvalues and
eigenvectors, and evaluating time vectors for a driven Hamiltonian.

- [QuSpin Floquet implementation](https://github.com/QuSpin/QuSpin/blob/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f/src/quspin/tools/Floquet.py)
- [QuSpin Floquet documentation](https://github.com/QuSpin/QuSpin/tree/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f/docs)

### AD-package boundary

The v3 [`api_inventory.json`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj/-/blob/3fd649035b1d46d7657be011b3266a8520ef8103/quspin_ad/api_inventory.json)
explicitly marks `quspin.tools.Floquet.Floquet` and `Floquet_t_vec` deferred
because spectral decomposition and branch choices have no rule. The registered
rules in [`quspin_ad/rules.py`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj/-/blob/3fd649035b1d46d7657be011b3266a8520ef8103/quspin_ad/rules.py)
contain no Floquet eigensystem or quasienergy derivative.

## Minimal reproduction

```python
from quspin.tools.Floquet import Floquet
import quspin_ad

floquet = Floquet(FT, HF, t_list=[0.0, T], t=T)  # upstream forward object
eps = floquet.EF  # quasienergies (modulo the drive frequency)

# Desired API (currently unavailable):
# value, tangent = quspin_ad.jvp(floquet.EF, tangents={"drive_phase": 1.0})
```

The probe is finite and only checks the existing forward object. A derivative
must reject branch crossings/degenerate eigenvalues rather than silently
relabeling quasienergies.

## Expected capability

Expose JVP/VJP for a fixed-dimensional one-period Floquet eigensystem with a
documented quasienergy branch convention, phase/gauge-invariant eigenvector
projector or phase alignment, active drive-phase/gauge/momentum inputs, and
explicit spectral-gap/degeneracy errors. Fixed-grid drives are sufficient for
the first implementation.

## Acceptance criteria

- Analytic two-step unitary eigenphases pass JVP/VJP and independent
  high-precision finite-difference checks away from crossings.
- A driven lattice fixture gives branch-consistent phase/momentum derivatives
  and raises a documented error at a deliberate degeneracy.
- Eigenvector observables are invariant under arbitrary input eigenvector phase
  changes (or use projectors), and existing sidecar tests remain passing.

## Non-goals

- Integer winding-number derivatives at a gap closing.
- Berry/QGT geometry, thermal/open-system Floquet machines, or adaptive ODE
  differentiation; those are separate extension/new-solver scopes.