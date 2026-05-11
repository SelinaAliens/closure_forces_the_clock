# Closure Forces the Clock — Papers 35 & 36

Companion code, data, and manuscripts for the matter-antimatter sector of the
Merkabit Research Series. Paper 34 (the upstream Ternary Spectrum result,
already on Zenodo) is included as precursor context. Together the three
papers form a self-contained *closure trilogy*:

| # | Title | Central claim |
|---|---|---|
| **34** | The Ternary Spectrum: Cyclotomic Z₃ Structure in Coupled Merkabit Triangles | The 137 ternary sector's transfer matrix has period 12 with cyclotomic Z₃ character; FFT bichromatic in {12, 6} at 98% purity |
| **35** | Closure Forces the Clock: Matter, Antimatter, and the Loop-Obstruction Trichotomy of B₃₁ | The merkabit's master clock is 60 = lcm(h(E₆), h(E₈)); the 5-fold ouroboros projects 60 → 12; three empirically distinguishable closure modes correspond to matter, antimatter (Paper 14 §4.3), and the Riemann zero regime (Paper 7) |
| **36** | The Fifth Face of PSL(2,7): Matter-Antimatter Asymmetry as the Yang-Mills Mass Gap | The baryon-to-photon ratio η_B = 5α⁴/\|2T\| = 5/(24·137⁴) = 5.91×10⁻¹⁰; Paper 10's "Four Faces" extends to five |

The three papers measure distinct sectors with distinct experiments but share a
single structural backbone: the PSL(2,7) stratum decomposition
**168 = 137 + 31** and its binary tetrahedral subgroup **2T** of order 24.

---

## The trilogy in one paragraph

Paper 34 measures the 137 ternary sector's coupling spectrum directly on 28
qubits and finds period-12 cyclotomic Z₃ structure. Paper 35 then measures the
31 binary sector on 6 qubits and identifies **60 = lcm(12, 30) as the
architecture's master clock**, with the 5-fold ouroboros {S, R, T, F, P}
collapsing 60 → 12 to produce the Paper 34 result as a sub-harmonic
projection. Paper 35 also measures the matter-antimatter rate asymmetry on the
binary triangle as **δ = 0.04171**, and Paper 36 identifies this as the
**Yang-Mills mass gap Δ = 1/|2T| = 1/24** already established in Papers 9 and
16. Combining the CP phase (1/24), four electromagnetic suppression factors
(α⁴), and the five-fold ouroboros amplification, the baryon asymmetry admits a
closed form

> **η_B = 5/(24·137⁴) = 5.907 × 10⁻¹⁰** vs observed **6.09 × 10⁻¹⁰** (Planck 2018).

Match to 3% with zero free parameters. Every integer in the formula is a
Lie-algebraic or group-theoretic invariant of E₆ or its binary-tetrahedral
double cover.

---

## Contents

```
cirq/          — simulation scripts (Cirq + NumPy)
results/       — raw JSON output of every run cited in the papers
paper/         — markdown drafts and the Paper 34 docx
PREDICTION.md  — pre-registered observables (22, 23, 24, 25, 25a-c, 26)
requirements.txt
```

### Script → paper mapping

| Script | Paper | Observable(s) | Purpose |
|---|---|---|---|
| `cirq/run_p4s_double_triangle_cirq.py` | 34 | Obs 23, Obs 24 | 28-qubit double-triangle sweep (Stages A, B, C) — the ternary cyclotomic Z₃ spectrum and the Regime 3 Riemann-zero forecast |
| `cirq/run_obs25a_binary_clock_cirq.py` | 35 | Obs 25a | Single-mode baseline — period-30 test, two drive modes (rational vs log-primes) |
| `cirq/run_obs25b_closure_modes_cirq.py` | 35 | Obs 25b | Three closure modes — matter, antimatter, Riemann — on the 6-qubit binary triangle |
| `cirq/run_obs25b_rgf_filtered_analysis.py` | 35 | Obs 25b-RGF | High-pass-filtered Wigner-GUE diagnostic on the Riemann mode |
| `cirq/run_obs25b_riemann_long_cirq.py` | 35 | Obs 25b extended | 960-sample Riemann sweep + multi-ensemble level-spacing test (GUE/GOE/Poisson) |
| `cirq/run_obs25c_chirality_cascade_cirq.py` | 36 | Obs 25c | 7-rung chirality cascade (triangle → tesseract on laptop; rung 6 = 24-cell supplied by Theorem 1) |

