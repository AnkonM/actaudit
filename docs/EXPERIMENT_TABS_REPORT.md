# ActAudit experiment tabs: hand-off report

Branch: `feature/experiment-tabs`, created from `main` at `4490dc6e11f74449cb9c7628a9ae98ebb30191f6` (recorded before any work; `main` must still equal this at hand-off). Spec: blueprint Section 15. Phases are numbered 9–16, continuing the blueprint roadmap.

## Progress log

Resume from this log and the blueprint alone. Each phase ends with one commit and a push of `feature/experiment-tabs` (never `main`).

| Phase | Status | Commit | Notes |
|---|---|---|---|
| 9 — Branch setup + blueprint | done | 227c1c7 | §5 schema v2 rows, §6.2 Rule 0 note, §11 tree, §12 Phases 9–16, §14 decision log, §15 spec; this report. History scanned for keys: clean. Baseline suite: 174 passed, 1 skipped. |
| 10 — Schema v2, Rule 0, trace, fixture compat; recording (1) | done | 625be6a | 213 passed, 1 skipped. Art. 2(3), 3(60), 10, 14, 15, 27, 50, 113 verified against the OJ text (CELLAR). Recording (1) partial: 4 of 7 quick-picks on v2 (tiers unchanged). |
| 11 — UI restructure + Tab 1 | done | (this commit) | 242 passed, 1 skipped. Eight lazy tabs with verbatim captions; Tab 1 migrated + ethical analysis; tab_grouping re-recorded. Quota exhausted (429 on all models). |
| 12 — Tabs 2, 4, 5 + datasets | next | | |
| 13 — Tabs 3, 6, 7A; recording (2) | pending | | |
| 14 — Tab 8; recording (3) | pending | | |
| 15 — Robustness study + Tab 7B; recording (4) | pending | | |
| 16 — Final verification + hand-off | pending | | |

**Pending recording:** (1) quick-picks CheXNet, military_target_recognition (overload, then daily quota); (2) synthetic-media examples; (3) Case Library; (4) robustness study. Single command: `python scripts/record_all.py`.

## Decision log

See blueprint §14, "Experiment tabs: autonomous decisions" (copied here at hand-off).
