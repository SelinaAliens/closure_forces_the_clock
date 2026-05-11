#!/usr/bin/env python3
"""
Observable 23 — Pre-hardware noise feasibility sweep (Qiskit Aer).

Reduced 8-qubit proxy of Paper 34's Observable 23 protocol:
    one compute merkabit (4q) writes to a database merkabit (4q) via a
    cross-chiral tunnel; we sweep 36 phase offsets and read the Renyi-2
    entropy of v_D via a 4-qubit SWAP test against a Z3-eigenstate
    reference. Paper 34's full Stage C is 28 qubits (double triangle); the
    8q proxy preserves the single-cell Z3 / period-12 dynamics that the
    threshold tests target, at a qubit count tractable on Aer with
    realistic IBM noise.

Pre-registered Paper 34 thresholds (from Stage C ideal sim):
    23-C  dominant FFT period in [11.88, 12.12]      (12 +/- 1%)
    23-Z  peak-to-trough offset gap = T_CYCLE/3 +/- 1 step  (4 +/- 1)
    23-P  peak-to-trough Renyi-2 entropy contrast >= 0.02
    23-H  bichromatic purity on {12, 6} >= 0.90      (90% of non-DC)

Noise levels swept:
    p_depol = 0.0          ideal sim baseline
    p_depol = 0.001        Heron r2 best-of-band proxy
    p_depol = 0.003        Heron r2 typical
    p_depol = 0.005        Eagle r3 typical
    fake_backend = FakeSherbrooke   real Eagle r3 calibration

Falsification: if 23-H drops below 0.90 (or any threshold fails) at
p_depol >= 0.003, the period-12 signature is noise-fragile and the
hardware test as written has insufficient SNR.

Usage:
    python run_obs23_p34_aer.py --shots 1024 --quick      # ~3 min smoke
    python run_obs23_p34_aer.py --shots 4096              # ~25 min full
    python run_obs23_p34_aer.py --fake sherbrooke         # FakeSherbrooke
"""
from __future__ import annotations
import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
from qiskit.circuit.library import UnitaryGate
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error

SCRIPT_DIR = Path(__file__).parent.resolve()
RESULTS_DIR = SCRIPT_DIR.parent / "results"

T_CYCLE = 12
N_OFFSETS = 36
COUPLING = 0.10
J_INTRA = 0.10
J_MEM = 0.5

OMEGA = complex(math.cos(2 * math.pi / 3), math.sin(2 * math.pi / 3))


# ---------------------------------------------------------------------------
# Z3 eigenstates on a 2-qubit (4d) register
# ---------------------------------------------------------------------------
def z3_state(k: int) -> np.ndarray:
    """k=0: alpha, k=1: beta (omega), k=2: gamma (omega^2). 4d, 4th coord = 0."""
    coeffs = np.array([1.0, OMEGA ** (-k), OMEGA ** (-2 * k), 0.0], dtype=complex)
    return coeffs / math.sqrt(3)


# ---------------------------------------------------------------------------
# Internal merkabit step (Paper 34 / Paper 24 convention)
#   three isoclinic rotation planes per step, T_CYCLE = 12
# ---------------------------------------------------------------------------
def cross_gate(theta):
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    Cf = np.array([[c, 0, -s, 0], [0, c, 0, -s],
                   [s, 0,  c, 0], [0, s, 0,  c]], dtype=complex)
    Ci = np.array([[c, 0,  s, 0], [0, c, 0,  s],
                   [-s, 0, c, 0], [0, -s, 0, c]], dtype=complex)
    return Cf, Ci


def horiz_gate(theta):
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    Hf = np.array([[c, -s, 0, 0], [s, c, 0, 0],
                   [0, 0, c, -s], [0, 0, s, c]], dtype=complex)
    Hi = np.array([[c, s, 0, 0], [-s, c, 0, 0],
                   [0, 0, c, s], [0, 0, -s, c]], dtype=complex)
    return Hf, Hi


