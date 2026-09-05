<!-- provenance: GitLab <矩阵实验室组织>/pycalphad_v3_adms_xj issue #2 by <作者>, fetched 2026-09-05, state=opened -->
<!-- ======== ISSUE 1/1 · pycalphad_v3_adms_xj#2 · Add implicit derivatives for pycalphad equilibrium and calculate workflows ======== -->

# Add implicit derivatives for pycalphad equilibrium and calculate workflows

## Summary

The pinned pycalphad release exposes `calculate`, `equilibrium` and the
stateful `Workspace` workflow for evaluating Gibbs energies, selecting active
phases and solving constrained equilibria. The reviewed `pycalphad-ad`
v0.1.0 package instead differentiates only a fixed, already-constructed
`Model` expression through `pycalphad_ad.evaluate`; its specification marks
database/parameter paths, `calculate`, `equilibrium` and `Workspace` as
deferred. Consequently a user cannot obtain derivatives of the existing
equilibrium outputs (chemical potentials, phase fractions, phase boundaries,
or fitted parameters) while keeping pycalphad's forward solver and active
phase set. This issue requests an implicit/active-set derivative boundary for
the existing workflows, not a new thermodynamic solver.

**Classification:** `upstream_parity_gap`

## Versions and scope

- Upstream software: pycalphad, commit `02c1ce1f16460b695d1a75a3e8d501edb295e7a6`
- AD package: [pycalphad_v3_adms_xj](https://git.gewu-lab.ai/<矩阵实验室组织>/pycalphad_v3_adms_xj), commit `85554b44ce0e0bb821f4e19a63b3c0c4be953386` (v0.1.0)
- Capability review: [pycalphad v0.1.0 private review](../0.1.0-85554b4/TASK_CAPABILITY_REVIEW.md)
- Benchmark ledger: [private pycalphad task ledger](https://git.gewu-lab.ai/flyingwagner/ad-software-private-benchmark/-/blob/main/pycalphad/pycalphad-task-ledger.json)

## Related tasks and papers

The following ledger records all require a derivative through an upstream
equilibrium/property, database-parameter, or constrained-minimization path;
they are consolidated here because they share one implementation contract.

| Task | What it needs | Paper |
|---|---|---|
| [`pycalphad.t028`](https://git.gewu-lab.ai/flyingwagner/ad-software-private-benchmark/-/blob/main/pycalphad/pycalphad-task-ledger.json) | Grand-potential derivative from equilibrium/property query | [Non-equilibrium Thermodynamic Foundation of the Grand-potential Phase Field Model](https://doi.org/10.48550/arxiv.2409.18864) |
| `pycalphad.t029` | Multiphase chemical-potential gradient | [Grand-potential-based phase-field model for multiple phases](https://doi.org/10.1103/PhysRevE.98.023309) |
| `pycalphad.t030` | Gibbs-energy/database parameter derivative | [Coupled microstructural-compositional evolution](https://doi.org/10.1557/opl.2013.165) |
| `pycalphad.t031` | Redlich-Kister parameter sensitivity of a phase diagram | [Optimised equilibrium phase diagram of arsenic-lead alloys](https://doi.org/10.1016/0040-6031(93)80375-k) |
| `pycalphad.t032` | CALPHAD parameter-fitting gradient | [Coupled phase diagram experimental study and thermodynamic optimization](https://doi.org/10.1016/j.jeurceramsoc.2019.12.043) |
| `pycalphad.t033` | Thermodynamic model covariance sensitivity | [CALPHAD modeling of a U-Nd-O miscibility gap](https://doi.org/10.1557/opl.2014.109) |
| `pycalphad.t034` | Phase-boundary uncertainty derivative | [Uncertainty propagation in a CALPHAD-reinforced model](https://doi.org/10.2139/ssrn.3427526) |
| `pycalphad.t035` | Bayesian CALPHAD posterior gradient | [Phase selection rules for high entropy alloys](https://doi.org/10.1016/j.matdes.2021.109532) |
| `pycalphad.t036` | Fisher-information derivative for experiment design | [Maximum information gain and experimental design](https://doi.org/10.1107/S160057672100563X) |
| `pycalphad.t037` | Phase-diagram uncertainty confidence derivative | [Uncertainty propagation in a CALPHAD-reinforced model](https://doi.org/10.1016/j.actamat.2019.11.031) |
| `pycalphad.t038` | Thermodynamic-assessment least-squares Jacobian | [Thermodynamic modeling of Al-Co-Cr-Fe-Ni alloys](https://doi.org/10.1016/j.jallcom.2021.162722) |
| `pycalphad.t039` | Model-fitting gradient for enthalpy data | [Mixing enthalpy of liquid Hf-Ni-Ti alloys](https://doi.org/10.1007/s11669-020-00806-4) |
| `pycalphad.t040` | Activity-data objective derivative | [Sublattice phase-field model for CALPHAD coupling](https://doi.org/10.1016/j.commatsci.2021.110466) |
| `pycalphad.t041` | Phase-equilibria composition Jacobian | [Phase-field simulations of Mg-Nd precipitates](https://doi.org/10.48550/arXiv.2602.18430) |
| `pycalphad.t042` | Electrochemical potential derivative from a phase diagram | [Equilibrium potentials of Ni-Ln alloys](https://doi.org/10.1039/d0nj03736b) |
| `pycalphad.t043` | Voltage/composition derivative | [Unifying chemical and electrochemical thermodynamics](https://doi.org/10.48550/arxiv.2507.10677) |
| `pycalphad.t047` | Gas-equilibrium fugacity derivative | [Thermodynamics of chemical equilibrium](https://doi.org/10.1016/0009-2509(63)85037-X) |
| `pycalphad.t048` | Reaction-affinity derivative at equilibrium | [New chemical affinity with reference to equilibrium](https://doi.org/10.1080/18811248.1994.9735262) |
| `pycalphad.t049` | Gibbs-Duhem phase-equilibrium consistency derivative | [Thermodynamic consistency test for phase-equilibrium data](https://doi.org/10.1016/j.fluid.2004.07.002) |
| `pycalphad.t050` | Tangent-plane-distance/stability derivative | [Stationary points of the Gibbs tangent-plane distance](https://doi.org/10.1016/j.cherd.2017.06.018) |
| `pycalphad.t051` | Metastability-barrier composition derivative | [Enthalpy and entropy effects on phase stability](https://doi.org/10.1016/j.actamat.2013.01.042) |
| `pycalphad.t052` | Spinodal-boundary derivative | [Grain-boundary spinodal decomposition in a high-entropy alloy](https://doi.org/10.1016/j.actamat.2019.07.052) |
| `pycalphad.t053` | Binodal coexistence-composition derivative | [Excess Gibbs energy and liquid-liquid equilibrium](https://doi.org/10.1016/j.fluid.2009.05.019) |
| `pycalphad.t132` | Constrained Gibbs minimization sensitivity | [Local and constrained minima in Gibbs free energy](https://doi.org/10.1002/aic.690250610) |
| `pycalphad.t133` | Chemical-potential equality constraint Jacobian | [Mass variables and chemical potentials](https://doi.org/10.1007/s10910-005-9016-2) |
| `pycalphad.t134` | Implicit derivative of equilibrium phase fractions | [Solidification paths coupled to equilibrium calculations](https://doi.org/10.2355/isijinternational.50.1859) |
| `pycalphad.t135` | Implicit phase-equilibrium parameter-estimation gradient | [Interaction-parameter estimation from phase equilibrium](https://doi.org/10.1021/ie970645g) |

## Evidence of the gap

### Upstream operation

The pinned upstream package exports `pycalphad.calculate`,
`pycalphad.equilibrium` and `pycalphad.Workspace` from
[`pycalphad/__init__.py`](https://github.com/pycalphad/pycalphad/blob/02c1ce1f16460b695d1a75a3e8d501edb295e7a6/pycalphad/__init__.py).
`calculate` evaluates model properties over conditions and constructs phase
records; `equilibrium` solves constrained Gibbs-energy minimization and
returns phase amounts/compositions; `Workspace` caches models and composition
sets across these calls. These are the forward operations used by the linked
task contracts.

### AD boundary

The reviewed [`SPEC.md`](https://git.gewu-lab.ai/<矩阵实验室组织>/pycalphad_v3_adms_xj/-/blob/85554b44ce0e0bb821f4e19a63b3c0c4be953386/pycalphad_ad/SPEC.md)
explicitly defers `calculate`, `equilibrium`, `Workspace`, database/parameter
paths and phase selection. [`pycalphad_ad/api.py`](https://git.gewu-lab.ai/<矩阵实验室组织>/pycalphad_v3_adms_xj/-/blob/85554b44ce0e0bb821f4e19a63b3c0c4be953386/pycalphad_ad/api.py)
and [`rules.py`](https://git.gewu-lab.ai/<矩阵实验室组织>/pycalphad_v3_adms_xj/-/blob/85554b44ce0e0bb821f4e19a63b3c0c4be953386/pycalphad_ad/rules.py)
register JVP/VJP only for a scalar property of a fixed `Model` and a supplied
state mapping. No rule propagates a tangent through the solver residual,
active phase set, composition-set amounts, or database parameters.

## Minimal reproduction

```python
import pycalphad as pc
import pycalphad.variables as v
import pycalphad_ad

dbf = pc.Database("alcrni.tdb")
conditions = {v.T: 1000, v.P: 101325, v.X("CR"): 0.2}
eq = pc.equilibrium(dbf, ["AL", "CR", "NI"], ["LIQUID", "FCC_A1"], conditions)
# Desired: JVP/VJP of a selected phase fraction or chemical potential
# with respect to X(CR), T, P or a model/database parameter.
pycalphad_ad.jvp(pc.equilibrium, dbf, ..., wrt="conditions")
```

Observed result: `equilibrium`/`calculate` has no registered AD rule and the
sidecar accepts neither the database/conditions workflow nor the returned
phase-fraction arrays. Expected result: a derivative of a selected smooth
output for a fixed active phase set, with a documented error when the active
set changes or the solver is non-converged.

## Expected capability

Provide a composable implicit-differentiation adapter for existing
`calculate`/`equilibrium` calls. Users should be able to select continuous
conditions (`T`, `P`, composition variables) and, where explicitly exposed by
the upstream model, continuous thermodynamic parameters, while keeping the
database, component list and phase topology fixed. Return JVP, VJP, `grad`
and `value_and_grad` for selected scalar/vector outputs (chemical potentials,
phase fractions, Gibbs energy, tangent-plane distance or a bounded objective),
using the converged solver residual and its linearized KKT system rather than
finite differences. Phase selection, sorting, bounds and solver failure are
explicit non-differentiable/error boundaries.

## Acceptance criteria

- Primal `calculate`/`equilibrium` outputs match the pinned upstream package on
  a small documented TDB fixture and fixed phase set.
- JVP/VJP agree with an independently assembled residual/KKT or carefully
  checked finite-difference oracle away from active-set transitions; verify
  real-inner-product duality and batched condition shapes.
- Cover composition, temperature and pressure tangents, selected model
  parameters, zero directions, solver failure, phase appearance/disappearance,
  bounds and non-converged states with explicit diagnostics.
- Re-run bounded probes corresponding to at least `t028`, `t032`, `t050` and
  `t134`; existing fixed-Model first-order tests remain passing.

## Non-goals

- No replacement minimizer, new CALPHAD thermodynamic model, database parser,
  phase-topology/mapping algorithm or plotting API.
- No promise of derivatives across phase-selection changes, discontinuous
  active-set transitions, failed solves or unconstrained database text I/O.
- Higher-order derivatives of a fixed `Model` expression are tracked in a
  separate issue.