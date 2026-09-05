<!-- provenance: GitLab <矩阵实验室组织>/quspin_v3_adms_xj issue #3 by <作者>, fetched 2026-09-05, state=opened -->
<!-- ======== ISSUE 1/1 · quspin_v3_adms_xj#3 · Add composable second-order derivatives for existing smooth QuSpin rules ======== -->

<!-- generated from <内部草稿文档>; edit the source draft and regenerate -->
<!-- classification: upstream_parity_gap; submit_enabled: true -->
# Add composable second-order derivatives for existing smooth QuSpin rules

## Summary

`quspin-ad` v0.1.0 provides analytic first-order JVP/VJP rules for seven
continuous QuSpin callables, including `ED_state_vs_time`, `commutator`,
`anti_commutator`, `lin_comb_Q_T`, `project_op`, `KL_div`, and
`coherent_state`.  Those rules cannot currently be differentiated again or
composed into a Hessian-vector product.  Consequently a workflow whose forward
path stays inside these already-supported, fixed-shape primitives still has to
fall back to finite differences for a second parameter response.  This issue is
limited to second-order composition over the implemented smooth rules; it does
not request a new QuSpin eigensolver, Floquet, entropy, or open-system API.

**Classification:** `upstream_parity_gap`

## Versions and scope

- Upstream software: QuSpin 1.0.1, pinned snapshot commit
  [`5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f`](https://github.com/QuSpin/QuSpin/tree/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f).
- AD package: [`quspin_v3_adms_xj`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj),
  version `0.1.0`, reviewed commit
  [`3fd649035b1d46d7657be011b3266a8520ef8103`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj/-/tree/3fd649035b1d46d7657be011b3266a8520ef8103).
- Private benchmark ledger:
  [`quspin-task-ledger.json`](<内部基准台账URL已脱敏>).
- Capability review: [`TASK_CAPABILITY_REVIEW.md`](TASK_CAPABILITY_REVIEW.md).
- Issue index: [`generated-issues/ISSUE_BUNDLE_INDEX.md`](generated-issues/ISSUE_BUNDLE_INDEX.md).

## Related tasks and papers

| Task | What it needs | Paper |
|---|---|---|
| [`quspin.dqpt_rate_second_derivative`](<内部基准台账URL已脱敏>) | Second directional derivative or HVP of a smooth Loschmidt-rate objective assembled from a fixed-shape `ED_state_vs_time` trajectory | [10.1103/PhysRevB.100.184313](https://doi.org/10.1103/PhysRevB.100.184313) |
| [`quspin.dynamical_structure_factor_edge_derivative`](<内部基准台账URL已脱敏>) | Second response of a smooth, broadened fixed-grid correlation/structure-factor objective built from time evolution and commutators | [10.1103/PhysRevB.75.205128](https://doi.org/10.1103/PhysRevB.75.205128) |

These task links provide scientific motivation only.  Acceptance is against
the bounded primitive-level contract below, not a claim that the complete
paper workflows are reproduced.

## Evidence of the gap

### Upstream operations

The pinned QuSpin source exposes the exact-diagonalization trajectory helper
`quspin.tools.evolution.ED_state_vs_time`, dense operator commutators,
Lanczos-vector linear combination, observable projection, KL divergence, and
coherent-state construction.  The reviewed sidecar already calls these
upstream functions for every primal value.

- [QuSpin evolution helpers](https://github.com/QuSpin/QuSpin/blob/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f/src/quspin/tools/evolution.py)
- [QuSpin operator helpers](https://github.com/QuSpin/QuSpin/blob/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f/src/quspin/operators/_functions.py)
- [QuSpin miscellaneous tools](https://github.com/QuSpin/QuSpin/blob/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f/src/quspin/tools/misc.py)
- [QuSpin Lanczos tools](https://github.com/QuSpin/QuSpin/blob/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f/src/quspin/tools/lanczos/_lanczos_utils.py)

### AD-package boundary

The package
[`api_inventory.json`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj/-/blob/3fd649035b1d46d7657be011b3266a8520ef8103/api_inventory.json)
marks the seven callables above as implemented at first order.  Their rules in
[`quspin_ad/rules.py`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj/-/blob/3fd649035b1d46d7657be011b3266a8520ef8103/quspin_ad/rules.py)
use NumPy operations to return ordinary tangent arrays and Python pullback
closures.  The bundled
[`quspin_ad/_chainrules.py`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj/-/blob/3fd649035b1d46d7657be011b3266a8520ef8103/quspin_ad/_chainrules.py)
only exposes `jvp`, `vjp`, `grad`, and `value_and_grad`; it has no nested-JVP,
Hessian, or HVP operation and no rule for differentiating a registered rule.

Thus first-order tangent values are available, but a second derivative of the
same supported smooth map is not an AD path.

## Minimal reproduction

```python
import numpy as np
import quspin_ad
import chainrules as ad

psi = np.array([1.0, 0.0], dtype=np.complex128)
E = np.array([-0.4, 0.7])
V = np.eye(2, dtype=np.complex128)
times = np.linspace(0.0, 2.0, 9)

value, dstate = ad.jvp(
    quspin_ad.ED_state_vs_time,
    psi, E, V, times,
    tangents={"E": np.array([0.2, -0.1])},
)

# First order is supported.  There is no package operation for differentiating
# this directional derivative again, for example:
# value, grad, hvp = ad.value_grad_and_hvp(loss, E, vector)
# or nested_jvp = ad.jvp(lambda x: ad.jvp(... x ...)[1], E, tangents={...})
```

The same missing composition is observable for bilinear `commutator`,
`anti_commutator`, `lin_comb_Q_T`, and `project_op`, and for nonlinear
`KL_div`, `coherent_state`, and `ED_state_vs_time`.  Zero Hessians for affine
directions and non-zero mixed/curvature terms should both be tested so that an
implementation cannot pass by returning zeros unconditionally.

## Expected capability

Provide a documented second-order composition interface for every currently
implemented smooth rule, at minimum a Hessian-vector product for real scalar
objectives and a nested directional-JVP equivalent.  It must preserve the
existing fixed-shape domains, real-linear complex cotangent convention, active
input names, output structures, and explicit boundary errors.  The
implementation should reuse the exact upstream primal and analytic first-order
rules; production finite differences are not an acceptable fallback.

## Acceptance criteria

- Each of the seven implemented callables has an HVP or nested-JVP check over
  every supported active input, including mixed active-input directions where
  applicable.
- `KL_div`, `coherent_state`, and `ED_state_vs_time` match an independent
  high-accuracy second-order oracle at regular points; affine/bilinear kernels
  match their analytic zero or mixed second derivatives.
- A small fixed-grid Loschmidt-rate fixture returns a finite second directional
  derivative with respect to `E` and agrees with an independent oracle.
- HVP symmetry/duality is checked for real scalar objectives, including complex
  states under the package's real-linear convention.
- Existing first-order JVP/VJP, zero-tangent, shape, dtype, and boundary tests
  remain passing.
- `a=0`, incompatible shapes, `iterate=True`, `out` mutation, and unsupported
  active inputs continue to fail explicitly rather than producing silent
  derivatives.

## Non-goals

- QuSpin Hamiltonian construction, `eigh`/`eigsh`/`eigvalsh`, or derivatives of
  eigenvectors and eigenvalue branches.
- Floquet eigensystems, Berry/QGT, entropy/SVD, thermal-state, Kubo, work-
  statistics, Lindblad/open-system, or non-Hermitian scientific abstractions.
- Adaptive ODE differentiation, full dynamic-control solver flow, sparse
  operator dispatch, changing basis/topology, or complete paper reproduction.