def diag_gate(theta):
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    Df = np.array([[c, 0, 0, -s], [0, c, -s, 0],
                   [0, s, c, 0], [s, 0, 0, c]], dtype=complex)
    Di = np.array([[c, 0, 0, s], [0, c, s, 0],
                   [0, -s, c, 0], [-s, 0, 0, c]], dtype=complex)
    return Df, Di


def step_angles(step_idx: int):
    theta = (2 * math.pi / T_CYCLE) * COUPLING
    w = 2 * math.pi * step_idx / T_CYCLE
    return (theta * (1.0 + 0.3 * math.cos(w)),
            theta * (1.0 + 0.3 * math.cos(w + 2 * math.pi / 3)),
            theta * (1.0 + 0.3 * math.cos(w + 4 * math.pi / 3)))


def merkabit_internal_step(qc, u_qubits, v_qubits, step_idx):
    th_c, th_h, th_d = step_angles(step_idx)
    Cf, Ci = cross_gate(th_c)
    qc.append(UnitaryGate(Cf, label="Cf"), u_qubits)
    qc.append(UnitaryGate(Ci, label="Ci"), v_qubits)
    Hf, Hi = horiz_gate(th_h)
    qc.append(UnitaryGate(Hf, label="Hf"), u_qubits)
    qc.append(UnitaryGate(Hi, label="Hi"), v_qubits)
    Df, Di = diag_gate(th_d)
    qc.append(UnitaryGate(Df, label="Df"), u_qubits)
    qc.append(UnitaryGate(Di, label="Di"), v_qubits)


def cross_chiral_tunnel(qc, u_src, v_dst, J):
    """iSWAP^J between u_src[0] and v_dst[0], iSWAP^(-J) between [1]s."""
    iswap = np.array([[1, 0, 0, 0],
                      [0, math.cos(math.pi * J / 2),
                          1j * math.sin(math.pi * J / 2), 0],
                      [0, 1j * math.sin(math.pi * J / 2),
                          math.cos(math.pi * J / 2), 0],
                      [0, 0, 0, 1]], dtype=complex)
    iswap_inv = np.array([[1, 0, 0, 0],
                          [0, math.cos(math.pi * J / 2),
                              -1j * math.sin(math.pi * J / 2), 0],
                          [0, -1j * math.sin(math.pi * J / 2),
                              math.cos(math.pi * J / 2), 0],
                          [0, 0, 0, 1]], dtype=complex)
    qc.append(UnitaryGate(iswap, label=f"isw{J}"), [u_src[0], v_dst[0]])
    qc.append(UnitaryGate(iswap_inv, label=f"isw-{J}"), [u_src[1], v_dst[1]])


# ---------------------------------------------------------------------------
# Circuit: 8q proxy
#   q[0,1] = u_M       compute merkabit u
#   q[2,3] = v_M       compute merkabit v
#   q[4,5] = u_D       database u (held |0>)
#   q[6,7] = v_D       database v (write target)
# ---------------------------------------------------------------------------
def build_obs23_circuit(label_M: int, label_D_ref: int, offset: int,
                         n_compute_steps: int = 12):
    """Run one offset configuration and prepare for SWAP-test readout.

       Returns a circuit that:
         - preps merkabit M with Z3 label `label_M` on both u and v
         - preps database D with v_D = Z3 eigenstate `label_D_ref`
         - runs `offset` filler internal steps on M
         - tunnels u_M -> v_D at J_MEM
         - runs `n_compute_steps` more internal steps on M
         - tunnels back v_D -> u_M
         - does SWAP test of v_D against the same Z3 reference
    """
    n_data = 8
    n_anc = 4   # 4-qubit SWAP test on v_D against the Z3 reference
    n_ref = 2   # Z3 ref on u-pair of an extra register
    q = QuantumRegister(n_data + n_ref + 1, "q")
    c = ClassicalRegister(1, "c")
    qc = QuantumCircuit(q, c)

    # Index aliases
    u_M = [q[0], q[1]]; v_M = [q[2], q[3]]
    u_D = [q[4], q[5]]; v_D = [q[6], q[7]]
    ref = [q[8], q[9]]
    anc = q[10]

    # State prep
    qc.initialize(z3_state(label_M), u_M)
    qc.initialize(z3_state(label_M), v_M)
    qc.initialize(z3_state(0),       u_D)   # u_D held in alpha
    qc.initialize(z3_state(0),       v_D)   # v_D start in alpha
    qc.initialize(z3_state(label_D_ref), ref)

    # Offset: pre-tunnel internal steps on M (this is what the offset varies)
    for s in range(offset):
        merkabit_internal_step(qc, u_M, v_M, s)

    # Cross-chiral tunnel: write u_M -> v_D
    cross_chiral_tunnel(qc, u_M, v_D, J_MEM)

    # Compute steps (one Coxeter period worth)
    for s in range(n_compute_steps):
        merkabit_internal_step(qc, u_M, v_M, s + offset)

    # Tunnel back: v_D -> u_M (read)
    cross_chiral_tunnel(qc, v_D, u_M, J_MEM)

    # SWAP test: |v_D> vs |ref> (2 qubits each, controlled SWAP)
    qc.h(anc)
    qc.cswap(anc, v_D[0], ref[0])
    qc.cswap(anc, v_D[1], ref[1])
    qc.h(anc)
    qc.measure(anc, c[0])
    return qc


