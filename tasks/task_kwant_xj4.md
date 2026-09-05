<!-- provenance: GitLab <矩阵实验室组织>/kwant_v3_adms_xj#4, fetched 2026-09-05, state=opened -->

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