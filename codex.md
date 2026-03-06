# codex.md

This repository mixes software engineering and optimization research.

When solving tasks:

- identify whether the task is software or optimization
- follow the corresponding workflow in `docs/workflow/`
- keep diffs minimal and aligned with existing patterns
- record key assumptions and decisions in `docs/decisions.md`
- after completion, output a Template Patch and append it to `docs/workflow.md`
- submit official experiments through HPC instead of running them on the login node
- assume `max_trips_per_vehicle=2` by default unless the experiment definition overrides it
- clean up failed experiment outputs immediately
