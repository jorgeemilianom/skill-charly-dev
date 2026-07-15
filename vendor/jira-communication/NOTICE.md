Vendored subset of the `jira-communication` skill's CLI scripts.

- Source: https://github.com/netresearch/jira-skill
- Version: 3.20.0
- Copyright (c) 2025 Netresearch DTT GmbH
- License: see `LICENSE-MIT` and `LICENSE-CC-BY-SA-4.0` in this directory

Only `scripts/` is vendored here (the CLI tools the `dev-*` skills call via `uv run`). The
documentation, references, and evals from the original skill are not included — see the source
repository for those.

To update: re-clone the source repo at a newer tag and replace `scripts/` here.
