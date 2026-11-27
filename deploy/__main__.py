"""Pulumi program: deploy pulumi-events MCP server to AWS ECS Fargate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pulumi
import pulumi_aws as aws
import pulumi_awsx as awsx

config = pulumi.Config()
container_cpu = config.get_int("containerCpu") or 256
container_memory = config.get_int("containerMemory") or 512
desired_count = config.get_int("desiredCount") or 1

# ---------------------------------------------------------------------------
# Secrets (from Pulumi config)
# ---------------------------------------------------------------------------
meetup_client_id = config.require_secret("meetupClientId")
luma_api_key = config.require_secret("lumaApiKey")
auth_token = config.require_secret("authToken")
google_client_id = config.require_secret("googleClientId")
google_client_secret = config.require_secret("googleClientSecret")
meetup_jwt_signing_key = config.get_secret("meetupJwtSigningKey") or ""
meetup_jwt_key_id = config.get("meetupJwtKeyId") or ""
meetup_member_id = config.get("meetupMemberId") or ""
luma_default_tint_color = config.get("lumaDefaultTintColor") or ""

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------
vpc = awsx.ec2.Vpc(
    "vpc",
    awsx.ec2.VpcArgs(
        number_of_availability_zones=2,
        nat_gateways=awsx.ec2.NatGatewayConfigurationArgs(
            strategy=awsx.ec2.NatGatewayStrategy.SINGLE,
        ),
    ),
)

# ---------------------------------------------------------------------------
# ECR Repository
# ---------------------------------------------------------------------------
repo = aws.ecr.Repository(
    "repo",
    aws.ecr.RepositoryArgs(
        force_delete=True,
    ),
)

# ---------------------------------------------------------------------------
# Container image build: EC2 Image Builder (no Docker daemon needed on the runner)
# ---------------------------------------------------------------------------
# Flow: source archive -> S3 -> Image Builder container recipe (component unpacks and
# `uv sync`s it, mirroring the repo Dockerfile) -> ECR. An aws.imagebuilder.Image
# resource is replaced whenever the source hash changes, which starts a new build and
# makes `pulumi up` wait for it. See ../delivery/README.md.
REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_INPUTS = ["src", "pyproject.toml", "uv.lock", ".python-version", "README.md"]
SOURCE_KEY = "source/pulumi-events.zip"
IMAGE_TAG = "latest"
PARENT_IMAGE = "public.ecr.aws/docker/library/python:3.12-slim-bookworm"
_IGNORED_NAMES = {".DS_Store", "Thumbs.db"}


def _source_files() -> list[Path]:
    """List the files that go into the image; the hash and the archive both use this."""
    files: list[Path] = []
    for entry in SOURCE_INPUTS:
        path = REPO_ROOT / entry
        candidates = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        files.extend(
            f
            for f in candidates
            if "__pycache__" not in f.parts
            and f.suffix not in {".pyc", ".pyo"}
            and f.name not in _IGNORED_NAMES
        )
    return files


SOURCE_FILES = _source_files()


def _source_hash() -> str:
    """Hash every file that goes into the image so code changes trigger a rebuild."""
    digest = hashlib.sha256()
    for file in SOURCE_FILES:
        digest.update(str(file.relative_to(REPO_ROOT)).encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


source_hash = _source_hash()


def _source_archive() -> pulumi.AssetArchive:
    """Archive exactly the hashed files, so hash and content cannot drift apart."""
    return pulumi.AssetArchive(
        {str(f.relative_to(REPO_ROOT)): pulumi.FileAsset(str(f)) for f in SOURCE_FILES}
    )


source_bucket = aws.s3.Bucket("image-source", force_destroy=True)

aws.s3.BucketPublicAccessBlock(
    "image-source-block",
    bucket=source_bucket.id,
    block_public_acls=True,
    block_public_policy=True,
    ignore_public_acls=True,
    restrict_public_buckets=True,
)

source_object = aws.s3.BucketObjectv2(
    "image-source-object",
    bucket=source_bucket.id,
    key=SOURCE_KEY,
    source=_source_archive(),
    source_hash=source_hash,
)

build_role = aws.iam.Role(
    "image-builder-role",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "sts:AssumeRole",
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                }
            ],
        }
    ),
)

for _name, _arn in {
    "ssm": "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    "ecr": "arn:aws:iam::aws:policy/EC2InstanceProfileForImageBuilderECRContainerBuilds",
}.items():
    aws.iam.RolePolicyAttachment(
        f"image-builder-role-{_name}",
        role=build_role.name,
        policy_arn=_arn,
    )

aws.iam.RolePolicy(
    "image-builder-role-source",
    role=build_role.id,
    policy=source_bucket.arn.apply(
        lambda arn: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject"],
                        "Resource": f"{arn}/{SOURCE_KEY}",
                    }
                ],
            }
        )
    ),
)

build_profile = aws.iam.InstanceProfile("image-builder-profile", role=build_role.name)

build_sg = aws.ec2.SecurityGroup(
    "image-builder-sg",
    vpc_id=vpc.vpc_id,
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],
        )
    ],
)

# Component: runs inside the container being built. Mirrors the repo Dockerfile
# (uv sync --frozen --no-dev into /app/.venv, non-root user `app`).
COMPONENT_TEMPLATE = """name: pulumi-events-app
description: Install pulumi-events from the S3 source archive
schemaVersion: 1.0
phases:
  - name: build
    steps:
      - name: DownloadSource
        action: S3Download
        inputs:
          - source: s3://{bucket}/{key}
            destination: /tmp/source.zip
      - name: InstallApp
        action: ExecuteBash
        inputs:
          commands:
            - set -euo pipefail
            - mkdir -p /app
            - python -m zipfile -e /tmp/source.zip /app
            - pip install --no-cache-dir uv
            - cd /app && UV_PYTHON_DOWNLOADS=never uv sync --frozen --no-dev --no-install-project
            - cd /app && UV_PYTHON_DOWNLOADS=never uv sync --frozen --no-dev --no-editable
            - rm -rf /app/src /tmp/source.zip /root/.cache
            - pip uninstall -y uv
            - groupadd --gid 1000 app
            - useradd --uid 1000 --gid app --create-home app
            - chown -R app:app /app
