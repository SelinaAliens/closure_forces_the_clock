#!/usr/bin/env python
"""Observable 25a — The Binary-Clock Test.

Paper 35 / Experiment 1. Standalone laptop precursor for the hardware
pre-registration. Tests whether the 31 binary sector of the merkabit
architecture has a dynamical period of h(E_8) = phi(31) = 30 under
rational (Regime 2) drive, and an aperiodic spectrum under log-prime
(Regime 3) drive.

Passing this test is a precondition for the Dual-Clock Factorisation
Theorem of Paper 35: T_full = T_137 (x) T_31 requires both sectors to
have a measurable clock before the tensor product can be claimed.

Architecture. Single triangle, 3 binary (2-spinor) merkabits, 6 data
qubits + 3 readout ancillas (9 total on hardware; state-vector sim uses
the 6 data qubits only). Gates {R, S, T} cycle per step. No F, no P —
that is what separates the 31 binary sector from the 137 ternary.

Thresholds.
    25a-P  Mode B dominant FFT period in [29, 31]
    25a-H  Mode B harmonic purity on divisors of 30 >= 0.80
    25a-R  Mode A power at period 30 <= 0.15

Run:
    python run_obs25a_binary_clock_cirq.py

Output:
    obs25a_binary_clock.json — raw spectra, FFT power, thresholds.
"""
from __future__ import annotations

import json
import time
from math import log, pi

import cirq
import numpy as np

# ---------------------------------------------------------------------------
# Architecture constants
# ---------------------------------------------------------------------------
N_SITES = 3
QUBITS_PER_MERKABIT = 2                         # 2-spinor: 1 for u, 1 for v
DATA_QUBITS = N_SITES * QUBITS_PER_MERKABIT     # 6

T_CYCLE_BINARY = 30          # h(E_8) = phi(31), Paper 8 Sec 7.1
SWEEP_N = 60                 # two full periods
N_STEPS_PER_RUN = 30         # one full period of drive per circuit
COUPLING = 0.10              # drive-phase scale
J_EDGE = 0.10                # triangle edge coupling strength


def _sieve(n: int) -> list[int]:
    """First-n primes via a sieve of Eratosthenes."""
    upper = max(20, int(n * (np.log(n) + np.log(np.log(max(n, 3)))) + 10))
    mark = np.ones(upper + 1, dtype=bool)
    mark[:2] = False
    for i in range(2, int(upper ** 0.5) + 1):
        if mark[i]:
            mark[i * i :: i] = False
    primes = np.flatnonzero(mark).tolist()
    return primes[:n]


# Enough primes to cover the deepest step index we drive.
PRIMES = _sieve(SWEEP_N + N_STEPS_PER_RUN + 10)


# ---------------------------------------------------------------------------
# Drive-frequency modes
# ---------------------------------------------------------------------------
def freq_mode_B(step: int) -> float:
    """Regime 2: rational drive commensurate at T_CYCLE_BINARY = 30."""
    return 2.0 * pi * step / T_CYCLE_BINARY


def freq_mode_A(step: int) -> float:
    """Regime 3: log-prime drive — rationally independent frequencies."""
    return log(PRIMES[step % len(PRIMES)])


# ---------------------------------------------------------------------------
# Binary-sector gates: {R, S, T} only
# ---------------------------------------------------------------------------
def R_gate(u, v, phase):
    """Rotation: opposing-sign Z on u and v (chiral pair)."""
    yield cirq.ZPowGate(exponent=phase / pi).on(u)
    yield cirq.ZPowGate(exponent=-phase / pi).on(v)


def S_gate(u, v, phase):
    """Substrate: opposing-sign X on u and v."""
    yield cirq.XPowGate(exponent=phase / pi).on(u)
    yield cirq.XPowGate(exponent=-phase / pi).on(v)


def T_gate(u, v, phase):
    """Transfer: iSWAP coupling u <-> v within a single merkabit."""
    yield cirq.ISwapPowGate(exponent=phase / pi).on(u, v)


def triangle_edge_coupling(qubits, site_i, site_j, J):
    """Nearest-neighbour iSWAP on the triangle (topology-only, not chiral)."""
    u_i = qubits[2 * site_i]
    v_j = qubits[2 * site_j + 1]
    yield cirq.ISwapPowGate(exponent=J).on(u_i, v_j)


