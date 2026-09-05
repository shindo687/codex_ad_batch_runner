<!-- provenance: GitLab <矩阵实验室组织>/kwant_v3_adms_xj issues #2-#5 (one combined task), fetched 2026-09-05, state=opened -->
<!-- combined: the four parity-gap issues below must be fixed together, in ONE repository and ONE chain of commits -->

# Combined task: close all four open AD parity gaps in kwant_v3_adms_xj

Base to review: kwant_v3_adms_xj @ fd4470d049d01bc0486eaa96f7b76a570ea6915f

This single issue bundles the four open parity-gap issues for this package.
Implement all four in the one working branch, with tests for each; the four
sections below are the original issue texts verbatim (issue order preserved).

SECTION 1 OF 4 -- original issue #2

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

SECTION 2 OF 4 -- original issue #3

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

SECTION 3 OF 4 -- original issue #4

<!-- generated from issues/operators.md; edit the source draft and regenerate -->
<!-- classification: upstream_parity_gap; submit_enabled: true -->
# [Astra] Expose complex-state JVP/VJP for native Density and Current operators

> **本 issue 由 Astra 评审并提出。Reviewed and submitted by Astra at the user's request.**

**Classification:** `upstream_parity_gap`

## Review context and provenance

- AD package: [kwant-ad 0.1.0, commit fd4470d049d01bc0486eaa96f7b76a570ea6915f](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/tree/fd4470d049d01bc0486eaa96f7b76a570ea6915f).
- Upstream: Kwant source commit `ef12fa0d78e25bd8ab5a5e6d7587c6b0d274bea6`, as recorded in [requirements.md](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/kwant_ad/requirements.md); the probes used the package's unmodified [bundled source](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/upstream/README.rst).
- Environment: Python 3.12.14, NumPy 2.5.2, SciPy 1.18.1, tinyarray 1.2.5, ChainRules 0.1.0; SciPy transport backend, MUMPS unavailable.
- Kwant was built from that exact bundled snapshot. Its build label `0.0.0+ef12fa0` is not a published release claim. Build dependencies, including SciPy, were supplied explicitly and the build used `--no-build-isolation`.
- Baseline sidecar suite: **18 passed, 1 warning in 12.00s**, exit 0. The warning is the unavailable optional MUMPS backend.
- **Scope:** package-level capability review requested for immediate issue submission. A public/private benchmark was not selected, so no benchmark coverage score, benchmark task IDs, or full-paper reproduction is claimed. This is a documented deferred capability, not a claim that a currently implemented rule regressed.
- This issue contains its bounded review evidence below. [Review context](#review-context-and-provenance) · [Astra issue index](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/issues?scope=all&state=all&search=Astra).

## Summary

Kwant already evaluates local Density and Current as smooth bilinear/quadratic functions of supplied wavefunctions on a finalized, fixed system. The sidecar has no derivative registration or usable Python-signature adapter for this existing operation. A two-site fixture gives nonzero state derivatives, while the public JVP fails during signature inspection and the native call has no VJP registration. This gap can be closed independently of differentiating how a wavefunction was produced.

## Evidence of the gap

### Upstream operation

[Density](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/upstream/src/kwant/operator.pyx#L723) and [Current](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/upstream/src/kwant/operator.pyx#L871) implement native local expectation values. The fixture supplies wavefunctions directly and runs both operators successfully.

### AD-package boundary

[SPEC.md](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/kwant_ad/SPEC.md) defers local-operator classes. [register_rules](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/kwant_ad/_rules.py#L329) contains no local-operator registration. With the installed ChainRules backend, `kwant_ad.jvp(op, psi, tangents={"bra": direction})` raises a signature-inspection TypeError before a rule can run; `rules.get_vjp(type(op).__call__)` independently confirms that a VJP is missing.

### Minimal bounded reproduction

Run with the reviewed package and its pinned upstream installed:

```python
import numpy as np
import kwant
import kwant_ad as ad

lat = kwant.lattice.chain(norbs=1)
syst = kwant.Builder()
syst[lat(0)] = 0.0
syst[lat(1)] = 0.2
syst[lat(0), lat(1)] = -1.0
syst = syst.finalized()
psi = np.array([1 + 0.2j, 0.3 - 0.4j])
direction = np.array([0.1 - 0.2j, -0.3 + 0.1j])
step = 1e-6
for cls in (kwant.operator.Density, kwant.operator.Current):
    op = cls(syst)
    print(cls.__name__, "forward", op(psi))
    print(cls.__name__, "FD oracle", (op(psi + step * direction) - op(psi - step * direction)) / (2 * step))
    try:
        ad.jvp(op, psi, tangents={"bra": direction})
    except Exception as error:
        print(cls.__name__, "public JVP", type(error).__name__, str(error))
    else:
        raise AssertionError("Expected missing derivative path has changed; re-review")
    try:
        ad.rules.get_vjp(cls.__call__)
    except Exception as error:
        print(cls.__name__, "VJP registration", type(error).__name__, str(error))
    else:
        raise AssertionError("Expected missing registration has changed; re-review")
```

### Observed output

This probe exits 0 because it catches and reports the expected missing-capability errors; exit 0 does **not** mean the derivative exists.

```text
Density forward [1.04 0.25]
Density FD oracle [ 0.12 -0.26]
Density public JVP TypeError Cannot inspect the signature of <kwant.operator.Density object at <address>>; register a thin Python wrapper with an explicit signature
Density VJP registration RuleNotFound No VJP rule is registered for _LocalOperator.__call__
Current forward [ 0.92 -0.92]
Current FD oracle [-0.36  0.36]
Current public JVP TypeError Cannot inspect the signature of <kwant.operator.Current object at <address>>; register a thin Python wrapper with an explicit signature
Current VJP registration RuleNotFound No VJP rule is registered for _LocalOperator.__call__
```

## Expected capability

Provide an explicit-signature adapter or registration for native Density/Current evaluation with fixed system, operator coefficients and site/hopping selection. Support complex state JVP/VJP for the expectation-value path and clearly distinguish independent bra/ket inputs from ket=None, where the same state enters both factors. Define derivatives over complex arrays using Re(vdot(cotangent, tangent)); obtain the primal from the native Kwant operator.

## Acceptance criteria

- For psi=[1+0.2j, 0.3-0.4j] and dpsi=[0.1-0.2j, -0.3+0.1j], the displayed Density derivative is [0.12, -0.26] and Current derivative is [-0.36, 0.36]. Check against analytic quadratic forms and independent central differences.
- Check independent bra and ket directions as well as the tied expectation path; the latter must include both contributions.
- Verify JVP/VJP duality for random real and imaginary state perturbations, sum=False vector outputs, sum=True scalar outputs and fixed where selections.
- Provide a reusable pullback and explicit shape/dtype/unsupported-activity errors; preserve native ordering and normalization semantics.
- No production finite differences, no eigenstate/scattering differentiation prerequisite, and all existing package tests remain passing.

## Non-goals

- Differentiating the solver that generated psi, changing lattice topology or where selections.
- New physical observables, Berry/QGT helpers, or automatic differentiation of arbitrary operator callbacks.
- Simultaneous support for all Hamiltonian/operator-parameter derivatives; those can have a separate explicit contract.

SECTION 4 OF 4 -- original issue #5

<!-- generated from issues/kpm.md; edit the source draft and regenerate -->
<!-- classification: upstream_parity_gap; submit_enabled: true -->
# [Astra] Differentiate fixed-moment KPM spectral density with respect to the Hamiltonian

> **本 issue 由 Astra 评审并提出。Reviewed and submitted by Astra at the user's request.**

**Classification:** `upstream_parity_gap`

## Review context and provenance

- AD package: [kwant-ad 0.1.0, commit fd4470d049d01bc0486eaa96f7b76a570ea6915f](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/tree/fd4470d049d01bc0486eaa96f7b76a570ea6915f).
- Upstream: Kwant source commit `ef12fa0d78e25bd8ab5a5e6d7587c6b0d274bea6`, as recorded in [requirements.md](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/kwant_ad/requirements.md); the probes used the package's unmodified [bundled source](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/upstream/README.rst).
- Environment: Python 3.12.14, NumPy 2.5.2, SciPy 1.18.1, tinyarray 1.2.5, ChainRules 0.1.0; SciPy transport backend, MUMPS unavailable.
- Kwant was built from that exact bundled snapshot. Its build label `0.0.0+ef12fa0` is not a published release claim. Build dependencies, including SciPy, were supplied explicitly and the build used `--no-build-isolation`.
- Baseline sidecar suite: **18 passed, 1 warning in 12.00s**, exit 0. The warning is the unavailable optional MUMPS backend.
- **Scope:** package-level capability review requested for immediate issue submission. A public/private benchmark was not selected, so no benchmark coverage score, benchmark task IDs, or full-paper reproduction is claimed. This is a documented deferred capability, not a claim that a currently implemented rule regressed.
- This issue contains its bounded review evidence below. [Review context](#review-context-and-provenance) · [Astra issue index](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/issues?scope=all&state=all&search=Astra).

## Summary

The sidecar differentiates jackson_kernel, lorentz_kernel and fermi_distribution, but it cannot propagate Hamiltonian perturbations through the existing KPM moment recurrence and spectral reconstruction. The native SpectralDensity path is smooth in a small fixed-matrix fixture with explicit spectral bounds and deterministic vectors; its density has a nonzero convergent Hamiltonian derivative, while the corresponding AD constructor path raises RuleNotFound.

## Evidence of the gap

### Upstream operation

[SpectralDensity](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/upstream/src/kwant/kpm.py#L39) accepts matrix Hamiltonians, explicit `bounds`, `num_moments`, and `vector_factory`; its call evaluates the reconstructed spectral density. The fixture fixes all these choices.

### AD-package boundary

[SPEC.md](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/kwant_ad/SPEC.md) explicitly defers SpectralDensity/Correlator/conductivity. [_register_kpm](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/kwant_ad/_rules.py#L66) supplies only elementwise kernel/occupation rules; [register_rules](https://git.gewu-lab.ai/<矩阵实验室组织>/kwant_v3_adms_xj/-/blob/fd4470d049d01bc0486eaa96f7b76a570ea6915f/kwant_ad/_rules.py#L329) does not compose Hamiltonian derivatives through SpectralDensity.

### Minimal bounded reproduction

Run with the reviewed package and its pinned upstream installed:

```python
import numpy as np
import kwant
import kwant_ad as ad

hamiltonian = np.array([[0.2, -1.0, 0.0], [-1.0, 0.3, -0.7], [0.0, -0.7, -0.1]])
direction = np.diag([1.0, 0.0, 0.0])
settings = dict(num_moments=20, num_vectors=3,
                vector_factory=list(np.eye(3)), bounds=(-3.0, 3.0), rng=0)
def rho(matrix):
    return kwant.kpm.SpectralDensity(matrix, **settings)(0.4)
print("upstream density", rho(hamiltonian))
for step in (1e-4, 1e-5, 1e-6):
    print("FD oracle step", step, "d_density",
          (rho(hamiltonian + step * direction) - rho(hamiltonian - step * direction)) / (2 * step))
try:
    ad.jvp(kwant.kpm.SpectralDensity, hamiltonian,
           tangents={"hamiltonian": direction}, **settings)
except Exception as error:
    print("public JVP", type(error).__name__, str(error))
else:
    raise AssertionError("Expected missing derivative path has changed; re-review")
```

### Observed output

This probe exits 0 because it catches and reports the expected missing-capability errors; exit 0 does **not** mean the derivative exists.

```text
upstream density 0.2169340655962436
FD oracle step 0.0001 d_density 0.09562285755618238
FD oracle step 1e-05 d_density 0.09562285786940404
FD oracle step 1e-06 d_density 0.09562285789577185
public JVP RuleNotFound No JVP rule is registered for SpectralDensity
```

## Expected capability

Expose a documented JVP/VJP adapter for the existing fixed-moment SpectralDensity → evaluation path with respect to a fixed-shape Hermitian matrix Hamiltonian. Keep expansion order, reconstruction energies, spectral bounds and supplied trace vectors fixed. A wrapper around the native object is sufficient; differentiating Python object construction itself is not required. Preserve the native reconstruction and normalization and document reverse-mode storage/recomputation.

## Acceptance criteria

- For the three-by-three Hamiltonian below, density(0.4)=0.2169340655962436 and its directional Hamiltonian derivative is approximately 0.0956228579. Match an independent shrinking-step oracle.
- Use deterministic trace vectors, fixed bounds and a fixed moment count in tests so randomness or eigensolver-bound changes do not contaminate derivatives.
- Verify JVP/VJP duality for Hermitian matrix directions, including imaginary off-diagonal components, and a scalar loss formed from a fixed grid of spectral densities.
- Retain primal parity with native SpectralDensity and explicitly reject unsupported changes to order, bounds, topology and sampling rules.
- Do not substitute finite-difference derivatives at runtime. Existing elementwise kernel and Bands tests must remain passing.

## Non-goals

- A new physical Kubo observable or a new solver family.
- Differentiating adaptive spectral-bound estimation, stochastic sampling, changing expansion order or automatic topology changes.
- Immediate coverage of all Correlator/conductivity/operator callbacks or claims of full-paper reproduction.
