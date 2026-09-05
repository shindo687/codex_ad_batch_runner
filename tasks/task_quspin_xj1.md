<!-- provenance: GitLab <矩阵实验室组织>/quspin_v3_adms_xj issue #1 by <作者>, fetched 2026-09-05, state=opened -->
<!-- ======== ISSUE 1/1 · quspin_v3_adms_xj#1 · Differentiate dynamic QuSpin drive parameters through fixed-grid trajectories ======== -->

<!-- generated from <内部草稿文档>; edit the source draft and regenerate -->
<!-- classification: upstream_parity_gap; submit_enabled: true -->
# Differentiate dynamic QuSpin drive parameters through fixed-grid trajectories

## Summary

QuSpin 1.0.1 exposes dynamic Hamiltonian callbacks and `hamiltonian.evolve`,
but the reviewed `quspin-ad` v0.1.0 sidecar only differentiates a few
post-evolution array primitives. It does not compose derivatives of callback
or schedule coefficients through a fixed-grid trajectory to a final or
time-integrated objective. This is an upstream-parity gap over an existing
QuSpin forward path and blocks finite-time control, dynamical Hamiltonian
learning, and quench-response gradients.

**Classification:** `upstream_parity_gap`

## Versions and scope

- Upstream software: QuSpin 1.0.1; sidecar upstream snapshot commit [`5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f`](https://github.com/QuSpin/QuSpin/tree/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f).
- AD package: [`quspin_v3_adms_xj`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj), reviewed commit [`3fd649035b1d46d7657be011b3266a8520ef8103`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj/-/tree/3fd649035b1d46d7657be011b3266a8520ef8103).
- Private benchmark ledger: [`quspin-task-ledger.json`](<内部基准台账URL已脱敏>).
- Capability review: [`TASK_CAPABILITY_REVIEW.md`](TASK_CAPABILITY_REVIEW.md).

## Related tasks and papers

| Task | What it needs | Paper |
|---|---|---|
| `quspin.finite_time_state_transfer_gradient` | Gradient of final-state fidelity through discretized dynamic controls | [10.48550/arXiv.2008.06076](https://doi.org/10.48550/arXiv.2008.06076) |
| `quspin.hamiltonian_learning_dynamics` | Prediction-loss gradient through time evolution with respect to Hamiltonian/control parameters | [10.1021/acs.jpca.2c08993](https://doi.org/10.1021/acs.jpca.2c08993) |
| `quspin.quantized_charge_pump_current` | Derivative of a driven finite-lattice current over a pump cycle | [10.1103/PhysRevB.96.035139](https://doi.org/10.1103/PhysRevB.96.035139) |
| `quspin.loschmidt_decay_rate_derivative` | Quench-trajectory and fitted decay-rate sensitivity | [10.48550/arXiv.quant-ph/0609202](https://doi.org/10.48550/arXiv.quant-ph/0609202) |
| `quspin.quench_observable_initial_parameter_susceptibility` | Initial-parameter derivative of a time-averaged quench observable | [10.1103/PhysRevB.80.054404](https://doi.org/10.1103/PhysRevB.80.054404) |

## Evidence of the gap

### Upstream operation

The pinned QuSpin source provides dynamic callback terms and
`hamiltonian.evolve`; its right-hand side evaluates each callback at the
current time and accepts finite time grids. The same source also exposes the
general `quspin.tools.evolution.evolve` entry point for callback parameters.

- [QuSpin `hamiltonian.evolve` source](https://github.com/QuSpin/QuSpin/blob/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f/src/quspin/operators/hamiltonian_core.py)
- [QuSpin evolution helpers](https://github.com/QuSpin/QuSpin/blob/5bf9e5b266e6d8b70e5cf5973c7c7d59d62e412f/src/quspin/tools/evolution.py)

### AD-package boundary

The v3 sidecar's [`api_inventory.json`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj/-/blob/3fd649035b1d46d7657be011b3266a8520ef8103/quspin_ad/api_inventory.json)
marks `hamiltonian`, `evolve`, and dynamic solver objects deferred. Its
[`rules.py`](<内部GitLab>/<矩阵实验室组织>/quspin_v3_adms_xj/-/blob/3fd649035b1d46d7657be011b3266a8520ef8103/quspin_ad/rules.py)
only registers first-order rules for `ED_state_vs_time`, `KL_div`,
`commutator`, `anti_commutator`, `lin_comb_Q_T`, and dense `project_op`.
There is no tangent slot for a dynamic callback coefficient or trajectory loss.

## Minimal reproduction

```python
import numpy as np
from quspin.basis import spin_basis_1d
from quspin.operators import hamiltonian

basis = spin_basis_1d(L=2)
def drive(t, amplitude):
    return amplitude * np.sin(t)

H = hamiltonian([], [["z", [[1.0, 0]], drive, (0.7,)]], basis=basis,
                dtype=np.complex128)
psi0 = np.zeros(basis.Ns, dtype=np.complex128); psi0[0] = 1
times = np.linspace(0.0, 1.0, 9)
trajectory = H.evolve(psi0, 0.0, times, eom="SE")  # upstream forward path

# Desired v3 API shape (currently unavailable):
# value, tangent = quspin_ad.jvp(H.evolve, ..., tangents={"amplitude": 1.0})
```

The forward trajectory is available from QuSpin, but the reviewed sidecar has
no composable derivative with respect to `amplitude`; replacing it with a
finite-difference sweep is not an AD implementation.

## Expected capability

Add a bounded fixed-grid dynamic-trajectory rule that accepts differentiable
drive coefficients (and the initial state), returns JVP/VJP for final-state or
time-integrated scalar objectives, preserves QuSpin state shapes and complex
real-linear cotangent conventions, and provides checkpointed reverse mode for
long grids. Missing derivative metadata, adaptive solvers, discontinuous
callbacks, and topology changes must fail explicitly.

## Acceptance criteria

- A two-level sinusoidal drive passes independent central-FD JVP/VJP and
  JVP/VJP duality checks for every drive coefficient.
- A small state-transfer or quench fixture matches `hamiltonian.evolve` on the
  same fixed grid and returns a final-fidelity/observable gradient.
- Callback coefficients with no derivative contract fail clearly; no runtime
  finite-difference fallback is introduced.
- Static existing sidecar tests remain passing and memory behavior is
  documented for checkpointed reverse mode.

## Non-goals

- Floquet eigensystem derivatives (separate issue below).
- Berry/QGT, thermal, Kubo/work-statistics, open-system, or non-Hermitian
  scientific layers.
- Adaptive ODE differentiation or topology-changing basis construction.