# ---------------------------------------------------------------------------
# Aer + noise
# ---------------------------------------------------------------------------
def build_depolarizing_noise(p):
    nm = NoiseModel()
    one_q = ["id", "x", "y", "z", "h", "s", "sdg", "t", "tdg",
             "rx", "ry", "rz", "u", "u1", "u2", "u3", "sx", "sxdg"]
    two_q = ["cx", "cz", "swap", "ecr", "iswap"]
    three_q = ["cswap", "ccx"]
    nm.add_all_qubit_quantum_error(depolarizing_error(0.1 * p, 1), one_q)
    nm.add_all_qubit_quantum_error(depolarizing_error(p, 2), two_q)
    nm.add_all_qubit_quantum_error(depolarizing_error(1.5 * p, 3), three_q)
    return nm


def make_simulator(p_depol, fake_name):
    if fake_name is not None:
        from qiskit_ibm_runtime.fake_provider import FakeProviderForBackendV2
        provider = FakeProviderForBackendV2()
        target = f"fake_{fake_name.lower()}"
        for b in provider.backends():
            if b.name == target:
                return AerSimulator.from_backend(b), b
        avail = sorted(b.name for b in provider.backends() if 'fake_' in b.name)
        raise ValueError(f"FakeBackend '{fake_name}' not found. Sample: {avail[:10]}")
    if p_depol > 0:
        return AerSimulator(noise_model=build_depolarizing_noise(p_depol)), None
    return AerSimulator(), None


_BASIS = ["id", "rz", "sx", "x", "cx", "cz", "ecr"]


def transpile_for(sim, qc, fake_name):
    if fake_name is not None:
        return transpile(qc, backend=sim, optimization_level=1)
    return transpile(qc, basis_gates=_BASIS, optimization_level=1)


# ---------------------------------------------------------------------------
# Observables
# ---------------------------------------------------------------------------
def overlap_from_swap(p_zero):
    """SWAP-test ancilla P(0) -> magnitude of <ref|v_D>."""
    return math.sqrt(max(0.0, 2 * p_zero - 1.0))


