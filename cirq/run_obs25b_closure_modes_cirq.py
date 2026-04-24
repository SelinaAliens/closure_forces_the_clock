#!/usr/bin/env python
"""Observable 25b — Three Closure Modes of the B_31 Binary Sector.

Paper 35 / Experiment 1 extended. Tests whether the binary triangle has
three distinguishable closure modes, consistent with Paper 14's
"antimatter is the geometry not completing its loop" and Paper 7's
"Riemann zeros are collapse events of the binary architecture":

    MATTER      = R-T-S order + rational drive (Regime 2)
    ANTIMATTER  = R-S-T order + rational drive (Regime 2, chirality flip)
    RIEMANN     = R-T-S order + log-prime drive (Regime 3)

Predictions:
    - MATTER and ANTIMATTER both close at period 60 (same architecture,
      same drive), but differ in phase/harmonic distribution if chirality
      is detected (matter/antimatter distinction operational).
    - MATTER and RIEMANN differ: rational drive gives period 60,
      incommensurate drive gives aperiodic near-closure with Wigner-like
      level-spacing statistics.

Pre-registered thresholds:
    25b-MP   MATTER dominant period in [55, 65]
    25b-MH   MATTER divisor-of-60 purity >= 0.65
    25b-AP   ANTIMATTER dominant period in [55, 65]
    25b-AH   ANTIMATTER divisor-of-60 purity >= 0.65
    25b-MA   MATTER-ANTIMATTER chirality asymmetry detected (>= 0.05)
    25b-RA   RIEMANN dominant period not in [55, 65] (aperiodicity)
    25b-RG   RIEMANN level-spacing KS p-value vs Wigner-GUE >= 0.10

Run:
    python run_obs25b_closure_modes_cirq.py

Output:
    obs25b_closure_modes.json
"""
from __future__ import annotations

import json
import time
from math import log, pi

import cirq
import numpy as np

# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------
N_SITES = 3
QUBITS_PER_MERKABIT = 2
DATA_QUBITS = N_SITES * QUBITS_PER_MERKABIT  # 6

T_CYCLE_BINARY = 30
SWEEP_N_SHORT = 60         # matter / antimatter — two periods of 30
SWEEP_N_LONG = 240         # riemann — long enough for level-spacing statistics
N_STEPS_PER_RUN = 30
COUPLING = 0.10
J_EDGE = 0.10


def _sieve(n: int) -> list[int]:
    upper = max(20, int(n * (np.log(n) + np.log(np.log(max(n, 3)))) + 10))
    mark = np.ones(upper + 1, dtype=bool)
    mark[:2] = False
    for i in range(2, int(upper ** 0.5) + 1):
        if mark[i]:
            mark[i * i :: i] = False
    primes = np.flatnonzero(mark).tolist()
    return primes[:n]


PRIMES = _sieve(SWEEP_N_LONG + N_STEPS_PER_RUN + 10)


# ---------------------------------------------------------------------------
# Drive frequencies
# ---------------------------------------------------------------------------
def freq_rational(step: int) -> float:
    return 2.0 * pi * step / T_CYCLE_BINARY


def freq_primes(step: int) -> float:
    return log(PRIMES[step % len(PRIMES)])


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------
def R_gate(u, v, phase):
    yield cirq.ZPowGate(exponent=phase / pi).on(u)
    yield cirq.ZPowGate(exponent=-phase / pi).on(v)


def S_gate(u, v, phase):
    yield cirq.XPowGate(exponent=phase / pi).on(u)
    yield cirq.XPowGate(exponent=-phase / pi).on(v)


def T_gate(u, v, phase):
    yield cirq.ISwapPowGate(exponent=phase / pi).on(u, v)


GATE_FN = {"R": R_gate, "S": S_gate, "T": T_gate}

# Paper 14: R-T-S = matter (write chirality); R-S-T = antimatter (read chirality)
CHIRALITY_ORDER = {
    "matter": ["R", "T", "S"],
    "antimatter": ["R", "S", "T"],
}


def triangle_edge(qubits, site_i, site_j, J):
    u_i = qubits[2 * site_i]
    v_j = qubits[2 * site_j + 1]
    yield cirq.ISwapPowGate(exponent=J).on(u_i, v_j)


