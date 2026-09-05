<!-- provenance: GitLab <矩阵实验室组织>/tenpy_v3_adms_xj#1, fetched 2026-09-05 00:32, state=opened -->

# Add differentiable MPS overlap and MPO expectation contractions

## Summary

TeNPy exposes high-level, fixed-size contractions for an existing MPS/MPO
state: `MPO.expectation_value(psi)` evaluates an operator expectation value
and `MPS.overlap(psi)` evaluates the overlap of two states.  The reviewed
`tenpy_ad` v0.1.0 sidecar differentiates only low-level fixed-array
`npc.tensordot`, `npc.inner`, `npc.trace`, and related smooth primitives; it
does not register either state-level contraction or propagate tangents through
the MPS/MPO environments.  Consequently, two ordinary TeNPy post-processing
operations cannot be differentiated even when the MPS/MPO tensors and their
topology/canonical structure are held fixed.

**Classification:** `upstream_parity_gap`

## Versions and scope

- Upstream TeNPy source: commit [`0adfd60a81249f9e614f51a5436147c97d916f32`](https://github.com/tenpy/tenpy/tree/0adfd60a81249f9e614f51a5436147c97d916f32).
- AD package: [`tenpy_v3_adms_xj`](https://<内部GitLab>/<矩阵实验室组织>/tenpy_v3_adms_xj), reviewed commit [`76c77b78e4c367749ffc69ea87782d229a5534f6`](https://<内部GitLab>/<矩阵实验室组织>/tenpy_v3_adms_xj/-/tree/76c77b78e4c367749ffc69ea87782d229a5534f6), version `0.1.0`.
- Private benchmark ledger: [`tenpy-task-ledger.json`](https://<内部GitLab>/<作者>/ad-software-private-benchmark/-/blob/f1892156dd4f9a118bb1707b44b320d04af5247a/tenpy/tenpy-task-ledger.json).
- Capability review: [`TASK_CAPABILITY_REVIEW.md`](https://<内部GitLab>/<作者>/ad-software-private-benchmark/-/blob/f1892156dd4f9a118bb1707b44b320d04af5247a/tenpy/bench/private/0.1.0/TASK_CAPABILITY_REVIEW.md).

## Related tasks and papers

| Task ID | Required path | Paper |
|---|---|---|
| `tenpy.matrix-product-operator-expectation-gradient` | Build a finite MPS/MPO and differentiate the fixed-state `MPO.expectation_value` result with respect to tensor or smooth operator parameters. | [Continuous matrix product operator approach to finite temperature quantum states](https://doi.org/10.48550/arXiv.2004.12928) |
| `tenpy.mps-overlap-derivative-parameter` | Differentiate `MPS.overlap` for finite MPS with fixed bond dimensions, canonical data, and contraction topology. | [Exact overlaps for “all” integrable matrix product states of rational spin chains](https://doi.org/10.48550/arxiv.2410.23282) |

These references are the benchmark provenance; this issue requests the
underlying differentiable contraction primitive, not a full paper replay.

## Upstream evidence

- [`tenpy/networks/mpo.py`](https://github.com/tenpy/tenpy/blob/0adfd60a81249f9e614f51a5436147c97d916f32/tenpy/networks/mpo.py) defines `MPO.expectation_value(self, psi, tol=..., max_range=..., init_env_data=...)` and contracts the operator with an MPS using the environment machinery.
- [`tenpy/networks/mps.py`](https://github.com/tenpy/tenpy/blob/0adfd60a81249f9e614f51a5436147c97d916f32/tenpy/networks/mps.py) provides the public MPS overlap operation (including the finite-state contraction path).
- These are forward operations on already constructed states; no topology mutation is required for the bounded case in this issue.

## AD-package evidence

`tenpy_ad/SPEC.md` lists only fixed-array primitives such as
`npc.tensordot`, `npc.inner`, and `npc.trace` as implemented.  It explicitly
defers model/lattice construction, canonicalization/SVD, and iterative
DMRG/TEBD/TDVP/VUMPS engines.  `tenpy_ad/api_inventory.json` contains no
registered rule for `MPO.expectation_value` or `MPS.overlap`.  The capability
review therefore marks both tasks `partially_supported`: their low-level
contractions are available, but the upstream state-level composition is not.

## Minimal bounded reproduction

```python
import tenpy
import tenpy_ad

# psi and H_mpo are already-created finite TeNPy objects with fixed
# dimensions, charges, canonical structure, and contraction topology.
value = H_mpo.expectation_value(psi)
overlap = psi_a.overlap(psi_b)

# Desired API (names may follow the package's existing ChainRules surface):
d_value = tenpy_ad.jvp(H_mpo.expectation_value, (psi,),
                       tangents={"psi": d_psi})
d_overlap = tenpy_ad.jvp(psi_a.overlap, (psi_b,),
                         tangents={"psi_b": d_psi_b})
```

The probe must work without rebuilding a model or changing bond dimensions;
it should compose into a scalar loss and a VJP with respect to tensor entries
or explicitly declared smooth parameters.

## Expected capability and acceptance criteria

- Register JVP and VJP rules for finite `MPO.expectation_value` and finite
  `MPS.overlap`, including the normalized-expectation denominator where
  applicable.
- Propagate tangents through the existing environment contractions using
  real-linear complex conventions consistent with the current sidecar.
- Support tensor-entry/parameter derivatives while topology, charges, bond
  dimensions, canonical gauges, and contraction ranges remain fixed.
- Match analytic/independent central-FD checks on small dense finite-MPS/MPO
  fixtures for value, JVP, VJP, and a composed scalar objective.
- Return documented errors for unsupported infinite-state, singular-norm,
  truncating, or topology-changing cases rather than silently differentiating
  through them.

## Non-goals

- No AD rules for DMRG, TEBD, TDVP, VUMPS, METTS, truncation, SVD/QR, or any
  iterative eigensolver are requested here.
- No model/lattice construction, charge-sector discovery, canonicalization,
  topology changes, or new tensor-network algorithms.
- No Berry/QGT, thermal, open-system, or other convenience observable layer;
  those remain separate extension/new-solver proposals.