def renyi2_entropy_proxy(overlap):
    """For pure states, |<ref|psi>|^2 = purity -> S2 = -log2(purity).
       Renyi-2 entropy of v_D's reduced state, lower bound under noise."""
    p = overlap ** 2
    p = max(min(p, 1.0 - 1e-12), 1e-12)
    return -math.log2(p)


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------
def run_offset_sweep(p_depol=0.0, fake_name=None, shots=4096, n_pairs=3,
                     verbose=False):
    """Average entropy over a small set of (label_M, label_D_ref) pairs at
       each offset. Default n_pairs=3 uses (alpha->alpha, beta->beta,
       gamma->gamma) as the "diagonal" pairs that Paper 34 uses for the
       Z3 read-back."""
    diag_pairs = [(0, 0), (1, 1), (2, 2)][:n_pairs]
    sim, fake_be = make_simulator(p_depol, fake_name)

    entropies = np.zeros(N_OFFSETS)
    for offset in range(N_OFFSETS):
        ent_per_pair = []
        for label_M, label_D in diag_pairs:
            qc = build_obs23_circuit(label_M, label_D, offset)
            tqc = transpile_for(sim, qc, fake_name)
            t0 = time.time()
            counts = sim.run(tqc, shots=shots).result().get_counts()
            zeros = int(counts.get("0", 0))
            p0 = zeros / shots
            ov = overlap_from_swap(p0)
            ent_per_pair.append(renyi2_entropy_proxy(ov))
            if verbose and offset == 0:
                print(f"    pair({label_M},{label_D}) p0={p0:.3f} S2={ent_per_pair[-1]:.3f} dt={time.time()-t0:.1f}s")
        entropies[offset] = float(np.mean(ent_per_pair))
        if verbose:
            print(f"  offset {offset:2d}/{N_OFFSETS}  S2={entropies[offset]:.4f}")
    return entropies