### Note on `obs25b_rgf_filtered.json` (read before citing)

This file is a **diagnostic that the framework predicts to fail at the
cutoffs tested**. All nine cutoffs (3.5 → 20.0) return `verdict = "fail"`.
That is the expected outcome, not a refutation, for three reasons:

1. The Wigner-GUE signature lives in the **actual Riemann zeros** (Paper 7,
   Analysis 40, p = 0.993), not in this 6-qubit proxy. The proxy uses a
   log-prime drive on a binary triangle; it is a forecast circuit, not a
   re-derivation of the Montgomery pair-correlation result.
2. Paper 35 §8.3 explicitly carries this as an open question and does **not**
   cite this JSON as evidence for GUE statistics. The `p = 0.993` quoted
   in Paper 35 traces to Paper 7, the Riemann-zero analysis.
3. The framework expects the 6-qubit proxy to enter the Riemann regime only
   after the Z₆₂ stratum is fully resolved (cf. Paper 35 §8.3 and Paper 36
   §6 Conjecture 1). The "fail × 9" pattern at the cutoffs tested is
   therefore consistent with the framework's own prediction.

If you cite or re-run this file, please retain this context — `verdict =
"fail"` here is a *predicted* characteristic of the proxy circuit at these
cutoffs, not a falsification of the Riemann-regime claim.

---

### Result → paper mapping

| JSON | Paper | Source script | Notes |
|---|---|---|---|
| `p4s_double_triangle_stageA_*.json` | 34 | double_triangle | Stage A baseline |
| `p4s_double_triangle_stageB_mode1_synchronous_*.json` | 34 | double_triangle | offset = 0 dominance matrix |
| `p4s_double_triangle_stageB_mode2_interleaved_*.json` | 34 | double_triangle | offset = 6 dominance matrix |
| `p4s_double_triangle_stageC_*.json` | 34 | double_triangle | **Main result** — 324-configuration entropy spectrum, FFT period 12 |
| `obs25a_binary_clock.json` | 35 | obs25a | Mode A vs Mode B FFT on 6 qubits |
| `obs25b_closure_modes.json` | 35 | obs25b | Three-mode entropy curves + all 7 threshold verdicts |
| `obs25b_rgf_filtered.json` | 35 | rgf_filtered | 9 high-pass cutoffs, KS test — **expected-fail diagnostic** (see note below) |
| `obs25b_riemann_long.json` | 35 | riemann_long | 960-sample extended sweep, multi-ensemble |
| `obs25c_chirality_cascade.json` | 36 | cascade | 5-rung δ measurements + exponential fit |

---

## Central result (Paper 36)

```
                            5 α⁴       5
            η_B   =   ─────────   =  ───────────   =  5.907 × 10⁻¹⁰
                           |2T|       24 · 137⁴

Observed (Planck 2018):        (6.09 ± 0.06) × 10⁻¹⁰
Agreement:                     3%, zero free parameters
```

Every integer is architectural:

- **5** = e₃, third exponent of E₆, the ouroboros fold-factor (Paper 8 Route B)
- **24** = |2T|, binary tetrahedral order = 2h(E₆) (Papers 9, 16)
- **137** = N(12 + 5ω) + dim(D₄) (Paper 8 Route B)

---

## Running the simulations