"""

dockerfile_template = """FROM {{{ imagebuilder:parentImage }}}
ENV PATH="/app/.venv/bin:$PATH" \\
    PULUMI_EVENTS_SERVER_HOST="0.0.0.0" \\
    PULUMI_EVENTS_AUTO_OPEN_BROWSER="false"
{{{ imagebuilder:environments }}}
{{{ imagebuilder:components }}}
WORKDIR /app
EXPOSE 8080
USER app
ENTRYPOINT ["pulumi-events"]
"""


def _recipe_version() -> str:
    """Derive the Image Builder semantic version from the build definition.

    Components and container recipes are immutable, and a replacement is created
    before the old one is deleted, so an edit must come with a new version or the
    create fails with ResourceAlreadyExists. The patch number is a hash of
    everything that defines the build; set `imageRecipeVersion` to override.
    """
    override = config.get("imageRecipeVersion")
    if override:
        return override
    definition = "\n".join([COMPONENT_TEMPLATE, dockerfile_template, PARENT_IMAGE, SOURCE_KEY])
    # 7 hex digits stay below Image Builder's per-part limit of 2^30 - 1.
    return f"1.0.{int(hashlib.sha256(definition.encode()).hexdigest()[:7], 16)}"


RECIPE_VERSION = _recipe_version()

build_component = aws.imagebuilder.Component(
    "image-component",
    name=f"{pulumi.get_project()}-{pulumi.get_stack()}-app",
    platform="Linux",
    version=RECIPE_VERSION,
    data=source_bucket.id.apply(
        lambda bucket: COMPONENT_TEMPLATE.format(bucket=bucket, key=SOURCE_KEY)
    ),
)

container_recipe = aws.imagebuilder.ContainerRecipe(
    "image-recipe",
    name=f"{pulumi.get_project()}-{pulumi.get_stack()}",
    version=RECIPE_VERSION,
    container_type="DOCKER",
    parent_image=PARENT_IMAGE,
    platform_override="Linux",
    components=[
        aws.imagebuilder.ContainerRecipeComponentArgs(component_arn=build_component.arn),
    ],
    dockerfile_template_data=dockerfile_template,
    target_repository=aws.imagebuilder.ContainerRecipeTargetRepositoryArgs(
        repository_name=repo.name,
        service="ECR",
    ),
)

infrastructure = aws.imagebuilder.InfrastructureConfiguration(
    "image-infra",
    name=f"{pulumi.get_project()}-{pulumi.get_stack()}",
    instance_profile_name=build_profile.name,
    instance_types=["t3.large"],
    subnet_id=vpc.private_subnet_ids.apply(lambda ids: ids[0]),
    security_group_ids=[build_sg.id],
    terminate_instance_on_failure=True,
    # The S3Download step runs inside the container build, one network hop past the
    # instance, so IMDSv2 needs a hop limit of 2 to hand it the instance-role token.
    instance_metadata_options=aws.imagebuilder.InfrastructureConfigurationInstanceMetadataOptionsArgs(
        http_tokens="required",
        http_put_response_hop_limit=2,
    ),
)

distribution = aws.imagebuilder.DistributionConfiguration(
    "image-distribution",
    name=f"{pulumi.get_project()}-{pulumi.get_stack()}",
    distributions=[
        aws.imagebuilder.DistributionConfigurationDistributionArgs(
            region=aws.get_region().region,
            container_distribution_configuration=(
                aws.imagebuilder.DistributionConfigurationDistributionContainerDistributionConfigurationArgs(
                    container_tags=[IMAGE_TAG],
                    target_repository=aws.imagebuilder.DistributionConfigurationDistributionContainerDistributionConfigurationTargetRepositoryArgs(
                        repository_name=repo.name,
                        service="ECR",
                    ),
                )
            ),
        )
    ],
)

# Image pipeline: kept for out-of-band rebuilds (base image patches), e.g.
#   aws imagebuilder start-image-pipeline-execution --image-pipeline-arn <arn>
# It is not the code-change trigger; the Image resource below is. Set the config
# `imageRebuildSchedule` (cron, e.g. "cron(0 4 ? * mon *)") to rebuild on a schedule.
rebuild_schedule = config.get("imageRebuildSchedule")
image_pipeline = aws.imagebuilder.ImagePipeline(
    "image-pipeline",
    name=f"{pulumi.get_project()}-{pulumi.get_stack()}",
    container_recipe_arn=container_recipe.arn,
    infrastructure_configuration_arn=infrastructure.arn,
    distribution_configuration_arn=distribution.arn,
    status="ENABLED",
    schedule=(
        aws.imagebuilder.ImagePipelineScheduleArgs(
            schedule_expression=rebuild_schedule,
            pipeline_execution_start_condition="EXPRESSION_MATCH_ONLY",
        )
        if rebuild_schedule
        else None
    ),
)

# Code-change trigger: creating an Image starts a build and the provider waits for it.
# `source-hash` is in replace_on_changes, so a new hash replaces the Image (create
# first, then delete the old one), which rebuilds from the freshly uploaded archive.
image = aws.imagebuilder.Image(
    "image",
    container_recipe_arn=container_recipe.arn,
    infrastructure_configuration_arn=infrastructure.arn,
    distribution_configuration_arn=distribution.arn,
    tags={"source-hash": source_hash},
    opts=pulumi.ResourceOptions(
        replace_on_changes=["tags"],
        depends_on=[source_object],
    ),
)

# ECS pins the digest this build produced, not the mutable `latest` tag, so an
# out-of-band ImagePipeline rebuild never reaches running tasks (restarts, scale-out)
# without a `pulumi up`. The lookup depends on image.id, so it runs after the build.
built_image = aws.ecr.get_image_output(
    repository_name=repo.name,
    image_tag=image.id.apply(lambda _: IMAGE_TAG),
)
image_ref = pulumi.Output.all(repo.repository_url, built_image.image_digest).apply(
    lambda args: f"{args[0]}@{args[1]}"
)

# ---------------------------------------------------------------------------
# ECS Cluster
# ---------------------------------------------------------------------------
cluster = aws.ecs.Cluster("cluster")

# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------
app_secrets = aws.secretsmanager.Secret("app-secrets")

app_secrets_version = aws.secretsmanager.SecretVersion(
    "app-secrets-version",
    aws.secretsmanager.SecretVersionArgs(
        secret_id=app_secrets.id,
        secret_string=pulumi.Output.all(
            meetup_client_id,
            luma_api_key,
            auth_token,
            google_client_id,
            google_client_secret,
            meetup_jwt_signing_key,
        ).apply(
            lambda args: json.dumps(
                {
                    "PULUMI_EVENTS_MEETUP_CLIENT_ID": args[0],
                    "PULUMI_EVENTS_LUMA_API_KEY": args[1],
                    "PULUMI_EVENTS_AUTH_TOKEN": args[2],
                    "PULUMI_EVENTS_GOOGLE_CLIENT_ID": args[3],
                    "PULUMI_EVENTS_GOOGLE_CLIENT_SECRET": args[4],
                    "PULUMI_EVENTS_MEETUP_JWT_SIGNING_KEY": args[5],
                }
            )
        ),
    ),
)

# ---------------------------------------------------------------------------
# IAM Roles
# ---------------------------------------------------------------------------
execution_role = aws.iam.Role(
    "execution-role",
    aws.iam.RoleArgs(
        assume_role_policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Effect": "Allow",
                        "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    }
                ],
            }
        ),
    ),
)

aws.iam.RolePolicyAttachment(
    "execution-role-ecr",
    aws.iam.RolePolicyAttachmentArgs(
        role=execution_role.name,
        policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
    ),
)

secrets_policy = aws.iam.RolePolicy(
    "execution-role-secrets",
    aws.iam.RolePolicyArgs(
        role=execution_role.id,
        policy=app_secrets.arn.apply(
            lambda arn: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "secretsmanager:GetSecretValue",
                            ],
                            "Resource": arn,
                        }
                    ],
                }
            )
        ),
    ),
)

task_role = aws.iam.Role(
    "task-role",
    aws.iam.RoleArgs(
        assume_role_policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Effect": "Allow",
                        "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    }
                ],
            }
        ),
    ),
)

# ---------------------------------------------------------------------------
# CloudWatch Log Group
# ---------------------------------------------------------------------------
log_group = aws.cloudwatch.LogGroup(
    "log-group",
    aws.cloudwatch.LogGroupArgs(
        retention_in_days=14,
    ),
)

# ---------------------------------------------------------------------------
# Security Groups
# ---------------------------------------------------------------------------
alb_sg = aws.ec2.SecurityGroup(
    "alb-sg",
    aws.ec2.SecurityGroupArgs(
        vpc_id=vpc.vpc_id,
        ingress=[
            aws.ec2.SecurityGroupIngressArgs(
                protocol="tcp",
                from_port=80,
                to_port=80,
                cidr_blocks=["0.0.0.0/0"],
            ),
        ],
        egress=[
            aws.ec2.SecurityGroupEgressArgs(
                protocol="-1",
                from_port=0,
                to_port=0,
                cidr_blocks=["0.0.0.0/0"],
            ),
        ],
    ),
)

ecs_sg = aws.ec2.SecurityGroup(
    "ecs-sg",
    aws.ec2.SecurityGroupArgs(
        vpc_id=vpc.vpc_id,
        ingress=[
            aws.ec2.SecurityGroupIngressArgs(
                protocol="tcp",
                from_port=8080,
                to_port=8080,
                security_groups=[alb_sg.id],
            ),
        ],
        egress=[
            aws.ec2.SecurityGroupEgressArgs(
                protocol="-1",
                from_port=0,
                to_port=0,
                cidr_blocks=["0.0.0.0/0"],
            ),
        ],
    ),
)

# ---------------------------------------------------------------------------
# ALB (internal, HTTP only — CloudFront terminates TLS)
# ---------------------------------------------------------------------------
alb = aws.lb.LoadBalancer(
    "alb",
    aws.lb.LoadBalancerArgs(
        internal=False,  # CloudFront needs to reach it
        load_balancer_type="application",
        security_groups=[alb_sg.id],
        subnets=vpc.public_subnet_ids,
    ),
)

target_group = aws.lb.TargetGroup(
    "tg",
    aws.lb.TargetGroupArgs(
        port=8080,
        protocol="HTTP",
        target_type="ip",
        vpc_id=vpc.vpc_id,
        health_check=aws.lb.TargetGroupHealthCheckArgs(
            path="/health",
            port="8080",
            protocol="HTTP",
            healthy_threshold=2,
            unhealthy_threshold=3,
            interval=30,
            timeout=5,
        ),
    ),
)

listener = aws.lb.Listener(
    "listener",
    aws.lb.ListenerArgs(
        load_balancer_arn=alb.arn,
        port=80,
        protocol="HTTP",
        default_actions=[
            aws.lb.ListenerDefaultActionArgs(
                type="forward",
                target_group_arn=target_group.arn,
            ),
        ],
    ),
)

# ---------------------------------------------------------------------------
# CloudFront Distribution
# ---------------------------------------------------------------------------
cloudfront_distribution = aws.cloudfront.Distribution(
    "cdn",
    aws.cloudfront.DistributionArgs(
        enabled=True,
        comment="pulumi-events MCP server",
        default_cache_behavior=aws.cloudfront.DistributionDefaultCacheBehaviorArgs(
            target_origin_id="alb",
            viewer_protocol_policy="redirect-to-https",
            allowed_methods=[
                "GET",
                "HEAD",
                "OPTIONS",
                "PUT",
                "POST",
                "PATCH",
                "DELETE",
            ],
            cached_methods=["GET", "HEAD"],
            # CachingDisabled managed policy
            cache_policy_id="4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
            # AllViewerExceptHostHeader managed origin request policy
            origin_request_policy_id="b689b0a8-53d0-40ab-baf2-68738e2966ac",
            compress=True,
        ),
        origins=[
            aws.cloudfront.DistributionOriginArgs(
                domain_name=alb.dns_name,
                origin_id="alb",
                custom_origin_config=aws.cloudfront.DistributionOriginCustomOriginConfigArgs(
                    http_port=80,
                    https_port=443,
                    origin_protocol_policy="http-only",
                    origin_ssl_protocols=["TLSv1.2"],
                ),
            ),
        ],
        restrictions=aws.cloudfront.DistributionRestrictionsArgs(
            geo_restriction=aws.cloudfront.DistributionRestrictionsGeoRestrictionArgs(
                restriction_type="none",
            ),
        ),
        viewer_certificate=aws.cloudfront.DistributionViewerCertificateArgs(
            cloudfront_default_certificate=True,
        ),
    ),
)

# ---------------------------------------------------------------------------
# ECS Task Definition
# ---------------------------------------------------------------------------
cloudfront_domain = cloudfront_distribution.domain_name.apply(
    lambda d: f"https://{d}"
)

task_definition = aws.ecs.TaskDefinition(
    "task-def",
    aws.ecs.TaskDefinitionArgs(
        family="pulumi-events",
        cpu=str(container_cpu),
        memory=str(container_memory),
        network_mode="awsvpc",
        requires_compatibilities=["FARGATE"],
        execution_role_arn=execution_role.arn,
        task_role_arn=task_role.arn,
        container_definitions=pulumi.Output.all(
            image_ref,
            log_group.name,
            app_secrets.arn,
            cloudfront_domain,
            meetup_jwt_key_id,
            meetup_member_id,
            luma_default_tint_color,
        ).apply(
            lambda args: json.dumps(
                [
                    {
                        "name": "pulumi-events",
                        "image": args[0],
                        "essential": True,
                        "portMappings": [
                            {
                                "containerPort": 8080,
                                "protocol": "tcp",
                            }
                        ],
                        "environment": [
                            {
                                "name": "PULUMI_EVENTS_SERVER_HOST",
                                "value": "0.0.0.0",  # noqa: S104
                            },
                            {
                                # Changes with the code so the task definition rolls out
                                # the freshly built image even though the tag is `latest`.
                                "name": "IMAGE_SOURCE_HASH",
                                "value": source_hash,
                            },
                            {
                                "name": "PULUMI_EVENTS_SERVER_PORT",
                                "value": "8080",
                            },
                            {
                                "name": "PULUMI_EVENTS_AUTO_OPEN_BROWSER",
                                "value": "false",
                            },
                            {
                                "name": "PULUMI_EVENTS_MEETUP_TOKEN_BACKEND",
                                "value": "env",
                            },
                            {
                                "name": "PULUMI_EVENTS_BASE_URL",
                                "value": args[3],
                            },
                            {
                                "name": "PULUMI_EVENTS_MEETUP_JWT_KEY_ID",
                                "value": args[4],
                            },
                            {
                                "name": "PULUMI_EVENTS_MEETUP_MEMBER_ID",
                                "value": args[5],
                            },
                            {
                                "name": "PULUMI_EVENTS_LUMA_DEFAULT_TINT_COLOR",
                                "value": args[6],
                            },
                        ],
                        "secrets": [
                            {
                                "name": "PULUMI_EVENTS_MEETUP_CLIENT_ID",
                                "valueFrom": f"{args[2]}:PULUMI_EVENTS_MEETUP_CLIENT_ID::",
                            },
                            {
                                "name": "PULUMI_EVENTS_LUMA_API_KEY",
                                "valueFrom": f"{args[2]}:PULUMI_EVENTS_LUMA_API_KEY::",
                            },
                            {
                                "name": "PULUMI_EVENTS_AUTH_TOKEN",
                                "valueFrom": f"{args[2]}:PULUMI_EVENTS_AUTH_TOKEN::",
                            },
                            {
                                "name": "PULUMI_EVENTS_GOOGLE_CLIENT_ID",
                                "valueFrom": f"{args[2]}:PULUMI_EVENTS_GOOGLE_CLIENT_ID::",
                            },
                            {
                                "name": "PULUMI_EVENTS_GOOGLE_CLIENT_SECRET",
                                "valueFrom": f"{args[2]}:PULUMI_EVENTS_GOOGLE_CLIENT_SECRET::",
                            },
                            {
                                "name": "PULUMI_EVENTS_MEETUP_JWT_SIGNING_KEY",
                                "valueFrom": f"{args[2]}:PULUMI_EVENTS_MEETUP_JWT_SIGNING_KEY::",
                            },
                        ],
                        "logConfiguration": {
                            "logDriver": "awslogs",
                            "options": {
                                "awslogs-group": args[1],
                                "awslogs-region": aws.get_region().region,
                                "awslogs-stream-prefix": "ecs",
                            },
                        },
                    }
                ]
            )
        ),
    ),
)

# ---------------------------------------------------------------------------
# ECS Service
# ---------------------------------------------------------------------------
service = aws.ecs.Service(
    "service",
    aws.ecs.ServiceArgs(
        cluster=cluster.arn,
        task_definition=task_definition.arn,
        desired_count=desired_count,
        launch_type="FARGATE",
        network_configuration=aws.ecs.ServiceNetworkConfigurationArgs(
            subnets=vpc.private_subnet_ids,
            security_groups=[ecs_sg.id],
            assign_public_ip=False,
        ),
        load_balancers=[
            aws.ecs.ServiceLoadBalancerArgs(
                target_group_arn=target_group.arn,
                container_name="pulumi-events",
                container_port=8080,
            ),
        ],
    ),
    pulumi.ResourceOptions(depends_on=[listener]),
)

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
pulumi.export("cloudfront_url", cloudfront_distribution.domain_name.apply(lambda d: f"https://{d}"))
pulumi.export("mcp_endpoint", cloudfront_distribution.domain_name.apply(lambda d: f"https://{d}/mcp"))
pulumi.export("alb_dns", alb.dns_name)
pulumi.export("ecr_repo_url", repo.repository_url)
