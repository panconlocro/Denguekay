#!/usr/bin/env python3
"""Rebuild the primary Brier comparison and the seasonal supplement."""
import argparse
import csv
import gzip
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date
from itertools import product
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent
ARMS = ('b3', 'history_geography', 'probabilistic_persistence')


def load_scores(manifest):
    entry = manifest['input']
    path = ROOT / entry['file']
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Prediction archive SHA-256 mismatch')
    seeds = manifest['seeds']
    groups = defaultdict(list)
    counts = Counter()
    events = Counter()
    seen = set()
    districts = set()
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            season = int(row['season'])
            horizon = int(row['horizon'])
            district = row['district']
            target = date.fromisoformat(row['target_week'])
            origin = date.fromisoformat(row['origin_close'])
            label = int(row['elevated_week'])
            key = (horizon, district, target)
            if (
                key in seen or not re.fullmatch(r'20\d{4}', district)
                or label not in (0, 1) or (target - origin).days != 7 * horizon - 6
                or origin.weekday() != 5 or target.weekday() != 6
            ):
                raise ValueError(f'Invalid or duplicate forecast row: {key}')
            seen.add(key)
            districts.add(district)
            counts[horizon] += 1
            events[horizon] += label
            persistence = float(row['probabilistic_persistence'])
            for seed in seeds:
                predictions = (float(row[f'b3_s{seed}']), float(row[f'history_geography_s{seed}']), persistence)
                if not all(0 <= value <= 1 for value in predictions):
                    raise ValueError(f'Invalid probability: {key}, seed {seed}')
                groups[season, horizon, seed].append(tuple((value - label) ** 2 for value in predictions))
    if (
        len(seen) != entry['rows'] or len(districts) != 65
        or dict(counts) != {h: 20410 for h in manifest['horizons']}
        or dict(events) != {h: 2632 for h in manifest['horizons']}
        or set(groups) != set(product(manifest['seasons'], manifest['horizons'], seeds))
    ):
        raise ValueError('Unexpected retrospective evaluation support')
    return {key: tuple(mean(losses) for losses in zip(*rows)) for key, rows in groups.items()}


def percentile(sorted_values, probability):
    position = (len(sorted_values) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def interval(values):
    samples = sorted(mean(sample) for sample in product(values, repeat=len(values)))
    return [percentile(samples, p) for p in (0.025, 0.975)]


def summarize(scores, manifest):
    records = []
    for horizon in manifest['horizons']:
        seasons = []
        for season in manifest['seasons']:
            pairs = [scores[season, horizon, seed] for seed in manifest['seeds']]
            geo_delta = [100 * (b3 / geo - 1) for b3, geo, _ in pairs]
            pp_skill = [100 * (1 - b3 / pp) for b3, _, pp in pairs]
            seasons.append({
                'season': season, 'horizon': horizon,
                **dict(zip(ARMS, map(median, zip(*pairs)))),
                'climate_change_pct': median(geo_delta), 'persistence_skill_pct': median(pp_skill),
            })
        changes = [s['climate_change_pct'] for s in seasons]
        skills = [s['persistence_skill_pct'] for s in seasons]
        records.append({
            'horizon': horizon,
            **{arm: mean(s[arm] for s in seasons) for arm in ARMS},
            'climate_change_pct': mean(changes), 'climate_ci_pct': interval(changes),
            'persistence_skill_pct': mean(skills), 'persistence_ci_pct': interval(skills),
            'climate_change_without_2026_pct': mean(s['climate_change_pct'] for s in seasons if s['season'] != 2026),
            'seasons': seasons,
        })
    return records


def main_table_row(record):
    def cell(value, bounds):
        return f'\u0024{value:+.2f}\u0024 ([{bounds[0]:+.2f}, {bounds[1]:+.2f}])'

    return ' & '.join((
        f"{record['horizon']} wk", *(f'{record[arm]:.5f}' for arm in ARMS),
        cell(record['climate_change_pct'], record['climate_ci_pct']),
        cell(record['persistence_skill_pct'], record['persistence_ci_pct']),
    )) + r'\\'


def seasonal_rows(results, seasons):
    by_horizon = [{row['season']: row for row in record['seasons']} for record in results]
    for season in seasons:
        cells = (f'\u0024{item[season][key]:+.2f}\u0024' for key in ('climate_change_pct', 'persistence_skill_pct')
                 for item in by_horizon)
        yield ' & '.join((str(season), *cells)) + r'\\'


def verify_tex(path, rows, table):
    source = path.read_text(encoding='utf-8').splitlines()
    if any(row not in source for row in rows):
        raise SystemExit(f'{table} differs from the rows in {path}')
    print(f'{table} matches {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('reproduced'))
    parser.add_argument('--main-tex', type=Path, help='Verify the Table II rows in the paper source')
    parser.add_argument('--supplement-tex', type=Path, help='Verify the Table S16 rows in the supplement source')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    results = summarize(load_scores(manifest), manifest)
    primary = [main_table_row(row) for row in results]
    seasonal = list(seasonal_rows(results, manifest['seasons']))
    if args.main_tex:
        verify_tex(args.main_tex, primary, 'Table II')
        text = args.main_tex.read_text(encoding='utf-8')
        expected = f"+{results[-1]['climate_change_without_2026_pct']:.2f}\\%"
        if expected not in text:
            raise SystemExit('The h4 sensitivity excluding 2026 differs from the paper')
    if args.supplement_tex:
        verify_tex(args.supplement_tex, seasonal, 'Table S16')
    args.out.mkdir(parents=True, exist_ok=True)
    for filename, rows in [('table_ii_rows.tex', primary), ('table_s16_rows.tex', seasonal)]:
        (args.out / filename).write_text('\n'.join(rows) + '\n', encoding='utf-8')
    (args.out / 'metrics.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(f'Rebuilt both tables in {args.out}')


if __name__ == '__main__':
    main()
