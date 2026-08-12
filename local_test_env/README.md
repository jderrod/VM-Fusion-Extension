# Local test environment

Self-contained sandbox that mirrors the production layout. Nothing in here
touches `\\ddc-mefs`. Created 2026-08-05.

## Toggling local vs. remote

One field controls every path — `run_mode` in `autostart_config.json` at the
add-in root:

| `run_mode` | Dropbox watched | Outputs land in |
|---|---|---|
| `LOCAL` | `local_test_env\order_dropbox` | `local_test_env\...` (this tree) |
| `VM`    | `\\ddc-mefs\iBob-Export\S2S_Export` | `\\ddc-mefs\Fusion\Fusion Folders\...` plus the Gannomat / Anderson / Voorwood shares |

That one field is read by both the toolbar button and the Fusion-startup
auto-start, so there is nothing else to change. To relocate this sandbox,
edit `local_base` in `local_config.json` (or set the `FUSION_PIPELINE_LOCAL_BASE`
environment variable, which wins over the file). Missing subfolders are
recreated automatically on start.

## Layout

```
order_dropbox/      <- DROP ORDER JSON HERE (the S2S_Export equivalent)
order_processing/      in-flight orders move here
order_completed/       finished orders
order_failed/          failed orders
input/{door,panel,stile}
output/
  models/              STEP exports
  gcode/               per-order .nc / .txt
  parameters/          parameter + cutlist CSVs
  logs/                folder_monitor + per-order logs
  dashboard/           pipeline_status.json, order_ledger.jsonl, current_progress.json
machine_drops/         flat drops that go to separate shares in VM mode
  gannomat/            drilling JSON   (VM: \\ddc-mefs\Gannomat\F360_output)
  anderson/            G-code files    (VM: \\ddc-mefs\Anderson)
  voorwood/            cutlist CSVs    (VM: \\ddc-mefs\Voorwood)
sample_orders/         staging area - NOT watched. Copy from here into
                       order_dropbox to kick off a run.
```

`machine_drops/` matters: before this change the three flat copies were
skipped entirely in LOCAL mode, so a local run never exercised that code.
They now always run, writing here instead of to the shares.

## Running a local test

1. Confirm `autostart_config.json` has `"run_mode": "LOCAL"`.
2. Start Fusion, click **Specs to Machine** (with `enabled:false` it will not
   auto-start, so the button is the trigger).
3. Copy an order JSON from `sample_orders/` into `order_dropbox/`.
4. Watch `output/logs/` and the dashboard.

Dashboard against this sandbox:

```
dashboard\start_dashboard_local.bat
```

then open <http://localhost:8765>. Add `--no-actions` if you want it
view-only (that also disables the crash-recovery relaunch loop).

## Note on Fusion models

Model selection is separate from paths — it comes from `drawing_config.json`,
which still points at the real Bobrick cloud project. A local run therefore
still opens and modifies real cloud models. This sandbox isolates the
*filesystem outputs*, not the Fusion cloud data.
