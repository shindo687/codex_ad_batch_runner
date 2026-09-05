<!-- provenance: GitLab <矩阵实验室组织>/kwant_v3_adms_xj#2, fetched 2026-09-05, state=opened -->

# Scattering and Green-function solver derivatives are missing in kwant-ad

## Summary

Kwant's upstream solvers expose the lead-connected scattering problem
(`kwant.smatrix`, `kwant.greens_function`, `kwant.ldos`, `kwant.wave_function`,
lead `modes`/`selfenergy`) for finalized systems with parameter dictionaries.
The kwant-ad sidecar at the reviewed commit leaves this entire numerical
family `deferred`: no ChainRules JVP/VJP rule exists, so no derivative can pass
through a scattering solve. This blocks every public-benchmark task whose
derivative is taken with respect to energy, bias, gate/tip potential, magnetic
flux, or mechanical coordinates through the scattering or retarded Green
operator — 16 of the 24 public tasks.

**Classification:** `upstream_parity_gap`

## Versions and scope

- Upstream software: Kwant upstream snapshot commit [`ef12fa0d78e25bd8ab5a5e6d7587c6b0d274bea6`](https://gitlab.kwant-project.org/kwant/kwant/-/tree/ef12fa0d78e25bd8ab5a5e6d7587c6b0d274bea6).
- AD package: [`kwant_v3_adms_xj`](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj), reviewed commit [`fd4470d049d01bc0486eaa96f7b76a570ea6915f`](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/commit/fd4470d049d01bc0486eaa96f7b76a570ea6915f).
- Capability review: `package-reviews/kwant/bench/public/0.1.0-fd4470d0/TASK_CAPABILITY_REVIEW.md` (public benchmark `c4e583b`, 24 tasks).

## Related tasks and papers

| Task | What it needs | Paper (doi) |
|---|---|---|
| `kwant.transmission_energy_derivative_thermoelectric` | dT/dE from `kwant.smatrix` over energy | 10.1103/physrevlett.106.120602 |
| `kwant.wigner_smith_time_delay` | dS/dE forming Q = −i S† dS/dE | 10.1103/physrevlett.106.120602 |
| `kwant.finite_bias_differential_conductance` | dI/dV through bias-dependent solves | 10.48550/arXiv.2305.07215 |
| `kwant.nonlinear_conductance_energy_derivatives` | higher energy/bias derivatives of T(E) | 10.48550/arXiv.2305.07215 |
| `kwant.adiabatic_pumping_scattering_derivatives` | ∂S/∂(gate, barrier, flux, SO parameters) | 10.1103/PhysRevB.102.165148 |
| `kwant.current_induced_force_scattering_derivatives` | ∂S/∂(mechanical coordinates) | 10.1103/physrevb.92.201403 |
| `kwant.scanning_gate_resistance_gradient` | ∇_tip dG from repeated solves | 10.1103/PhysRevB.102.165148 |
| `kwant.magnetoconductance_field_sensitivity` | small-field derivative of G through Peierls phases | 10.1103/physrevb.92.201403 |
| `kwant.gate_conductance_derivative_subband_spectroscopy` | dG/dV_gate | 10.48550/arXiv.2305.07215 |
| `kwant.spin_transfer_torque_magnetization_derivative` | ∂S/∂(magnetization direction) | 10.1103/physrevb.92.201403 |
| `kwant.full_counting_statistics_cumulants` | derivatives of transmission eigenvalues/cumulant function | 10.1103/physrevlett.106.120602 |
| `kwant.local_current_bias_response_derivative` | bias derivative of local currents through GF | 10.48550/arXiv.2305.07215 |
| `kwant.partial_density_of_states_injectivity` | energy derivatives of scattering-derived DOS | 10.1103/physrevlett.106.120602 |
| `kwant.quantum_capacitance_scattering_phase` | energy derivative of DOS/scattering phase | 10.1103/PhysRevB.102.165148 |
| `kwant.charge_relaxation_resistance_ac_response` | dS/dE in low-frequency admittance | 10.1103/physrevlett.106.120602 |
| `kwant.differential_shot_noise_bias` | dS/dV noise response | 10.48550/arXiv.2305.07215 |
| `kwant.conductance_scaling_beta_function` | β = d⟨ln g⟩/d ln L statistics loop | 10.1103/PhysRevB.102.165148 |

(Exact paper anchors are preserved in the bench ledger, `kwant/kwant-task-ledger.json` @ `c4e583b`.)

## Evidence of the gap

### Upstream operation

`kwant.solvers.default.smatrix` evaluates the scattering matrix of a finalized
lead-connected system (`upstream/src/kwant/solvers/default.py`, host
snapshot `ef12fa0`), and `greens_function`, `ldos`, `wave_function`,
`modes`, and `selfenergy` provide the same parameter-keyed forward surface.
All accept `params={...}` for onsite/hopping/bias-type parameters.

### AD boundary

`kwant_ad/api_inventory.json` marks all solver/scattering symbols `deferred`
("needs an implicit/state adjoint contract not exposed by this snapshot");
`kwant_ad/SUPPORT.md` documents "Scattering/Green-function solvers — Deferred;
no silent fallback". No JVP/VJP rule under these names appears in
`kwant_ad/_rules.py`, and the package freezes the upstream snapshot `ef12fa0`.

### Minimal reproduction

```python
import kwant
import kwant_ad  # registers fermi/jackson/lorentz/Bands rules
from kwant_ad import jvp
from kwant.solvers.default import smatrix

lat = kwant.lattice.square(a=1)
syst = kwant.Builder()
syst[(lat(i, j) for i in range(8) for j in range(4))] = 4
syst[lat.neighbors()] = -1
lead = kwant.Builder(kwant.TranslationalSymmetry((-1, 0)))
lead[(lat(0, j) for j in range(4))] = 4
lead[lat.neighbors()] = -1
syst.attach_lead(lead)
syst.attach_lead(lead.reversed())
fsys = syst.finalized()

def G(V):
    s = smatrix(fsys, energy=0.2, params={"on": V})
    return s.transmission(1, 0)

jvp(G, 1.0, tangents={"V": 1.0})  # expected: transmission sensitivity
```

Observed: `RuleNotFound` — no JVP rule is registered for any scattering solve
(probe at commit `fd4470d0`). Expected: a first-order linear map for the
parameter derivative of scattering quantities, or an explicit
state-adjoint/self-energy-differentiated path.

## Expected capability

A JVP/VJP rule (or a set of rules) for the scattering/Green-function family
with active inputs `params` (and, where applicable, `energy`), returning
tangents of transmission/probability/current observables formed from S; with
documented non-smooth boundaries (mode threshold crossings, channel
activation, lead non-Hermiticity) raising `NonDifferentiablePoint` instead of
silent values.

## Acceptance criteria

- `kwant_ad` registers rules for `smatrix`/`greens_function`-derived
  transmission so the reproduction above returns a tangent within the
  package's FD tolerance (`1e-6`…`1e-5`) versus central differences on a
  single-channel probe.
- A higher-level check passes for the Wigner-Smith Q = −i S† dS/dE workflow on
  a two-terminal system.
- Non-smooth/multi-mode crossing → explicit `NonDifferentiablePoint`, and
  existing 18 tests remain passing.
- Existing rule families (Bands, KPM kernels) are unchanged.

## Non-goals

- No new solver families (no Tkwant time propagation, no MUMPS symmetry
  break, no open-system additions).
- No high-order scattering Dirichlet-to-Neumann research; this issue covers
  the first-order parameter derivative over the existing upstream surface.
- Berry/QGT eigenvector derivatives; that is a separate gap tracked in the
  eigenvector-derivative issue.
- No finite-difference fallback inside kwant-ad (kept analytic per SPEC).