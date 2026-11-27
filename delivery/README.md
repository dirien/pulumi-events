# delivery

A [Pulumi Delivery](https://www.pulumi.com/docs/delivery/) pipeline (public preview) that deploys the
app stack in `../deploy` (`pulumi-events-infra`) from Pulumi Cloud instead of a local machine.
It declares one pipeline, no cloud resources of its own.

| Stage | What runs | Gate |
|---|---|---|
| `verify` | `Job`: `uv sync`, ruff check/format check, pytest | none |
| `deploy` | `Stacks`: `pulumi up` on `pulumi-events-infra/dev`, `deploy/` directory | after `verify` succeeds |

Trigger: a push to `main` that changes `src/**`, `tests/**`, `Dockerfile`, `pyproject.toml`, `uv.lock`,
`.python-version`, `README.md`, `deploy/**` or `delivery/**`. Override repo, branch, stack and paths with
`pulumi config set` (see `Pulumi.yaml`) or edit `__main__.py`. For a prod stack, add a `Stage` with
`when=delivery.RuleArgs(kind="manual", ...)`.

## How the image gets built

No Docker daemon is needed on the runner. `deploy/__main__.py` builds the container with EC2 Image Builder:

1. Source files (`src/`, `pyproject.toml`, `uv.lock`, `.python-version`, `README.md`) are zipped into an S3 object.
2. An Image Builder component downloads the zip into a `python:3.12-slim-bookworm` parent image and runs the same
   `uv sync --frozen --no-dev` steps as the root `Dockerfile` (that file stays the reference for local builds;
   keep the component in `deploy/__main__.py` in sync with it).
3. The image is pushed to the ECR repo with tag `latest`.
4. An `aws.imagebuilder.Image` resource carries a `source-hash` tag with `replace_on_changes`. Any change to the
   source hash replaces it, starts a build, and `pulumi up` waits for the build before the ECS task definition
   is updated. An `IMAGE_SOURCE_HASH` env var in the task definition forces a new revision and rollout.
5. `aws.imagebuilder.ImagePipeline` exists for out-of-band rebuilds (base image patches):
   `aws imagebuilder start-image-pipeline-execution --image-pipeline-arn <arn>`, or set
   `pulumi config set imageRebuildSchedule "cron(0 4 ? * mon *)"` in the app stack. A pipeline rebuild
   overwrites `latest` but does not roll out ECS by itself; run a `pulumi up` or
   `aws ecs update-service --force-new-deployment`.

## Bootstrap (one time)

1. Need a Pulumi Cloud org and Pulumi CLI >= 3.277.0. Install the GitHub integration in Pulumi Cloud and grant it
   `dirien/pulumi-events`.
2. The target stack must already exist (Delivery does not create stacks):
   `cd deploy && pulumi stack init <org>/dev` (if not done), with its ESC imports in `Pulumi.dev.yaml`.
3. Make sure the ESC environment `marketing/aws-auth` yields AWS credentials for a role that can also manage
   Image Builder, S3, IAM, EC2 and ECR. Delivery runs stack updates as the pipeline's service principal
   (generated, or set `service_principal` on `delivery.Pipeline`); it needs access to the ESC environments and stack.
   I could not verify from the docs how the OIDC `sub` claim looks for Delivery runs. Check the Delivery
   identity docs and update the trust policy of the role accordingly.
4. Register the pipeline, then commit and push:

   ```bash
   cd delivery
   uv sync
   pulumi stack init <org>/main
   pulumi delivery register     # writes delivery:source into Pulumi.main.yaml; commit it
   cd .. && git add delivery && git commit -m "feat: add delivery pipeline" && git push origin main
   ```

   Registering does not start a run; the push does. Follow it in Pulumi Cloud under Delivery, Pipelines.
5. Later edits to `delivery/` are picked up on push to the default branch.

First deploy note: the app stack previously used `pulumi-docker-build`; its `image` resource is removed from state
by the next `pulumi up`. Run `uv lock` in `deploy/` to drop that dependency from `uv.lock`.

## Open points

- Delivery is a public preview, and the docs say the Python SDK sample was not run end to end. Expect API changes.
- The `verify` job runs in the default Delivery image; if `uv` or Python 3.12 is missing there, set `image=` on the `Job`.
- Image Builder with a non-AL/Ubuntu parent (`python:slim`, Debian) relies on `platform_override="Linux"`.
  If the first build rejects the parent image, switch `PARENT_IMAGE` to an Amazon Linux or Ubuntu based
  image and install Python 3.12 in the component.
- The build instance runs in a private subnet through the NAT gateway; first builds take several minutes.
