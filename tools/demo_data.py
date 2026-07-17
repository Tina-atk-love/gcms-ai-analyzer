#!/usr/bin/env python3
"""
Demo Data Generator — Realistic GC-MS Flavor Analysis Dataset
===============================================================
Generates a realistic simulated GC-MS dataset for demonstrating the
capabilities of the GC-MS AI Analyzer without requiring real data.

The demo simulates a food flavor comparison experiment:
  - Group A: Roasted coffee beans (6 samples)
  - Group B: Green coffee beans (6 samples)
  - ~45 volatile compounds typically found in coffee aroma
  - Realistic RT, area, match_factor values
  - Designed to showcase: OAV, ROVA, PCA, ANOVA, flavor wheel

Usage:
  from tools.demo_data import generate_demo_dataset
  df = generate_demo_dataset()
"""

import numpy as np
import pandas as pd
from pathlib import Path


# ================================================================
# Realistic Coffee Aroma Compound Database
# ================================================================
# Based on published GC-MS analyses of coffee volatiles
# (Flament, 2002; Czerny et al., 2008; Caporaso et al., 2018)

COFFEE_COMPOUNDS = [
    # (name, formula, rt_min, base_mz, category, odor_descriptor, roast_ratio)
    # roast_ratio: >1 = higher in roasted, <1 = higher in green, ~1 = similar
    ("2-Methylpropanal", "C4H8O", 3.12, 43, "Roasted/Maillard", "malty, chocolate", 3.5),
    ("2-Methylbutanal", "C5H10O", 3.85, 57, "Roasted/Maillard", "malty, cocoa", 4.2),
    ("3-Methylbutanal", "C5H10O", 3.91, 44, "Roasted/Maillard", "malty, ethereal", 3.8),
    ("Hexanal", "C6H12O", 5.23, 56, "Green/Grassy", "grassy, green", 0.3),
    ("2-Heptanone", "C7H14O", 6.15, 43, "Fruity", "fruity, spicy", 1.2),
    ("Heptanal", "C7H14O", 6.89, 70, "Green/Grassy", "green, oily", 0.5),
    ("Methional", "C4H8OS", 7.34, 48, "Sulfurous", "cooked potato", 5.5),
    ("2,3-Butanedione", "C4H6O2", 3.45, 43, "Roasted/Maillard", "buttery, creamy", 2.8),
    ("2,3-Pentanedione", "C5H8O2", 4.21, 43, "Roasted/Maillard", "buttery, sweet", 2.5),
    ("Acetoin", "C4H8O2", 4.56, 45, "Roasted/Maillard", "buttery, cream", 1.8),
    ("Furfural", "C5H4O2", 8.12, 96, "Roasted/Maillard", "bready, almond", 6.0),
    ("5-Methylfurfural", "C6H6O2", 9.45, 110, "Roasted/Maillard", "sweet, caramel", 5.0),
    ("Furfuryl alcohol", "C5H6O2", 9.89, 98, "Roasted/Maillard", "burnt, smoky", 7.0),
    ("2-Acetylfuran", "C6H6O2", 10.12, 95, "Roasted/Maillard", "balsamic, sweet", 4.5),
    ("5-Hydroxymethylfurfural", "C6H6O3", 15.67, 97, "Roasted/Maillard", "caramel, sweet", 3.2),
    ("Pyrazine", "C4H4N2", 4.78, 80, "Roasted/N-heterocyclic", "nutty, roasted", 12.0),
    ("2-Methylpyrazine", "C5H6N2", 5.56, 94, "Roasted/N-heterocyclic", "nutty, roasted", 15.0),
    ("2,3-Dimethylpyrazine", "C6H8N2", 6.34, 108, "Roasted/N-heterocyclic", "nutty, caramel", 14.0),
    ("2,5-Dimethylpyrazine", "C6H8N2", 6.45, 108, "Roasted/N-heterocyclic", "nutty, cocoa", 13.5),
    ("2-Ethylpyrazine", "C6H8N2", 6.78, 107, "Roasted/N-heterocyclic", "nutty, peanut", 10.0),
    ("2-Ethyl-3-methylpyrazine", "C7H10N2", 7.45, 121, "Roasted/N-heterocyclic", "earthy, nutty", 8.0),
    ("2,3,5-Trimethylpyrazine", "C7H10N2", 7.23, 122, "Roasted/N-heterocyclic", "roasted, earthy", 11.0),
    ("2-Acetylpyrazine", "C6H6N2O", 10.34, 94, "Roasted/N-heterocyclic", "popcorn, roasted", 6.0),
    ("Pyridine", "C5H5N", 3.67, 79, "Roasted/N-heterocyclic", "burnt, bitter", 3.0),
    ("2-Methylpyridine", "C6H7N", 4.45, 93, "Roasted/N-heterocyclic", "burnt, astringent", 2.5),
    ("Pyrrole", "C4H5N", 5.12, 67, "Roasted/N-heterocyclic", "nutty, ethereal", 4.0),
    ("2-Acetylpyrrole", "C6H7NO", 11.23, 94, "Roasted/N-heterocyclic", "roasted, nutty", 5.5),
    ("Guaiacol", "C7H8O2", 11.56, 109, "Phenolic", "smoky, phenolic", 8.0),
    ("4-Ethylguaiacol", "C9H12O2", 13.45, 137, "Phenolic", "spicy, clove", 6.0),
    ("4-Vinylguaiacol", "C9H10O2", 14.12, 150, "Phenolic", "clove, spicy", 5.0),
    ("p-Cresol", "C7H8O", 12.34, 107, "Phenolic", "phenolic, smoky", 4.5),
    ("Vanillin", "C8H8O3", 16.23, 151, "Phenolic", "vanilla, sweet", 1.5),
    ("Acetic acid", "C2H4O2", 3.01, 43, "Acidic", "sour, vinegar", 2.0),
    ("Propanoic acid", "C3H6O2", 3.78, 74, "Acidic", "pungent, sour", 1.5),
    ("Butanoic acid", "C4H8O2", 4.56, 60, "Acidic", "rancid, cheese", 1.3),
    ("3-Methylbutanoic acid", "C5H10O2", 5.67, 60, "Acidic", "sweaty, cheese", 1.8),
    ("Hexanoic acid", "C6H12O2", 8.90, 60, "Acidic", "sweaty, pungent", 1.0),
    ("Linalool", "C10H18O", 12.78, 71, "Terpenoid", "floral, citrus", 0.4),
    ("Limonene", "C10H16", 10.56, 68, "Terpenoid", "citrus, fresh", 0.3),
    ("beta-Caryophyllene", "C15H24", 18.23, 69, "Terpenoid", "woody, spicy", 0.6),
    ("2-Furanmethanethiol", "C5H6OS", 10.89, 81, "Sulfurous", "roasted coffee", 20.0),
    ("Dimethyl trisulfide", "C2H6S3", 9.34, 126, "Sulfurous", "sulfurous, cabbage", 8.0),
    ("Dimethyl disulfide", "C2H6S2", 4.12, 94, "Sulfurous", "sulfurous, onion", 3.0),
    ("Methanethiol", "CH4S", 1.56, 47, "Sulfurous", "sulfurous, gas", 2.5),
    ("2-Methylthiophene", "C5H6S", 7.89, 97, "Sulfurous", "sulfurous, gasoline", 4.0),
]