# ---------------------------------------------------------------------------
# Threshold evaluation
# ---------------------------------------------------------------------------
def evaluate_thresholds(entropy_curve):
    n = len(entropy_curve)
    fft = np.fft.rfft(entropy_curve - entropy_curve.mean())
    power = np.abs(fft) ** 2
    total = float(power[1:].sum())

    # 23-C: dominant period
    k_dom = int(np.argmax(power[1:])) + 1
    period_dom = float(n / k_dom)
    pass_C = 11.88 <= period_dom <= 12.12

    # 23-Z: peak-trough offset gap = T_CYCLE/3 +- 1
    peaks_idx = np.argsort(entropy_curve)[-3:]
    troughs_idx = np.argsort(entropy_curve)[:3]
    # Look for the modal gap between any peak-trough pair within one cycle
    gap_candidates = []
    for p in peaks_idx:
        for t in troughs_idx:
            d = abs(int(p) - int(t)) % T_CYCLE
            if d > T_CYCLE / 2:
                d = T_CYCLE - d
            gap_candidates.append(d)
    if gap_candidates:
        gap_mode = float(np.median(gap_candidates))
    else:
        gap_mode = float("nan")
    pass_Z = abs(gap_mode - T_CYCLE / 3) <= 1.0

    # 23-P: peak-trough contrast
    contrast = float(entropy_curve.max() - entropy_curve.min())
    pass_P = contrast >= 0.02

    # 23-H: bichromatic purity on {12, 6}
    if total > 1e-12:
        hit = 0.0
        for k in range(1, len(fft)):
            per = n / k
            if abs(per - 12) < 0.5 or abs(per - 6) < 0.5:
                hit += float(power[k])
        purity = hit / total
    else:
        purity = float("nan")
    pass_H = purity >= 0.90

    # Top FFT bins
    ranked = sorted([(float(power[k]), float(n / k), k)
                     for k in range(1, len(fft))], reverse=True)[:6]

    return {
        "23-C": {"period_dom": period_dom, "pass": bool(pass_C)},
        "23-Z": {"gap_mode": gap_mode, "pass": bool(pass_Z)},
        "23-P": {"contrast": contrast, "pass": bool(pass_P)},
        "23-H": {"purity_12_6": float(purity), "pass": bool(pass_H)},
        "top_fft": [{"power": p, "period": pe, "k": k} for p, pe, k in ranked],
        "non_dc_power": total,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", type=int, default=2048)
    ap.add_argument("--n-pairs", type=int, default=3)
    ap.add_argument("--quick", action="store_true",
                    help="ideal + p=0.005 only, fewer pairs")
    ap.add_argument("--fake", default=None,
                    help="FakeBackend name (e.g. sherbrooke for Eagle r3)")
    ap.add_argument("--out-tag", default=None)
    args = ap.parse_args()

    if args.quick:
        noise_levels = [0.0, 0.005]
        n_pairs = 1
    else:
        noise_levels = [0.0, 0.001, 0.003, 0.005]
        n_pairs = args.n_pairs

    print("=" * 78)
    print("Observable 23 — Pre-hardware noise feasibility (8q proxy)")
    print(f"Sweep: {N_OFFSETS} offsets x {n_pairs} Z3 pairs x {len(noise_levels)} levels"
          + (f" + fake_{args.fake}" if args.fake else ""))
    print(f"Shots: {args.shots} per circuit")
    print("=" * 78)

    runs = {}
    t_total = time.time()

    for p in noise_levels:
        print(f"\n[depol p={p}]")
        t0 = time.time()
        ent = run_offset_sweep(p_depol=p, fake_name=None,
                               shots=args.shots, n_pairs=n_pairs)
        thr = evaluate_thresholds(ent)
        runs[f"depol_{p}"] = {
            "p_depol": p,
            "entropy_curve": ent.tolist(),
            "thresholds": thr,
            "runtime_s": float(time.time() - t0),
        }
        print(f"  runtime {time.time()-t0:.1f}s")
        print(f"  23-C dominant period = {thr['23-C']['period_dom']:.3f}  -> {'PASS' if thr['23-C']['pass'] else 'FAIL'}")
        print(f"  23-Z peak-trough gap = {thr['23-Z']['gap_mode']:.2f}      -> {'PASS' if thr['23-Z']['pass'] else 'FAIL'}")
        print(f"  23-P contrast        = {thr['23-P']['contrast']:.4f}  -> {'PASS' if thr['23-P']['pass'] else 'FAIL'}")
        print(f"  23-H bichromatic     = {thr['23-H']['purity_12_6']*100:.1f}%   -> {'PASS' if thr['23-H']['pass'] else 'FAIL'}")

    if args.fake is not None:
        print(f"\n[fake backend: {args.fake}]")
        t0 = time.time()
        ent = run_offset_sweep(p_depol=0.0, fake_name=args.fake,
                               shots=args.shots, n_pairs=n_pairs)
        thr = evaluate_thresholds(ent)
        runs[f"fake_{args.fake}"] = {
            "fake_backend": args.fake,
            "entropy_curve": ent.tolist(),
            "thresholds": thr,
            "runtime_s": float(time.time() - t0),
        }
        print(f"  runtime {time.time()-t0:.1f}s")
        print(f"  23-C dominant period = {thr['23-C']['period_dom']:.3f}  -> {'PASS' if thr['23-C']['pass'] else 'FAIL'}")
        print(f"  23-Z peak-trough gap = {thr['23-Z']['gap_mode']:.2f}      -> {'PASS' if thr['23-Z']['pass'] else 'FAIL'}")
        print(f"  23-P contrast        = {thr['23-P']['contrast']:.4f}  -> {'PASS' if thr['23-P']['pass'] else 'FAIL'}")
        print(f"  23-H bichromatic     = {thr['23-H']['purity_12_6']*100:.1f}%   -> {'PASS' if thr['23-H']['pass'] else 'FAIL'}")

    print(f"\nTotal runtime: {(time.time()-t_total)/60:.2f} min")

    # Write JSON
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tag = args.out_tag or (args.fake or "depol")
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "stack": "qiskit_aer",
        "qiskit_version": __import__("qiskit").__version__,
        "observable": "23-precursor-8q-proxy",
        "paper": 34,
        "thresholds_pre_registered": {
            "23-C": "dominant FFT period in [11.88, 12.12]",
            "23-Z": "peak-trough offset gap = T_CYCLE/3 +/- 1 step",
            "23-P": "peak-trough Renyi-2 contrast >= 0.02",
            "23-H": "bichromatic purity on {12, 6} >= 0.90",
        },
        "parameters": {
            "T_CYCLE": T_CYCLE,
            "N_OFFSETS": N_OFFSETS,
            "COUPLING": COUPLING,
            "J_INTRA": J_INTRA,
            "J_MEM": J_MEM,
            "shots": args.shots,
            "n_pairs": n_pairs,
            "noise_levels": noise_levels,
            "fake_backend": args.fake,
        },
        "runs": runs,
    }
    out = RESULTS_DIR / f"obs23_p34_aer_{tag}_{datetime.now():%Y%m%dT%H%M%S}.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