def binary_step(qubits, step_idx, freq_fn, chirality):
    phase = freq_fn(step_idx) * COUPLING
    order = CHIRALITY_ORDER[chirality]
    gate_name = order[step_idx % 3]
    gate_fn = GATE_FN[gate_name]
    for site in range(N_SITES):
        u = qubits[2 * site]
        v = qubits[2 * site + 1]
        yield from gate_fn(u, v, phase)
    for site in range(N_SITES):
        yield from triangle_edge(qubits, site, (site + 1) % N_SITES, J_EDGE)


def build_circuit(offset, n_steps, freq_fn, chirality):
    qubits = [cirq.LineQubit(i) for i in range(DATA_QUBITS)]
    circuit = cirq.Circuit()
    for site in range(N_SITES):
        circuit.append(cirq.H.on(qubits[2 * site]))
    for s in range(n_steps):
        circuit.append(binary_step(qubits, s + offset, freq_fn, chirality))
    return circuit, qubits


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------
def reduced_density_matrix(state, kept, total):
    n_kept = len(kept)
    shape = [2] * total
    psi = state.reshape(shape)
    perm = list(kept) + [i for i in range(total) if i not in kept]
    psi = np.transpose(psi, perm)
    psi = psi.reshape(2 ** n_kept, -1)
    return psi @ psi.conj().T


def entropy(rho):
    ev = np.linalg.eigvalsh(rho)
    ev = ev[ev > 1e-12]
    return 0.0 if len(ev) == 0 else float(-np.sum(ev * np.log2(ev)))


# ---------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------
def run_mode(mode_label, chirality, sweep_n):
    freq_fn = freq_rational if mode_label == "rational" else freq_primes
    sim = cirq.Simulator()
    ents = np.zeros(sweep_n)
    for offset in range(sweep_n):
        circuit, _ = build_circuit(offset, N_STEPS_PER_RUN, freq_fn, chirality)
        state = sim.simulate(circuit).final_state_vector
        rho = reduced_density_matrix(state, [0, 1], DATA_QUBITS)
        ents[offset] = entropy(rho)
    return ents


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def fft_spectrum(curve):
    n = len(curve)
    signal = curve - curve.mean()
    fft = np.fft.rfft(signal)
    power = np.abs(fft) ** 2
    freqs = np.arange(len(fft)) / n
    periods = np.full_like(freqs, np.inf, dtype=float)
    periods[1:] = 1.0 / freqs[1:]
    return periods, power


def divisor_purity(periods, power, target=60, tol=0.5):
    """Fraction of non-DC power sitting on divisors of `target`."""
    divisors = [d for d in range(2, target + 1) if target % d == 0]
    total = power[1:].sum()
    if total < 1e-15:
        return float("nan")
    hit = 0.0
    for d in divisors:
        idx = int(np.argmin(np.abs(periods - d)))
        if abs(periods[idx] - d) < tol:
            hit += power[idx]
    return float(hit / total)


def dominant_period(periods, power):
    if power[1:].sum() < 1e-15:
        return float("nan")
    idx = np.argmax(power[1:]) + 1
    return float(periods[idx])


def top_peaks(periods, power, k=6):
    order = np.argsort(power[1:])[::-1][:k] + 1
    return [(float(periods[i]), float(power[i])) for i in order]


def chirality_asymmetry(curve_m, curve_a):
    """L2 asymmetry between matter and antimatter entropy curves."""
    diff = curve_m - curve_a
    base = 0.5 * (np.abs(curve_m).mean() + np.abs(curve_a).mean())
    if base < 1e-15:
        return float("nan")
    return float(np.sqrt((diff ** 2).mean()) / base)


# ---------------------------------------------------------------------------
# Level-spacing (GUE) test for Riemann mode
# ---------------------------------------------------------------------------
def local_minima(curve, min_prominence=0.0):
    """Indices of interior local minima."""
    idx = []
    for i in range(1, len(curve) - 1):
        if curve[i] < curve[i - 1] and curve[i] < curve[i + 1]:
            if curve[i - 1] - curve[i] >= min_prominence:
                idx.append(i)
    return np.array(idx)


