<!-- provenance: GitLab <矩阵实验室组织>/kwant_v3_adms_xj#5, fetched 2026-09-05, state=opened -->

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