# ---------------------------------------------------------------------------
# Circuit
# ---------------------------------------------------------------------------
def binary_triangle_step(qubits, step_idx: int, freq_fn):
    """One internal step: R/S/T on each merkabit (cycling), then edges."""
    phase = freq_fn(step_idx) * COUPLING

    for site in range(N_SITES):
        u = qubits[2 * site]
        v = qubits[2 * site + 1]
        gate_idx = step_idx % 3
        if gate_idx == 0:
            yield from R_gate(u, v, phase)
        elif gate_idx == 1:
            yield from S_gate(u, v, phase)
        else:
            yield from T_gate(u, v, phase)

    for site in range(N_SITES):
        yield from triangle_edge_coupling(
            qubits, site, (site + 1) % N_SITES, J_EDGE
        )


def build_circuit(offset: int, n_steps: int, mode: str):
    qubits = [cirq.LineQubit(i) for i in range(DATA_QUBITS)]
    circuit = cirq.Circuit()

    # |+> prep on u qubits gives a non-trivial initial state
    for site in range(N_SITES):
        circuit.append(cirq.H.on(qubits[2 * site]))

    freq_fn = freq_mode_B if mode == "B" else freq_mode_A
    for s in range(n_steps):
        circuit.append(binary_triangle_step(qubits, s + offset, freq_fn))

    return circuit, qubits


# ---------------------------------------------------------------------------
# Measurement — partial trace and entropy
# ---------------------------------------------------------------------------
def reduced_density_matrix(state_vec, kept_indices, total_qubits):
    n_kept = len(kept_indices)
    dim_kept = 2 ** n_kept
    shape = [2] * total_qubits
    psi = state_vec.reshape(shape)
    perm = list(kept_indices) + [
        i for i in range(total_qubits) if i not in kept_indices
    ]
    psi = np.transpose(psi, perm)
    psi = psi.reshape(dim_kept, -1)
    return psi @ psi.conj().T


def von_neumann_entropy(rho):
    eigvals = np.linalg.eigvalsh(rho)
    eigvals = eigvals[eigvals > 1e-12]
    if len(eigvals) == 0:
        return 0.0
    return float(-np.sum(eigvals * np.log2(eigvals)))


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------
def run_sweep(mode: str) -> np.ndarray:
    simulator = cirq.Simulator()
    entropies = np.zeros(SWEEP_N)
    for offset in range(SWEEP_N):
        circuit, _ = build_circuit(offset, N_STEPS_PER_RUN, mode)
        state = simulator.simulate(circuit).final_state_vector
        rho = reduced_density_matrix(state, [0, 1], DATA_QUBITS)
        entropies[offset] = von_neumann_entropy(rho)
    return entropies


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def fft_spectrum(entropy_curve):
    n = len(entropy_curve)
    signal = entropy_curve - entropy_curve.mean()
    fft = np.fft.rfft(signal)
    power = np.abs(fft) ** 2
    freqs = np.arange(len(fft)) / n
    periods = np.full_like(freqs, np.inf, dtype=float)
    periods[1:] = 1.0 / freqs[1:]
    return periods, power


def eval_mode_B(periods, power):
    total = power[1:].sum()
    if total < 1e-15:
        return {
            "25a-P": (float("nan"), False),
            "25a-H": (float("nan"), False),
        }
    idx = np.argmax(power[1:]) + 1
    dom = float(periods[idx])
    targets = [30, 15, 10, 6, 5, 3, 2]
    hit = 0.0
    for tp in targets:
        i = int(np.argmin(np.abs(periods - tp)))
        hit += power[i]
    purity = float(hit / total)
    return {
        "25a-P": (dom, 29.0 <= dom <= 31.0),
        "25a-H": (purity, purity >= 0.80),
    }