def generate_demo_dataset(n_samples_per_group=6, seed=42):
    """Generate a realistic GC-MS flavor analysis demo dataset.

    Simulates a coffee roasting experiment:
      Group A: Roasted beans (high Maillard compounds)
      Group B: Green beans (high terpenoid/green compounds)

    Returns:
        pandas DataFrame with columns:
            sample, compound, rt, area, match_factor, group, formula,
            category, odor_descriptor
    """
    rng = np.random.default_rng(seed)
    rows = []

    # Generate roasted samples
    for s in range(n_samples_per_group):
        sample_id = f"Roasted-{s+1:02d}"
        for comp in COFFEE_COMPOUNDS:
            name, formula, rt, base_mz, category, odor, roast_ratio = comp

            # RT with small between-sample variation
            rt_actual = rt + rng.normal(0, 0.02)

            # Area: base on roast_ratio with biological variation
            if roast_ratio >= 1.0:
                # Higher in roasted
                base_area = 50000 * roast_ratio + rng.normal(0, 5000)
            else:
                # Higher in green
                base_area = 50000 / roast_ratio + rng.normal(0, 5000)

            area = max(1000, int(base_area * rng.lognormal(0, 0.3)))

            # Match factor: simulated NIST library match quality
            match = int(min(950, max(500, 750 + rng.normal(0, 80))))

            # Concentration (semi-quantitative, µg/kg equivalent)
            conc = area * 0.001 * rng.lognormal(0, 0.2)

            rows.append({
                'sample': sample_id,
                'compound': name,
                'rt': round(rt_actual, 3),
                'area': area,
                'match_factor': match,
                'group': 'Roasted',
                'formula': formula,
                'category': category,
                'odor': odor,
                'conc_ug_kg': round(conc, 2),
                'base_mz': base_mz,
            })

    # Generate green bean samples
    for s in range(n_samples_per_group):
        sample_id = f"Green-{s+1:02d}"
        for comp in COFFEE_COMPOUNDS:
            name, formula, rt, base_mz, category, odor, roast_ratio = comp

            rt_actual = rt + rng.normal(0, 0.02)

            # Green beans: inverse the roast_ratio effect
            if roast_ratio >= 1.0:
                base_area = 50000 / roast_ratio + rng.normal(0, 5000)
            else:
                base_area = 50000 * (1 / roast_ratio) + rng.normal(0, 5000)

            area = max(1000, int(base_area * rng.lognormal(0, 0.3)))
            match = int(min(950, max(500, 750 + rng.normal(0, 80))))
            conc = area * 0.001 * rng.lognormal(0, 0.2)

            rows.append({
                'sample': sample_id,
                'compound': name,
                'rt': round(rt_actual, 3),
                'area': area,
                'match_factor': match,
                'group': 'Green',
                'formula': formula,
                'category': category,
                'odor': odor,
                'conc_ug_kg': round(conc, 2),
                'base_mz': base_mz,
            })

    df = pd.DataFrame(rows)
    return df


