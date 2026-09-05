<!-- provenance: GitLab <矩阵实验室组织>/pycalphad_v3_adms_xj issue #1 by <作者>, fetched 2026-09-05, state=opened -->
<!-- ======== ISSUE 1/1 · pycalphad_v3_adms_xj#1 · Add composable second-order derivatives for fixed pycalphad Model properties ======== -->

# Add composable second-order derivatives for fixed pycalphad Model properties

## Summary

The pinned pycalphad `Model` exposes symbolic Gibbs-energy and thermodynamic
property expressions whose forward derivatives can be evaluated for a fixed
model and state. The reviewed `pycalphad-ad` v0.1.0 sidecar exposes only a
first-order JVP/VJP for `pycalphad_ad.evaluate(model, state, property_name)`.
Consequently, a chemical-potential derivative (a derivative of a Gibbs
derivative) and a thermodynamic Hessian cannot be obtained by nested AD or an
HVP. This is a focused derivative-composition gap over an existing upstream
symbolic forward path; it does not request differentiation through phase
selection or the equilibrium active set.

**Classification:** `upstream_parity_gap`

## Versions and scope

- Upstream pycalphad snapshot: `02c1ce1f16460b695d1a75a3e8d501edb295e7a6` (immutable `upstream/` snapshot in the package).
- AD package: [`pycalphad_v3_adms_xj`](https://<内部GitLab>/<矩阵实验室组织>/pycalphad_v3_adms_xj), commit [`85554b44ce0e0bb821f4e19a63b3c0c4be953386`](https://<内部GitLab>/<矩阵实验室组织>/pycalphad_v3_adms_xj/-/tree/85554b44ce0e0bb821f4e19a63b3c0c4be953386), version `0.1.0`.
- Private bench ledger: [`pycalphad-task-ledger.json`](https://<内部GitLab>/<作者>/ad-software-private-benchmark/-/blob/f1892156dd4f9a118bb1707b44b320d04af5247a/pycalphad/pycalphad-task-ledger.json).
- Capability review: [`TASK_CAPABILITY_REVIEW.md`](TASK_CAPABILITY_REVIEW.md).

## Related tasks and papers

| Task | Required derivative | Paper |
|---|---|---|
| `pycalphad.t044` | Derivative of a chemical potential with respect to composition/state, requiring a second derivative of Gibbs energy | [10.1039/c5ta01809a](https://doi.org/10.1039/c5ta01809a) |
| `pycalphad.t045` | Composition derivative of a redox potential derived from a thermodynamic property | [10.1007/s10853-021-06033-7](https://doi.org/10.1007/s10853-021-06033-7) |
| `pycalphad.t046` | Pressure/temperature derivative of a chemical potential | [10.1039/f19858102921](https://doi.org/10.1039/f19858102921) |
| `pycalphad.t106` | Derivative of an alloy chemical-potential observable | [10.48550/arXiv.2509.05991](https://doi.org/10.48550/arXiv.2509.05991) |
| `pycalphad.t112` | Compositionally coupled thermodynamic Hessian/HVP | [10.1016/j.matchar.2018.06.019](https://doi.org/10.1016/j.matchar.2018.06.019) |

## Evidence of the gap

### Upstream operation

In the pinned upstream source, `pycalphad.Model` builds symbolic Gibbs-energy
and thermodynamic property expressions and uses SymEngine differentiation.
The expression tree is therefore a fixed, continuous forward path on which a
second derivative/Hessian-vector product is well-defined away from singular
or piecewise boundaries.

### AD-package boundary

The v3 [`SPEC.md`](https://<内部GitLab>/<矩阵实验室组织>/pycalphad_v3_adms_xj/-/blob/85554b44ce0e0bb821f4e19a63b3c0c4be953386/pycalphad_ad/SPEC.md)
and [`api.py`](https://<内部GitLab>/<矩阵实验室组织>/pycalphad_v3_adms_xj/-/blob/85554b44ce0e0bb821f4e19a63b3c0c4be953386/pycalphad_ad/api.py)
define only `evaluate` with first-order state JVP/VJP. There is no documented
nested rule, HVP, Hessian output, or second-order result for a fixed Model
property. Equilibrium minimization, phase selection, database I/O and mapping
remain intentionally outside this issue.

## Minimal reproduction

```python
import pycalphad_ad

value, first = pycalphad_ad.jvp(
    pycalphad_ad.evaluate, model, state,
    tangents={"state": dstate}, property_name="GM",
)

# Required for t044/t045/t046/t106/t112, but unavailable today:
# value, hvp = pycalphad_ad.hvp(
#     pycalphad_ad.evaluate, model, state,
#     vector={"state": dstate}, property_name="GM",
# )
```

## Expected capability and acceptance criteria

- Add a documented nested JVP/VJP or HVP for fixed `Model` expressions, with
  active state variables and stable scalar/vector shapes.
- Verify first- and second-order results against SymEngine's exact second
  derivative on a two-component analytic model and an independent central-FD
  oracle used only in tests.
- Support chemical-potential composition/pressure/temperature derivatives and
  dense or directional Hessian products without requiring a dense Hessian.
- Raise explicit errors at non-finite, piecewise, zero-denominator and other
  non-differentiable points; preserve all existing first-order tests.

## Non-goals

This issue does not request derivatives through `equilibrium`, phase selection,
active-set changes, database parsing, mapping/grid topology, or a new phase
solver. Those are separate solver/workflow scope items.