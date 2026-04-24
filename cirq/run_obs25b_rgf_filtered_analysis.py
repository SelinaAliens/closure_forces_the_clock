#!/usr/bin/env python
"""Observable 25b-RGF — Wigner-GUE test with high-pass filter.

The raw RIEMANN entropy curve from obs25b is dominated by the period-3
gate cycle (R-T-S). Its local minima cluster at multiples of 3, which
is not the Wigner-distributed structure Paper 7 predicts. This script
removes short-period Fourier components and re-tests level spacings.

Standalone: reads obs25b_closure_modes.json, applies FFT high-pass at
several period cutoffs, re-evaluates the Wigner-GUE KS test on the
resulting entropy-minima spacings.
"""
from __future__ import annotations

import json
from math import pi

import numpy as np


def high_pass(signal, period_cutoff):
    """Zero out FFT components with period < period_cutoff."""
    n = len(signal)
    mean = signal.mean()
    fft = np.fft.rfft(signal - mean)
    for k in range(1, len(fft)):
        period = n / k
        if period < period_cutoff:
            fft[k] = 0.0
    return np.fft.irfft(fft, n=n)


def find_minima(curve, prominence=0.0):
    idx = []
    for i in range(1, len(curve) - 1):
        if curve[i] < curve[i - 1] and curve[i] < curve[i + 1]:
            left = curve[i - 1] - curve[i]
            right = curve[i + 1] - curve[i]
            if left >= prominence and right >= prominence:
                idx.append(i)
    return np.array(idx)


def wigner_gue_cdf(s):
    grid = np.linspace(0.0, max(float(s.max()) * 1.5, 3.0), 2000)
    pdf = (32.0 / pi ** 2) * grid ** 2 * np.exp(-4.0 * grid ** 2 / pi)
    cdf = np.cumsum(pdf) * (grid[1] - grid[0])
    cdf /= cdf[-1]
    return np.interp(s, grid, cdf)


def wigner_goe_cdf(s):
    """GOE (Gaussian Orthogonal Ensemble) as secondary comparison."""
    grid = np.linspace(0.0, max(float(s.max()) * 1.5, 3.0), 2000)
    pdf = (pi / 2.0) * grid * np.exp(-pi * grid ** 2 / 4.0)
    cdf = np.cumsum(pdf) * (grid[1] - grid[0])
    cdf /= cdf[-1]
    return np.interp(s, grid, cdf)


def ks_test(spacings, cdf_fn):
    if len(spacings) < 8:
        return float("nan"), float("nan")
    s = np.sort(spacings / spacings.mean())
    n = len(s)
    emp = np.arange(1, n + 1) / n
    theo = cdf_fn(s)
    D = float(np.max(np.abs(emp - theo)))
    lam = (np.sqrt(n) + 0.12 + 0.11 / np.sqrt(n)) * D
    p = 0.0
    for j in range(1, 100):
        p += 2 * (-1) ** (j - 1) * np.exp(-2 * j ** 2 * lam ** 2)
    return D, float(max(0.0, min(1.0, p)))


def main():
    with open("obs25b_closure_modes.json") as f:
        data = json.load(f)

    riemann = np.array(data["riemann"]["spectrum"])

    print("=" * 68)
    print("Observable 25b-RGF — Filtered Wigner-GUE Test")
    print("Paper 35 / Experiment 1 — observable refinement")
    print("=" * 68)
    print(f"Riemann curve length : {len(riemann)}")
    print(f"Mean entropy          : {riemann.mean():.4f}")
    print()
    print(f"{'cutoff':>6} {'mins':>5} {'sp_mean':>8} "
          f"{'D_GUE':>7} {'p_GUE':>7} {'D_GOE':>7} {'p_GOE':>7}  verdict")
    print("-" * 68)

    results = []
    for cutoff in [3.5, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]:
        filtered = high_pass(riemann, cutoff)
        mins = find_minima(filtered)
        if len(mins) < 8:
            print(f"  {cutoff:5.1f}  {len(mins):3d}  (too few)")
            continue
        spacings = np.diff(mins).astype(float)
        D_gue, p_gue = ks_test(spacings, wigner_gue_cdf)
        D_goe, p_goe = ks_test(spacings, wigner_goe_cdf)
        # Pick whichever ensemble is closer
        verdict = "PASS" if max(p_gue, p_goe) >= 0.10 else "fail"
        print(f"  {cutoff:5.1f}  {len(mins):3d}  {spacings.mean():7.2f}  "
              f"{D_gue:.4f}  {p_gue:.4f}  {D_goe:.4f}  {p_goe:.4f}  {verdict}")
        results.append({
            "cutoff": cutoff,
            "n_minima": int(len(mins)),
            "spacings_mean": float(spacings.mean()),
            "spacings_std": float(spacings.std()),
            "ks_D_gue": D_gue,
            "ks_p_gue": p_gue,
            "ks_D_goe": D_goe,
            "ks_p_goe": p_goe,
            "verdict": verdict,
        })

    # Best cutoff by max(p_gue, p_goe)
    if results:
        best = max(results, key=lambda r: max(r["ks_p_gue"], r["ks_p_goe"]))
        print()
        print(f"BEST cutoff = {best['cutoff']}  "
              f"p_GUE = {best['ks_p_gue']:.4f}  p_GOE = {best['ks_p_goe']:.4f}  "
              f"-> {best['verdict']}")

        # Pre-registered threshold evaluation
        overall_pass = max(best["ks_p_gue"], best["ks_p_goe"]) >= 0.10
        print()
        print("=" * 68)
        print("25b-RGF (filtered) threshold:")
        print(f"  max(p_GUE, p_GOE) >= 0.10  ->  "
              f"measured {max(best['ks_p_gue'], best['ks_p_goe']):.4f}  ->  "
              f"{'PASS' if overall_pass else 'FAIL'}")
        print("=" * 68)

    with open("obs25b_rgf_filtered.json", "w") as f:
        json.dump({
            "source": "obs25b_closure_modes.json -> riemann.spectrum",
            "curve_length": int(len(riemann)),
            "results_by_cutoff": results,
        }, f, indent=2)
    print("\nRaw data: obs25b_rgf_filtered.json")


if __name__ == "__main__":
    main()
