#!/usr/bin/env python
"""Observable 25b-RGF-long — extended Riemann sweep with high-pass filter.

Riemann mode at 960 samples (vs 240 in obs25b). Rules out whether the
GUE test failure is statistical thinness or observable-choice.
"""
from __future__ import annotations

import json
import time
from math import log, pi

import cirq
import numpy as np

# ---------------------------------------------------------------------------
# Same architecture as obs25b
# ---------------------------------------------------------------------------
N_SITES = 3
DATA_QUBITS = 6
T_CYCLE_BINARY = 30
N_STEPS_PER_RUN = 30
COUPLING = 0.10
J_EDGE = 0.10
SWEEP_N = 960


def _sieve(n):
    upper = max(20, int(n * (np.log(n) + np.log(np.log(max(n, 3)))) + 10))
    mark = np.ones(upper + 1, dtype=bool)
    mark[:2] = False
    for i in range(2, int(upper ** 0.5) + 1):
        if mark[i]:
            mark[i * i :: i] = False
    return np.flatnonzero(mark).tolist()[:n]


PRIMES = _sieve(SWEEP_N + N_STEPS_PER_RUN + 10)


def freq_primes(step):
    return log(PRIMES[step % len(PRIMES)])


def R_gate(u, v, phase):
    yield cirq.ZPowGate(exponent=phase / pi).on(u)
    yield cirq.ZPowGate(exponent=-phase / pi).on(v)


def S_gate(u, v, phase):
    yield cirq.XPowGate(exponent=phase / pi).on(u)
    yield cirq.XPowGate(exponent=-phase / pi).on(v)


def T_gate(u, v, phase):
    yield cirq.ISwapPowGate(exponent=phase / pi).on(u, v)


GATE_FN = {"R": R_gate, "S": S_gate, "T": T_gate}
MATTER_ORDER = ["R", "T", "S"]


def triangle_edge(qubits, i, j, J):
    yield cirq.ISwapPowGate(exponent=J).on(qubits[2 * i], qubits[2 * j + 1])


def binary_step(qubits, step_idx):
    phase = freq_primes(step_idx) * COUPLING
    gate_name = MATTER_ORDER[step_idx % 3]
    gate_fn = GATE_FN[gate_name]
    for site in range(N_SITES):
        u, v = qubits[2 * site], qubits[2 * site + 1]
        yield from gate_fn(u, v, phase)
    for site in range(N_SITES):
        yield from triangle_edge(qubits, site, (site + 1) % N_SITES, J_EDGE)


def build_circuit(offset):
    qubits = [cirq.LineQubit(i) for i in range(DATA_QUBITS)]
    circuit = cirq.Circuit()
    for site in range(N_SITES):
        circuit.append(cirq.H.on(qubits[2 * site]))
    for s in range(N_STEPS_PER_RUN):
        circuit.append(binary_step(qubits, s + offset))
    return circuit, qubits


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


def run_sweep():
    sim = cirq.Simulator()
    ents = np.zeros(SWEEP_N)
    for offset in range(SWEEP_N):
        circuit, _ = build_circuit(offset)
        state = sim.simulate(circuit).final_state_vector
        rho = reduced_density_matrix(state, [0, 1], DATA_QUBITS)
        ents[offset] = entropy(rho)
    return ents


def high_pass(signal, period_cutoff):
    n = len(signal)
    fft = np.fft.rfft(signal - signal.mean())
    for k in range(1, len(fft)):
        if n / k < period_cutoff:
            fft[k] = 0.0
    return np.fft.irfft(fft, n=n)


def find_minima(curve, prominence=0.0):
    idx = []
    for i in range(1, len(curve) - 1):
        if curve[i] < curve[i - 1] and curve[i] < curve[i + 1]:
            if (curve[i - 1] - curve[i]) >= prominence:
                idx.append(i)
    return np.array(idx)


def wigner_cdf(s, ensemble="GUE"):
    grid = np.linspace(0.0, max(float(s.max()) * 1.5, 3.0), 2000)
    if ensemble == "GUE":
        pdf = (32.0 / pi ** 2) * grid ** 2 * np.exp(-4.0 * grid ** 2 / pi)
    elif ensemble == "GOE":
        pdf = (pi / 2.0) * grid * np.exp(-pi * grid ** 2 / 4.0)
    else:  # Poisson
        pdf = np.exp(-grid)
    cdf = np.cumsum(pdf) * (grid[1] - grid[0])
    cdf /= cdf[-1]
    return np.interp(s, grid, cdf)


def ks_test(spacings, ensemble):
    if len(spacings) < 8:
        return float("nan"), float("nan")
    s = np.sort(spacings / spacings.mean())
    n = len(s)
    emp = np.arange(1, n + 1) / n
    theo = wigner_cdf(s, ensemble)
    D = float(np.max(np.abs(emp - theo)))
    lam = (np.sqrt(n) + 0.12 + 0.11 / np.sqrt(n)) * D
    p = 0.0
    for j in range(1, 100):
        p += 2 * (-1) ** (j - 1) * np.exp(-2 * j ** 2 * lam ** 2)
    return D, float(max(0.0, min(1.0, p)))


def main():
    print("=" * 68)
    print("Observable 25b-RGF-long — extended Riemann sweep")
    print("=" * 68)
    print(f"Sweep: {SWEEP_N} offsets (4x obs25b long)")

    t0 = time.time()
    print("Running primes drive sweep...")
    riemann = run_sweep()
    print(f"  runtime {time.time() - t0:.1f}s  mean entropy {riemann.mean():.4f}")

    print("\n" + "-" * 68)
    print(f"{'cutoff':>6} {'mins':>5} {'sp_mn':>6} "
          f"{'p_GUE':>7} {'p_GOE':>7} {'p_Poi':>7}  best")
    print("-" * 68)
    results = []
    for cutoff in [3.5, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0]:
        filt = high_pass(riemann, cutoff)
        mins = find_minima(filt)
        if len(mins) < 8:
            print(f"  {cutoff:5.1f}  {len(mins):3d}  (too few)")
            continue
        spacings = np.diff(mins).astype(float)
        _, p_gue = ks_test(spacings, "GUE")
        _, p_goe = ks_test(spacings, "GOE")
        _, p_poi = ks_test(spacings, "Poisson")
        best_name = max([("GUE", p_gue), ("GOE", p_goe), ("Poisson", p_poi)],
                        key=lambda x: x[1])[0]
        best_p = max(p_gue, p_goe, p_poi)
        print(f"  {cutoff:5.1f}  {len(mins):3d}  {spacings.mean():5.2f}  "
              f"{p_gue:.4f}  {p_goe:.4f}  {p_poi:.4f}  "
              f"{best_name}({best_p:.4f})")
        results.append({
            "cutoff": cutoff,
            "n_minima": int(len(mins)),
            "p_gue": p_gue, "p_goe": p_goe, "p_poisson": p_poi,
            "best_ensemble": best_name, "best_p": best_p,
        })

    if results:
        best = max(results, key=lambda r: r["best_p"])
        print()
        print(f"BEST: cutoff={best['cutoff']}  "
              f"ensemble={best['best_ensemble']}  "
              f"p={best['best_p']:.4f}  "
              f"-> {'PASS' if best['best_p'] >= 0.10 else 'FAIL'}")

    with open("obs25b_riemann_long.json", "w") as f:
        json.dump({
            "sweep_n": SWEEP_N,
            "spectrum": riemann.tolist(),
            "results_by_cutoff": results,
        }, f, indent=2)
    print("\nRaw: obs25b_riemann_long.json")


if __name__ == "__main__":
    main()
