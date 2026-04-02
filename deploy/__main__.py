"""Pulumi program: deploy pulumi-events MCP server to AWS ECS Fargate."""

import json

import pulumi
import pulumi_aws as aws
import pulumi_awsx as awsx
import pulumi_docker_build as docker_build

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
# Docker Image Build + Push
# ---------------------------------------------------------------------------
image = docker_build.Image(
    "image",
    docker_build.ImageArgs(
        tags=[repo.repository_url.apply(lambda url: f"{url}:latest")],
        context=docker_build.BuildContextArgs(location=".."),
        dockerfile=docker_build.DockerfileArgs(location="../Dockerfile"),
        platforms=[docker_build.Platform.LINUX_AMD64],
        push=True,
        registries=[
            docker_build.RegistryArgs(
                address=repo.repository_url,
                username="AWS",
                password=aws.ecr.get_authorization_token_output(
                    registry_id=repo.registry_id,
                ).password,
            ),
        ],
    ),
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
            image.ref,
            log_group.name,
            app_secrets.arn,
            cloudfront_domain,
            meetup_jwt_key_id,
            meetup_member_id,
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
