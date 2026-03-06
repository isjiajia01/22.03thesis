# MVT Audit Toolkit

This toolkit builds and runs a **Minimal Verifiable Test (MVT)** suite for the rolling-horizon dispatch + VRP + risk/compute gating pipeline.

## One-Command Run

From repository root:

```bash
bash make_mvt.sh
```

This command will:

1. Generate synthetic MVT datasets and case configs.
2. Run all MVT cases and write artifacts to `data/results/MVT/...`.
3. Audit all runs and write traffic-light and counterexample outputs to `data/audits/`.
4. Run trust spot-checks (`A4_REAL`, arrival-cumul source, `EXP04 Seed_1` large-scale).

## Core Outputs

- `data/audits/mvt_index_<timestamp>.csv`
- `data/audits/mvt_report_<timestamp>.md`
- `data/audits/mvt_traffic_light_<timestamp>.csv`
- `data/audits/mvt_failure_minimal_counterexamples_<timestamp>.txt`
- `data/audits/mvt_one_page_summary_<timestamp>.md`
- `data/audits/mvt_policy_sanity_12day_<timestamp>.csv`
- `data/audits/mvt_spotcheck_report_<timestamp>.md`
- `data/audits/mvt_spotcheck_traffic_light_<timestamp>.csv`
- `data/audits/mvt_spotcheck_counterexamples_<timestamp>.txt`

## Traffic-Light Interpretation

In `mvt_traffic_light_<timestamp>.csv`, each row is one check on one run:

- `PASS`: Check condition satisfied.
- `FAIL`: Check condition violated; inspect `minimal_counterexample` and `evidence_path`.

The minimum reproducible evidence is always provided as:

- `case_name`
- `seed`
- `run_serial`
- `check_name`
- `minimal_counterexample`
- `evidence_path`

## Important VRP Constraint Audit Note

VRP time-window and capacity checks rely on route instrumentation exported in solver output (`stop_details`, `route_load`, `vehicle_capacity`) and then persisted into `simulation_results.json` under `vrp_audit_traces`.

This instrumentation does **not** change solver logic; it only exposes auditable state.
