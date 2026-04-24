#!/usr/bin/env python
"""Observable 25c — The 7-Rung Chirality Cascade.

Paper 36 / Experiment 1. Tests whether the architectural chirality
asymmetry delta ~ 0.065 (Paper 35) propagates multiplicatively across
the seven rungs of the genesis pipeline, surviving at PSL(2,7) level
as delta^7 ~ 5e-9 — the observed baryon asymmetry.

Rungs tested on laptop state-vector simulator:
    1 — triangle       (C_3, 3 sites, 3 edges,  3 qubits)
    2 — tetrahedron    (K_4, 4 sites, 6 edges,  4 qubits)
    3 — pentachoron    (K_5, 5 sites, 10 edges, 5 qubits)
    4 — dual pentachoron / cube Q_3 (8 sites, 12 edges, 8 qubits)
    5 — tesseract Q_4  (16 sites, 32 edges, 16 qubits)
    6 — 24-cell        (24 sites, 96 edges, 24 qubits) — optional, heavy

Rung 7 (PSL(2,7)) is the Observable 25 hardware pre-registration
(Paper 35); it is not a direct simulation target here because its
natural realisation is a 9-qubit triangle circuit with Paper 35's
full machinery.

For each rung we run matter (R-T-S gate order) and antimatter (R-S-T),
measure the RMS chirality asymmetry between the entropy curves, and
compare to the Paper 35 reference delta_1 = 0.1268.

Key test: is the cascade multiplicative? If yes, running the product
delta_1 * delta_2 * ... * delta_6 should project toward delta^7 ~ eta_B.

Run:
    python run_obs25c_chirality_cascade_cirq.py [--heavy]

--heavy includes rung 6 (24-cell, ~20 min); default is rungs 1-5.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from math import pi

import cirq
import numpy as np


# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------
T_CYCLE_BINARY = 30
SWEEP_N = 60            # two master periods
N_STEPS_PER_RUN = 30
COUPLING = 0.10


def freq_rational(step: int) -> float:
    return 2.0 * pi * step / T_CYCLE_BINARY


CHIRALITY_ORDER = {
    "matter": ["R", "T", "S"],
    "antimatter": ["R", "S", "T"],
}


# ---------------------------------------------------------------------------
# Graph topologies per rung
# ---------------------------------------------------------------------------
def cycle_edges(n):
    return [(i, (i + 1) % n) for i in range(n)]


def complete_edges(n):
    return [(i, j) for i in range(n) for j in range(i + 1, n)]


def hypercube_edges(n_bits):
    edges = []
    for v in range(2 ** n_bits):
        for k in range(n_bits):
            w = v ^ (1 << k)
            if v < w:
                edges.append((v, w))
    return edges


def twenty_four_cell_edges():
    """24-cell: permutations of (+-1, +-1, 0, 0) in 4D. Edges = nearest
    neighbours at distance sqrt(2)."""
    verts = []
    for i in range(4):
        for j in range(i + 1, 4):
            for si in (+1, -1):
                for sj in (+1, -1):
                    v = [0, 0, 0, 0]
                    v[i] = si
                    v[j] = sj
                    verts.append(tuple(v))
    # 24 unique vertices
    verts = list(dict.fromkeys(verts))
    assert len(verts) == 24, f"got {len(verts)} vertices"
    edges = []
    for a in range(24):
        for b in range(a + 1, 24):
            d2 = sum((verts[a][k] - verts[b][k]) ** 2 for k in range(4))
            if abs(d2 - 2.0) < 1e-9:
                edges.append((a, b))
    return edges


class Rung:
    def __init__(self, number, name, n_sites, edges):
        self.number = number
        self.name = name
        self.n_sites = n_sites
        self.edges = edges

    def __repr__(self):
        return (f"Rung {self.number} ({self.name}): "
                f"{self.n_sites} sites, {len(self.edges)} edges")


RUNGS_STANDARD = [
    Rung(1, "triangle",         3,  cycle_edges(3)),
    Rung(2, "tetrahedron",      4,  complete_edges(4)),
    Rung(3, "pentachoron",      5,  complete_edges(5)),
    Rung(4, "dual_pentachoron", 8,  hypercube_edges(3)),
    Rung(5, "tesseract",        16, hypercube_edges(4)),
]


# ---------------------------------------------------------------------------
# Circuit construction (1 qubit per site; T acts on graph edges)
# ---------------------------------------------------------------------------
def gate_step(qubits, rung, step_idx, chirality):
    """One internal step for a given rung."""
    phase = freq_rational(step_idx) * COUPLING
    gate_name = CHIRALITY_ORDER[chirality][step_idx % 3]

    if gate_name == "R":
        for q in qubits:
            yield cirq.ZPowGate(exponent=phase / pi).on(q)
    elif gate_name == "S":
        for q in qubits:
            yield cirq.XPowGate(exponent=phase / pi).on(q)
    else:  # T
        for (i, j) in rung.edges:
            yield cirq.ISwapPowGate(exponent=phase / pi).on(qubits[i], qubits[j])


def build_circuit(rung, offset, chirality):
    qubits = [cirq.LineQubit(i) for i in range(rung.n_sites)]
    circuit = cirq.Circuit()
    # Non-trivial initial state: H on every second site
    for i in range(0, rung.n_sites, 2):
        circuit.append(cirq.H.on(qubits[i]))
    for s in range(N_STEPS_PER_RUN):
        circuit.append(gate_step(qubits, rung, s + offset, chirality))
    return circuit, qubits


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------
def entropy_of_qubit(state_vector, qubit_index, total_qubits):
    """Von Neumann entropy of a single-qubit reduced density matrix."""
    shape = [2] * total_qubits
    psi = state_vector.reshape(shape)
    perm = [qubit_index] + [i for i in range(total_qubits) if i != qubit_index]
    psi = np.transpose(psi, perm)
    psi = psi.reshape(2, -1)
    rho = psi @ psi.conj().T
    ev = np.linalg.eigvalsh(rho)
    ev = ev[ev > 1e-12]
    if len(ev) == 0:
        return 0.0
    return float(-np.sum(ev * np.log2(ev)))


def run_rung(rung, chirality):
    sim = cirq.Simulator()
    ents = np.zeros(SWEEP_N)
    for offset in range(SWEEP_N):
        circuit, _ = build_circuit(rung, offset, chirality)
        state = sim.simulate(circuit).final_state_vector
        ents[offset] = entropy_of_qubit(state, 0, rung.n_sites)
    return ents


def chirality_asymmetry(curve_m, curve_a):
    diff = curve_m - curve_a
    base = 0.5 * (np.abs(curve_m).mean() + np.abs(curve_a).mean())
    if base < 1e-15:
        return float("nan")
    return float(np.sqrt((diff ** 2).mean()) / base)


# ---------------------------------------------------------------------------
# Cascade analysis
# ---------------------------------------------------------------------------
def cascade_product(deltas):
    """Multiplicative survival if deltas compound independently."""
    product = 1.0
    for d in deltas:
        product *= d
    return product


def cascade_average(deltas):
    geo_mean = math.exp(sum(math.log(d) for d in deltas) / len(deltas))
    arith_mean = sum(deltas) / len(deltas)
    return arith_mean, geo_mean


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--heavy", action="store_true",
                        help="include rung 6 (24-cell, ~20 min)")
    args = parser.parse_args()

    rungs = list(RUNGS_STANDARD)
    if args.heavy:
        rungs.append(Rung(6, "24-cell", 24, twenty_four_cell_edges()))

    print("=" * 72)
    print("Observable 25c — The 7-Rung Chirality Cascade")
    print("Paper 36 / Experiment 1")
    print("=" * 72)
    for r in rungs:
        print(f"  {r}")
    print()

    per_rung = []
    for rung in rungs:
        t0 = time.time()
        print(f"Rung {rung.number} ({rung.name}, {rung.n_sites}q, "
              f"{len(rung.edges)} edges)...")

        matter = run_rung(rung, "matter")
        antimatter = run_rung(rung, "antimatter")
        delta = chirality_asymmetry(matter, antimatter)
        runtime = time.time() - t0

        print(f"  matter mean entropy     = {matter.mean():.4f}")
        print(f"  antimatter mean entropy = {antimatter.mean():.4f}")
        print(f"  chirality delta         = {delta:.4f}")
        print(f"  runtime                 = {runtime:.1f}s")
        print()

        per_rung.append({
            "number": rung.number,
            "name": rung.name,
            "n_sites": rung.n_sites,
            "n_edges": len(rung.edges),
            "matter_mean_entropy": float(matter.mean()),
            "antimatter_mean_entropy": float(antimatter.mean()),
            "chirality_delta": delta,
            "runtime_sec": runtime,
            "matter_spectrum": matter.tolist(),
            "antimatter_spectrum": antimatter.tolist(),
        })

    # Cascade analysis
    deltas = [r["chirality_delta"] for r in per_rung]
    n = len(deltas)

    print("=" * 72)
    print("CASCADE ANALYSIS")
    print("=" * 72)
    print(f"Per-rung chirality deltas (rung 1 to {n}):")
    for r in per_rung:
        print(f"  rung {r['number']} ({r['name']:>18s}): "
              f"delta = {r['chirality_delta']:.4f}")

    arith, geo = cascade_average(deltas)
    print(f"\nArithmetic mean delta = {arith:.4f}")
    print(f"Geometric mean delta  = {geo:.4f}")

    prod_measured = cascade_product(deltas)
    print(f"\nMultiplicative product of {n} measured rungs:")
    print(f"  product(delta_1..{n}) = {prod_measured:.4e}")

    # Extrapolate to 7 rungs using geometric mean
    if n < 7:
        extrap = prod_measured * (geo ** (7 - n))
        print(f"  extrapolation to 7 rungs (geo-mean fill) = {extrap:.4e}")

    # Observed baryon asymmetry
    eta_B_obs = 6.1e-10
    print(f"\nObserved eta_B = {eta_B_obs:.2e}")

    # Reference delta from Paper 35 (binary triangle 2-spinor, 6q)
    delta_paper35 = 0.1268
    predicted_7fold = delta_paper35 ** 7
    print(f"\nPaper 35 reference delta = {delta_paper35:.4f}")
    print(f"  delta^7 = {predicted_7fold:.4e}  (cascade hypothesis target)")

    # Consistency check: is delta roughly constant across rungs?
    delta_std = float(np.std(deltas))
    delta_mean = float(np.mean(deltas))
    coefficient_of_variation = delta_std / delta_mean if delta_mean > 0 else float("inf")
    print(f"\nAcross-rung delta CV = {coefficient_of_variation:.2f}")
    uniform = coefficient_of_variation < 0.30
    print(f"  uniform (CV < 0.30)? {'YES' if uniform else 'NO'}")

    # Pre-registered thresholds
    print("\n" + "=" * 72)
    print("OBSERVABLE 25c THRESHOLDS")
    print("=" * 72)
    rows = [
        ("25c-UNI", "Per-rung delta uniform (CV < 0.30)",
         coefficient_of_variation, uniform),
        ("25c-NONZ", "All rung deltas detectable (> 0.02)",
         float(min(deltas)), min(deltas) > 0.02),
    ]
    if n >= 6:
        # When we have at least 6 rungs measured, test cascade survival
        in_range = 1e-12 < prod_measured < 1e-7
        rows.append(("25c-CASC",
                     "6+ rung cascade product in [1e-12, 1e-7] (eta_B scale)",
                     prod_measured, in_range))
    for key, desc, val, passed in rows:
        mark = "PASS" if passed else "FAIL"
        val_str = (f"{val:.4e}" if abs(val) < 1e-2
                   else f"{val:.4f}")
        print(f"  {key}  {desc}")
        print(f"        measured = {val_str}   ->   {mark}")

    out = {
        "meta": {
            "observable": "25c",
            "paper": 36,
            "n_rungs_tested": n,
            "heavy_mode": args.heavy,
            "sweep_n": SWEEP_N,
            "n_steps_per_run": N_STEPS_PER_RUN,
            "coupling": COUPLING,
            "paper35_reference_delta": delta_paper35,
            "eta_B_observed": eta_B_obs,
        },
        "rungs": per_rung,
        "cascade": {
            "deltas": deltas,
            "arith_mean": arith,
            "geo_mean": geo,
            "product_measured": prod_measured,
            "product_extrapolated_7": (
                prod_measured * geo ** (7 - n) if n < 7 else prod_measured
            ),
            "delta_mean": delta_mean,
            "delta_std": delta_std,
            "coefficient_of_variation": coefficient_of_variation,
            "paper35_prediction_delta7": predicted_7fold,
        },
        "thresholds": {k: {"value": v, "pass": bool(p)}
                       for k, _, v, p in rows},
    }
    with open("obs25c_chirality_cascade.json", "w") as f:
        json.dump(out, f, indent=2, default=lambda x: None if
                  (isinstance(x, float) and (np.isnan(x) or np.isinf(x))) else x)
    print("\nRaw data: obs25c_chirality_cascade.json")


if __name__ == "__main__":
    main()