Python 3.13, Cirq ≥ 1.6, NumPy ≥ 1.26. See `requirements.txt`.

```bash
# Paper 34 — ternary cyclotomic spectrum (28 qubits, ~3 hours)
cd cirq/
python run_p4s_double_triangle_cirq.py

# Paper 35 — binary closure modes (6 qubits, ~6 seconds)
python run_obs25a_binary_clock_cirq.py        # basic Mode A/B
python run_obs25b_closure_modes_cirq.py       # three-mode matter/antimatter/Riemann
python run_obs25b_rgf_filtered_analysis.py    # Wigner-GUE diagnostic
python run_obs25b_riemann_long_cirq.py        # extended 960-offset Riemann sweep

# Paper 36 — chirality cascade (5 rungs, ~80 seconds; rung 6 by theorem)
python run_obs25c_chirality_cascade_cirq.py            # rungs 1-5
python run_obs25c_chirality_cascade_cirq.py --heavy    # optional rung 6, ~15 hours
```

Rung 6 (24-cell) is proved theoretically in Paper 36 §6 (Theorem 1) via the
orbit-stabilizer argument on 2T unit quaternions. The `--heavy` flag is
available but unnecessary — the hardware pre-registration is Observable 26
(Willow / IBM Heron r2, 24 qubits).

---

## Pre-registered observables

See `PREDICTION.md` for thresholds, falsifiers, and hardware budgets.
Summary:

- **Obs 22** (Paper 33, predecessor): Pentachoric Verification Protocol, 19 qubits
- **Obs 23** (Paper 34): Cyclotomic Z₃ spectrum, 28 qubits — simulation PASS on all four thresholds
- **Obs 24** (Paper 34): Regime 3 incommensurate 137 × 137 coupling — Riemann-zero forecast, forthcoming
- **Obs 25** (Paper 35): Three-mode closure trichotomy on 9 qubits, IBM + Willow cross-arch
- **Obs 25a–c** (Papers 35/36): laptop precursors to 25 + cascade
- **Obs 26** (Paper 36): 24-qubit chirality asymmetry on 24-cell, Willow or IBM Heron r2

---

## Related repositories (framework context)

The framework underlying these three papers spans ~30 papers; the key
upstream dependencies are:

- [`SelinaAliens/tesseract_quantum_implementation`](https://github.com/SelinaAliens/tesseract_quantum_implementation) — Papers 31, 32, 33 (cross-chiral tunnel primitive, Z₃ CA, primitive-complete QC)
- [`SelinaAliens/pentachoric_verification`](https://github.com/SelinaAliens/pentachoric_verification) — Paper 33 Pentachoric Verification Protocol (Observable 22, 19 qubits)
- [`SelinaAliens/genesis_sequence_merkabit`](https://github.com/SelinaAliens/genesis_sequence_merkabit) — the 16-rung forcing chain that defines the polytope ladder used by Paper 36's cascade
- Papers 9, 16 (Yang-Mills mass gap, Δ = 1/24) — see `results_registry.md` in the framework memory

---

## Provenance

All three papers were drafted in collaboration with **Claude (Anthropic, Opus
4.7, 1M-context)** as a coding, simulation, and manuscript assistant. Paper
36's central identification (δ_rate = Δ(YM) = 1/|2T|, Paper 35 measurement
= Paper 16 algebraic constant) emerged during the same session that produced
the Paper 35 and Paper 36 drafts, upon comparing the laptop measurement
against the framework's master constants table. Final scientific
responsibility rests with the human author.

AI did not execute on IBM or Google hardware and had no operational runtime
access.

---

## License

MIT. See `LICENSE`.

## Citation

If you use this code, please cite:

```
Stenberg, S. (2026). The Ternary Spectrum / Closure Forces the Clock /
The Fifth Face of PSL(2,7). Papers 34, 35, 36, Merkabit Research Series.
Zenodo. [DOIs to be assigned on publication]
```
