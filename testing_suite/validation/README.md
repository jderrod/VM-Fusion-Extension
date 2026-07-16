# Panel Validation Dashboard

Compares each panel scenario's **actual** model output against an **expected**
output computed independently from the scenario's inputs, and renders the
comparison as a self-contained HTML dashboard.

## How expected is computed

`panel_expected.py` re-implements the derived-parameter formulas from the
**Panel Calculated Values** sheet of
`../Panel inputs & outputs v22 macro_enabled ....xlsm` (verified to reproduce
that sheet's own cached values). The **ValidationOutputs** sheet is deliberately
**not** used — it is out of date. Expected is recomputed from the inputs the
model actually received, so a mismatch means the model's derivation disagrees
with the spec logic (not just that a stored table is stale).

Notes baked into the engine:
- Fusion stores text params wrapped in literal quotes (`'TOP'`, `'B-386'`) — the
  engine strips them.
- Excel semantics are replicated: case-insensitive string compare; a blank cell
  is 0 in a numeric compare but `""` in a text compare.
- The sheet's `cutout_B_*` formulas are a copy/paste bug (they read `cutout_A`
  and swap x/y/width). The engine computes the **intended** logic instead
  (mirror `cutout_A` keyed on the `cutout_B` code).

## Data sources

- Inputs **and** actual outputs come from each
  `Panel Scenarios/<scenario>/P1_all_parameters.CSV`. The sibling `.json` is
  **stale** — do not use it.
- Point elsewhere with the `PANEL_SCENARIOS_DIR` env var.

## What gets checked

Per scenario (~41 params): all 14 derived-model outputs (expected vs actual),
plus the 25 fixed constants (model value vs spec constant, to catch drift). The
2 helper values (`front/back_notching_activation_offset`) aren't model outputs →
shown as n/a. As of the last run: **109/109 scenarios pass.**

## Usage

```
python gen_dashboard.py                 # writes validation_dashboard.html
python compare.py                       # prints a text summary to the console
```

Open `validation_dashboard.html` in any browser — no server required. Re-run
`gen_dashboard.py` after new scenarios are processed to refresh it.

## Files

- `panel_expected.py` — the expected-output engine (calc-sheet logic)
- `compare.py` — per-scenario expected-vs-actual comparison
- `gen_dashboard.py` — builds the HTML dashboard
- `validation_dashboard.html` — generated report