def get_demo_tic(t_points=800, rt_range=(1.5, 20.0)):
    """Generate a realistic TIC chromatogram for the demo."""
    rng = np.random.default_rng(42)
    t = np.linspace(rt_range[0], rt_range[1], t_points)
    tic = np.zeros(t_points)
    noise = rng.normal(0, 500, t_points)

    for comp in COFFEE_COMPOUNDS:
        _, _, rt, _, _, _, _ = comp
        peak_width = 0.04 + (rt - rt_range[0]) / (rt_range[1] - rt_range[0]) * 0.15
        peak = 50000 * np.exp(-((t - rt) / peak_width) ** 2)
        tic += peak

    tic += noise
    tic = np.maximum(tic, 100)
    return t, tic


def get_demo_peaks():
    """Get peak list for demo TIC annotation."""
    peaks = []
    for comp in COFFEE_COMPOUNDS:
        name, formula, rt, _, category, _, _ = comp
        peaks.append({
            'rt': rt,
            'height': 50000,
            'snr': 50,
            'compound': name,
            'category': category,
        })
    return peaks


if __name__ == '__main__':
    df = generate_demo_dataset()
    print(f"Demo dataset: {len(df)} rows, {df['compound'].nunique()} compounds, "
          f"{df['sample'].nunique()} samples, {df['group'].nunique()} groups")
    print(f"\nSample peaks:")
    print(df.groupby('compound')['area'].mean().sort_values(ascending=False).head(10))
    print(f"\nCompound categories: {df['category'].unique().tolist()}")