def eval_mode_A(periods, power):
    total = power[1:].sum()
    if total < 1e-15:
        return {"25a-R": (float("nan"), False)}
    i30 = int(np.argmin(np.abs(periods - 30)))
    frac = float(power[i30] / total)
    return {"25a-R": (frac, frac <= 0.15)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 64)
    print("Observable 25a — The Binary-Clock Test")
    print("Paper 35 / Experiment 1 (laptop precursor)")
    print("=" * 64)
    print(f"Architecture : {N_SITES}-site binary triangle, {DATA_QUBITS} data qubits")
    print(f"Sweep        : {SWEEP_N} offsets (2 periods of T_CYCLE = {T_CYCLE_BINARY})")
    print(f"Per-offset   : {N_STEPS_PER_RUN} internal steps")
    print(f"Coupling     : drive={COUPLING}, J_edge={J_EDGE}")

    t0 = time.time()
    print("\n[1/2] Mode B — Regime 2 (rational drive, omega_k = 2*pi*k/30)")
    spectrum_B = run_sweep("B")
    print(
        f"      runtime {time.time() - t0:.1f}s, "
        f"entropy mean={spectrum_B.mean():.4f} std={spectrum_B.std():.4f}"
    )

    t1 = time.time()
    print("\n[2/2] Mode A — Regime 3 (log-prime drive)")
    spectrum_A = run_sweep("A")
    print(
        f"      runtime {time.time() - t1:.1f}s, "
        f"entropy mean={spectrum_A.mean():.4f} std={spectrum_A.std():.4f}"
    )

    periods_B, power_B = fft_spectrum(spectrum_B)
    periods_A, power_A = fft_spectrum(spectrum_A)
    res_B = eval_mode_B(periods_B, power_B)
    res_A = eval_mode_A(periods_A, power_A)

    print("\n" + "=" * 64)
    print("OBSERVABLE 25a THRESHOLDS")
    print("=" * 64)
    rows = [
        ("25a-P", "Mode B dominant period in [29, 31]", res_B["25a-P"]),
        ("25a-H", "Mode B harmonic purity on divisors of 30 >= 0.80",
         res_B["25a-H"]),
        ("25a-R", "Mode A power at period 30 <= 0.15", res_A["25a-R"]),
    ]
    for key, desc, (val, passed) in rows:
        mark = "PASS" if passed else "FAIL"
        print(f"  {key}  {desc}")
        print(f"        measured = {val:.4f}   ->   {mark}")

    overall = all(p for _, _, (_, p) in rows)
    verdict = (
        "PASS — binary clock present, Paper 35 theorem precondition met"
        if overall
        else "FAIL — theorem precondition not met; revise before Paper 35"
    )
    print(f"\nOVERALL: {verdict}")

    # Top five Fourier peaks for each mode — useful for eyeballing
    def top_peaks(periods, power, k=5):
        order = np.argsort(power[1:])[::-1][:k] + 1
        return [(float(periods[i]), float(power[i])) for i in order]

    print("\nTop FFT peaks (period, power):")
    print(f"  Mode B: {top_peaks(periods_B, power_B)}")
    print(f"  Mode A: {top_peaks(periods_A, power_A)}")

    out = {
        "meta": {
            "observable": "25a",
            "paper": 35,
            "experiment": 1,
            "n_sites": N_SITES,
            "data_qubits": DATA_QUBITS,
            "T_CYCLE_BINARY": T_CYCLE_BINARY,
            "sweep_n": SWEEP_N,
            "n_steps_per_run": N_STEPS_PER_RUN,
            "coupling": COUPLING,
            "j_edge": J_EDGE,
        },
        "mode_B": {
            "spectrum": spectrum_B.tolist(),
            "periods": [None if np.isinf(p) else float(p) for p in periods_B],
            "power": power_B.tolist(),
            "thresholds": {
                k: {"value": v[0], "pass": bool(v[1])} for k, v in res_B.items()
            },
        },
        "mode_A": {
            "spectrum": spectrum_A.tolist(),
            "periods": [None if np.isinf(p) else float(p) for p in periods_A],
            "power": power_A.tolist(),
            "thresholds": {
                k: {"value": v[0], "pass": bool(v[1])} for k, v in res_A.items()
            },
        },
        "overall_pass": overall,
    }
    out_path = "obs25a_binary_clock.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nRaw data written to {out_path}")


if __name__ == "__main__":
    main()
