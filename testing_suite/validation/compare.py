"""
Compare each panel scenario's ACTUAL model output against the EXPECTED output
computed independently by panel_expected (the calc-sheet logic).

Inputs and actual outputs both come from each scenario folder's
P1_all_parameters.CSV — the CSV is the current export; the sibling .json is
STALE and must not be used. The ValidationOutputs sheet is likewise not used
(out of date). Expected is recomputed from the inputs the model actually
received, so a mismatch means the model's derivation disagrees with the spec.
"""
import csv
import glob
import os

import panel_expected as pe

SCEN_DIR = os.environ.get(
    'PANEL_SCENARIOS_DIR',
    r'C:\Users\james.derrod\VM Fusion Extension\Panel Scenarios')

FLOAT_TOL = 1e-4


def _approx(a, b):
    if pe._blank(a) and pe._blank(b):
        return True
    if pe._blank(a) != pe._blank(b):
        return False
    try:
        return abs(float(a) - float(b)) <= FLOAT_TOL
    except (TypeError, ValueError):
        return pe._seq(a, b)


def _parse_value(raw):
    """CSV Value cell -> number when numeric, else the (quote-preserving) string.
    Downstream _unquote/_seq handle the quoted text params ('WHOLE', 'B-386')."""
    if raw is None:
        return None
    s = raw.strip()
    if s == '':
        return None
    try:
        return float(s)
    except ValueError:
        return s  # text like "'WHOLE'" or an expression string


def extract_params(csv_path):
    """Return (inputs, actual) dicts from a P1_all_parameters.csv.

    CSV columns: Type, Parameter Name, Value, Unit, Expression, Comment.
    Multi-line quoted Comment fields are handled by csv.reader.
    """
    allv = {}
    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) < 3:
                continue
            name = row[1].strip()
            if not name:
                continue
            allv[name] = _parse_value(row[2])
    inputs = {k: allv.get(k) for k in pe.INPUT_PARAMS}
    return inputs, allv


def compare_scenario(inputs, actual):
    """Return a list of per-param comparison rows.

    status:
      match    - expected number equals actual
      mismatch - expected and actual disagree
      empty    - no cutout expected and model reports 0/blank (consistent)
      na       - helper value not exported as a model parameter
    """
    expected = pe.compute_expected(inputs)
    rows = []
    for p in pe.DERIVED_PARAMS:
        exp = expected[p]
        act = actual.get(p, None)
        if p in pe.HELPER_PARAMS:
            status = 'na'
        elif pe._blank(exp):
            status = 'empty' if (pe._blank(act) or pe._num(act) == 0.0) else 'mismatch'
        else:
            if pe._blank(act):
                status = 'mismatch'
            else:
                status = 'match' if _approx(exp, act) else 'mismatch'
        rows.append({'param': p, 'expected': exp, 'actual': act,
                     'status': status, 'kind': 'derived'})
    # Fixed constants: the model value should equal the spec constant.
    for p, exp in pe.FIXED_CONSTANTS.items():
        act = actual.get(p, None)
        if act is None:
            status = 'na'
        else:
            status = 'match' if _approx(exp, act) else 'mismatch'
        rows.append({'param': p, 'expected': exp, 'actual': act,
                     'status': status, 'kind': 'constant'})
    return expected, rows


def scan(scen_dir=SCEN_DIR):
    results = []
    folders = sorted(glob.glob(os.path.join(scen_dir, 'XX8X_PV_*')))
    for folder in folders:
        cpath = os.path.join(folder, 'P1_all_parameters.csv')
        if not os.path.exists(cpath):
            continue
        scenario = os.path.basename(folder).split(' ')[0]
        try:
            inputs, actual = extract_params(cpath)
        except Exception as e:
            results.append({'scenario': scenario, 'folder': os.path.basename(folder),
                            'error': str(e), 'rows': [], 'inputs': {}})
            continue
        expected, rows = compare_scenario(inputs, actual)
        counts = {'match': 0, 'mismatch': 0, 'empty': 0, 'na': 0}
        for r in rows:
            counts[r['status']] += 1
        results.append({
            'scenario': scenario,
            'folder': os.path.basename(folder),
            'inputs': inputs,
            'expected': expected,
            'rows': rows,
            'counts': counts,
            'ok': counts['mismatch'] == 0,
        })
    return results


if __name__ == '__main__':
    res = scan()
    total = len(res)
    passed = sum(1 for r in res if r.get('ok'))
    mism = [r for r in res if not r.get('ok')]
    print(f'Scenarios: {total} | pass: {passed} | with mismatches: {len(mism)}')
    # aggregate which params mismatch most
    from collections import Counter
    pc = Counter()
    for r in mism:
        for row in r['rows']:
            if row['status'] == 'mismatch':
                pc[row['param']] += 1
    print('\nMost-mismatching params:')
    for p, n in pc.most_common():
        print(f'  {n:4d}  {p}')
    print('\nFirst 15 scenarios with mismatches:')
    for r in mism[:15]:
        bad = [f"{row['param']}(exp={row['expected']},act={row['actual']})"
               for row in r['rows'] if row['status'] == 'mismatch']
        print(f"  {r['scenario']}: " + '; '.join(bad))