def wigner_gue_cdf(s):
    """Approximate GUE Wigner-surmise CDF via numerical integration."""
    # P(s) = (32/pi^2) s^2 exp(-4 s^2 / pi)
    grid = np.linspace(0, max(s.max() * 1.5, 3.0), 2000)
    pdf = (32.0 / pi ** 2) * grid ** 2 * np.exp(-4.0 * grid ** 2 / pi)
    cdf = np.cumsum(pdf) * (grid[1] - grid[0])
    cdf /= cdf[-1]
    return np.interp(s, grid, cdf)


def ks_test_gue(spacings):
    """Simple two-sided KS statistic vs GUE Wigner surmise."""
    if len(spacings) < 8:
        return float("nan"), float("nan")
    s = np.sort(spacings / spacings.mean())
    n = len(s)
    empirical = np.arange(1, n + 1) / n
    theoretical = wigner_gue_cdf(s)
    D = np.max(np.abs(empirical - theoretical))
    # Kolmogorov limiting distribution p-value
    lam = (np.sqrt(n) + 0.12 + 0.11 / np.sqrt(n)) * D
    p = 0.0
    for j in range(1, 100):
        p += 2 * (-1) ** (j - 1) * np.exp(-2 * j ** 2 * lam ** 2)
    p = float(max(0.0, min(1.0, p)))
    return float(D), p


