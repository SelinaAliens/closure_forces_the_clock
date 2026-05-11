# Results — read me before citing

JSON output of every simulation cited in Papers 35 and 36. For the
script → paper → result mapping, see the top-level `README.md`.

Paper 34's simulation outputs (the 28-qubit double-triangle Stage A/B/C
sweeps, and the 8q Aer precursor) are not in this folder — they live with
the [Paper 34 Zenodo deposit](https://doi.org/10.5281/zenodo.19855595).

## Quick contents

| File | Paper | Notes |
|---|---|---|
| `obs25a_binary_clock.json` | 35 | Mode A/B baseline |
| `obs25b_closure_modes.json` | 35 | **Main closure-trichotomy result** |
| `obs25b_rgf_filtered.json` | 35 | **Expected-fail diagnostic — see note** |
| `obs25b_riemann_long.json` | 35 | 960-sample extended sweep |
| `obs25c_chirality_cascade.json` | 36 | **5-rung cascade** |

---

## ⚠ Note on `obs25b_rgf_filtered.json` — read before citing

This file is a **diagnostic that the framework predicts to fail at the
cutoffs tested**. All nine cutoffs (3.5 → 20.0) return `verdict = "fail"`.
That is the expected outcome, not a refutation:

1. The Wigner-GUE signature lives in the **actual Riemann zeros** (Paper 7,
   Analysis 40, p = 0.993), not in this 6-qubit proxy. The proxy uses a
   log-prime drive on a binary triangle; it is a forecast circuit, not a
   re-derivation of the Montgomery pair-correlation result.
2. Paper 35 §8.3 carries this as an open question and does **not** cite
   this JSON as evidence for GUE statistics. The `p = 0.993` quoted in
   Paper 35 traces to Paper 7.
3. The framework expects the 6-qubit proxy to enter the Riemann regime
   only after the Z₆₂ stratum is fully resolved (cf. Paper 35 §8.3 and
   Paper 36 §6 Conjecture 1). `verdict = "fail"` at these cutoffs is
   consistent with the framework's own prediction.

If you cite or re-run this file, retain this context: the fails here are
*predicted* characteristics of the proxy circuit, not a falsification of
the Riemann-regime claim.

---

## Note on δ_rate precision (`obs25b_closure_modes.json` ↔ Paper 36 §3.1)

Paper 36 §3.1 writes:

> δ_rate = (0.8066 − 0.7420)/(0.8066 + 0.7420) = 0.04171

The purities 0.8066 and 0.7420 are 4-significant-figure roundings of the
exact values in `obs25b_closure_modes.json`:

- `matter.divisor_60_purity` = 0.8065579742484663
- `antimatter.divisor_60_purity` = 0.7419979625547106

Computing δ_rate from the exact values gives **0.041683**, not 0.04171.
Both forms agree with Δ(YM) = 1/24 = 0.041̅6 to four significant figures;
the 3 × 10⁻⁵ shift between them is rounding of the displayed purities,
not of the underlying simulation. Paper 36 v9 carries an inline footnote
to this effect after the computation in §3.1.
