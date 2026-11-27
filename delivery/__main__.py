"""Pulumi Delivery pipeline for pulumi-events.

Pulumi Cloud runs this release pipeline on every push to the branch that touches
the app or infra: a ``verify`` stage (lint and tests), then a ``deploy`` stage that
runs ``pulumi up`` on the existing ``pulumi-events-infra`` stack. Nothing runs from
a developer machine. The stack itself must already exist (Delivery does not create
stacks); its AWS and app credentials come from the ESC environments imported in
``deploy/Pulumi.dev.yaml``.

Pulumi Delivery is in public preview; the SDK may change.
"""

from __future__ import annotations

import pulumi
import pulumi_delivery as delivery

config = pulumi.Config()
project = config.get("targetProject") or "pulumi-events-infra"
stack = config.get("targetStack") or "dev"
repository = config.get("githubRepository") or "dirien/pulumi-events"
branch = config.get("branch") or "main"
infra_dir = config.get("infraDir") or "deploy"

# Only changes to the app, the image inputs, the infra program or this pipeline start a run.
source = delivery.GitHubSource(
    "repo",
    repository=repository,
    branch=branch,
    trigger={
        "paths": [
            "src/**",
            "tests/**",
            "Dockerfile",
            "pyproject.toml",
            "uv.lock",
            ".python-version",
            "README.md",
            f"{infra_dir}/**",
            "delivery/**",
        ]
    },
)

pipeline = delivery.Pipeline("pulumi-events")

# Stage 1: static checks and tests.
verify = delivery.Stage("verify", pipeline=pipeline)
delivery.Job(
    "lint-and-test",
    stage=verify,
    source=source,
    directory=".",
    pre_run_commands=["command -v uv >/dev/null 2>&1 || pip install --quiet uv"],
    command=(
        "uv sync --frozen && uv run ruff check src/ tests/ "
        "&& uv run ruff format --check src/ tests/ && uv run pytest -q"
    ),
)

# Stage 2: pulumi up on the app stack. The program builds the image with EC2 Image
# Builder inside AWS, so the runner needs no Docker daemon.
deploy = delivery.Stage("deploy", pipeline=pipeline, from_=[verify])
delivery.Stacks(
    "deploy",
    stage=deploy,
    stacks={
        "app": {
            "stack": f"{project}/{stack}",
            "source": source,
            "directory": infra_dir,
            # Target program uses `toolchain: uv`.
            "pre_run_commands": ["command -v uv >/dev/null 2>&1 || pip install --quiet uv"],
        },
    },
)

# To add a prod stack later: a third Stage with from_=[deploy] and
# when=delivery.RuleArgs(kind="manual", description="..."), plus another Stacks.