def riemann_gue_analysis(curve):
    mins = local_minima(curve)
    if len(mins) < 8:
        return {
            "n_minima": int(len(mins)),
            "ks_D": None,
            "ks_p": None,
            "spacings_mean": None,
            "spacings_std": None,
        }
    spacings = np.diff(mins).astype(float)
    D, p = ks_test_gue(spacings)
    return {
        "n_minima": int(len(mins)),
        "ks_D": D,
        "ks_p": p,
        "spacings_mean": float(spacings.mean()),
        "spacings_std": float(spacings.std()),
    }


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
def evaluate(matter, antimatter, riemann, riemann_gue):
    periods_m, power_m = fft_spectrum(matter)
    periods_a, power_a = fft_spectrum(antimatter)
    periods_r, power_r = fft_spectrum(riemann)

    dom_m = dominant_period(periods_m, power_m)
    dom_a = dominant_period(periods_a, power_a)
    dom_r = dominant_period(periods_r, power_r)
    pur_m = divisor_purity(periods_m, power_m, target=60)
    pur_a = divisor_purity(periods_a, power_a, target=60)
    asym = chirality_asymmetry(matter, antimatter)
    ks_p = riemann_gue.get("ks_p")

    rows = [
        ("25b-MP", "MATTER dominant period in [55,65]",
         dom_m, 55.0 <= dom_m <= 65.0),
        ("25b-MH", "MATTER divisor-of-60 purity >= 0.65",
         pur_m, pur_m >= 0.65),
        ("25b-AP", "ANTIMATTER dominant period in [55,65]",
         dom_a, 55.0 <= dom_a <= 65.0),
        ("25b-AH", "ANTIMATTER divisor-of-60 purity >= 0.65",
         pur_a, pur_a >= 0.65),
        ("25b-MA", "MATTER-ANTIMATTER chirality asymmetry >= 0.05",
         asym, asym >= 0.05),
        ("25b-RA", "RIEMANN dominant period NOT in [55,65]",
         dom_r, not (55.0 <= dom_r <= 65.0)),
        ("25b-RG", "RIEMANN Wigner-GUE KS p >= 0.10",
         ks_p if ks_p is not None else float("nan"),
         (ks_p is not None) and ks_p >= 0.10),
    ]

    return rows, {
        "matter_fft": (periods_m, power_m),
        "antimatter_fft": (periods_a, power_a),
        "riemann_fft": (periods_r, power_r),
        "dom_m": dom_m,
        "dom_a": dom_a,
        "dom_r": dom_r,
        "pur_m": pur_m,
        "pur_a": pur_a,
        "asym": asym,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 68)
    print("Observable 25b — Three Closure Modes of the B_31 Binary Sector")
    print("Paper 35 / Experiment 1 (extended)")
    print("=" * 68)
    print(f"Architecture : {N_SITES}-site binary triangle, {DATA_QUBITS} data qubits")
    print(f"Sweeps       : short={SWEEP_N_SHORT}, long={SWEEP_N_LONG}")
    print(f"Per-offset   : {N_STEPS_PER_RUN} internal steps")

    t0 = time.time()
    print("\n[1/3] MATTER — R-T-S order, rational drive at 2pi/30")
    matter = run_mode("rational", "matter", SWEEP_N_SHORT)
    print(f"      runtime {time.time() - t0:.1f}s  entropy mean={matter.mean():.4f}")

    t1 = time.time()
    print("\n[2/3] ANTIMATTER — R-S-T order, rational drive at 2pi/30")
    antimatter = run_mode("rational", "antimatter", SWEEP_N_SHORT)
    print(f"      runtime {time.time() - t1:.1f}s  entropy mean={antimatter.mean():.4f}")

    t2 = time.time()
    print("\n[3/3] RIEMANN — R-T-S order, log-prime drive (Regime 3)")
    riemann = run_mode("primes", "matter", SWEEP_N_LONG)
    print(f"      runtime {time.time() - t2:.1f}s  entropy mean={riemann.mean():.4f}")

    riemann_gue = riemann_gue_analysis(riemann)
    print(f"      riemann minima n={riemann_gue['n_minima']}  "
          f"KS p-value={riemann_gue['ks_p']}")

    rows, extras = evaluate(matter, antimatter, riemann, riemann_gue)

    print("\n" + "=" * 68)
    print("OBSERVABLE 25b THRESHOLDS")
    print("=" * 68)
    for key, desc, val, passed in rows:
        mark = "PASS" if passed else "FAIL"
        v = f"{val:.4f}" if isinstance(val, float) and not np.isnan(val) else str(val)
        print(f"  {key}  {desc}")
        print(f"        measured = {v}   ->   {mark}")

    overall = sum(1 for _, _, _, p in rows if p)
    print(f"\nPASS count: {overall} / {len(rows)}")

    # Inspect top peaks
    print("\nTop FFT peaks (period, power):")
    for label, curve in [("MATTER", matter), ("ANTIMATTER", antimatter),
                         ("RIEMANN", riemann)]:
        per, pwr = fft_spectrum(curve)
        print(f"  {label:11s}: {top_peaks(per, pwr)}")

    # Output
    out = {
        "meta": {
            "observable": "25b",
            "paper": 35,
            "experiment": "1 extended",
            "n_sites": N_SITES,
            "data_qubits": DATA_QUBITS,
            "T_CYCLE_BINARY": T_CYCLE_BINARY,
            "sweep_n_short": SWEEP_N_SHORT,
            "sweep_n_long": SWEEP_N_LONG,
            "n_steps_per_run": N_STEPS_PER_RUN,
            "coupling": COUPLING,
            "j_edge": J_EDGE,
        },
        "matter": {
            "spectrum": matter.tolist(),
            "dominant_period": extras["dom_m"],
            "divisor_60_purity": extras["pur_m"],
            "top_peaks": top_peaks(*fft_spectrum(matter)),
        },
        "antimatter": {
            "spectrum": antimatter.tolist(),
            "dominant_period": extras["dom_a"],
            "divisor_60_purity": extras["pur_a"],
            "top_peaks": top_peaks(*fft_spectrum(antimatter)),
        },
        "riemann": {
            "spectrum": riemann.tolist(),
            "dominant_period": extras["dom_r"],
            "top_peaks": top_peaks(*fft_spectrum(riemann)),
            "gue_analysis": riemann_gue,
        },
        "matter_antimatter_asymmetry": extras["asym"],
        "thresholds": {key: {"value": val, "pass": bool(p)}
                       for key, _, val, p in rows},
    }
    with open("obs25b_closure_modes.json", "w") as f:
        json.dump(out, f, indent=2, default=lambda x: None if (isinstance(x, float) and np.isnan(x)) else x)
    print("\nRaw data written to obs25b_closure_modes.json")


if __name__ == "__main__":
    main()
