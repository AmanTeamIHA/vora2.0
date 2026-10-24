#!/bin/sh
# Push is done by the caller. This registers task definitions, migrates, and rolls the services.
set -eu

api_image="$1"
web_image="$2"
agent_image="${3:-}"
cluster="vora2-dev"
region="ap-south-1"

status="$(aws ecs describe-clusters --clusters "$cluster" --region "$region" --query 'clusters[0].status' --output text)"
if [ "$status" != "ACTIVE" ]; then
  echo "Cluster $cluster is not active yet. Infra apply creates it."
  exit 0
fi

register() {
  family="$1"
  image="$2"
  container="$3"
  aws ecs describe-task-definition --task-definition "$family" --region "$region" --query taskDefinition > /tmp/vora-td.json
  jq --arg image "$image" --arg container "$container" '
    .containerDefinitions |= map(if .name == $container then .image = $image else . end)
    | del(
        .taskDefinitionArn,
        .revision,
        .status,
        .requiresAttributes,
        .compatibilities,
        .registeredAt,
        .registeredBy,
        .deregisteredAt
      )
  ' /tmp/vora-td.json > /tmp/vora-td-new.json
  aws ecs register-task-definition --region "$region" --cli-input-json file:///tmp/vora-td-new.json > /dev/null
}

register vora2-api "$api_image" api
register vora2-web "$web_image" web
register vora2-migrate "$api_image" migrate
register vora2-bootstrap-owner "$api_image" owner

net="$(aws ecs describe-services --cluster "$cluster" --services vora2-api --region "$region" --query 'services[0].networkConfiguration.awsvpcConfiguration')"
subnets="$(printf '%s' "$net" | jq -r '.subnets | join(",")')"
groups="$(printf '%s' "$net" | jq -r '.securityGroups | join(",")')"

task="$(aws ecs run-task \
  --cluster "$cluster" \
  --region "$region" \
  --launch-type FARGATE \
  --task-definition vora2-migrate \
  --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$groups],assignPublicIp=DISABLED}" \
  --query 'tasks[0].taskArn' \
  --output text)"

aws ecs wait tasks-stopped --cluster "$cluster" --region "$region" --tasks "$task"
code="$(aws ecs describe-tasks --cluster "$cluster" --region "$region" --tasks "$task" --query 'tasks[0].containers[0].exitCode' --output text)"
echo "alembic exit $code"
test "$code" = "0"

aws ecs update-service --cluster "$cluster" --region "$region" --service vora2-api --task-definition vora2-api --desired-count 1 > /dev/null
aws ecs update-service --cluster "$cluster" --region "$region" --service vora2-web --task-definition vora2-web --desired-count 1 > /dev/null
aws ecs wait services-stable --cluster "$cluster" --region "$region" --services vora2-api vora2-web

if aws ecs describe-task-definition --task-definition vora2-seed-demo --region "$region" >/dev/null 2>&1; then
  register vora2-seed-demo "$api_image" seed
  seed="$(aws ecs run-task \
    --cluster "$cluster" \
    --region "$region" \
    --launch-type FARGATE \
    --task-definition vora2-seed-demo \
    --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$groups],assignPublicIp=DISABLED}" \
    --query 'tasks[0].taskArn' \
    --output text)"
  aws ecs wait tasks-stopped --cluster "$cluster" --region "$region" --tasks "$seed"
  seed_code="$(aws ecs describe-tasks --cluster "$cluster" --region "$region" --tasks "$seed" --query 'tasks[0].containers[0].exitCode' --output text)"
  echo "seed exit $seed_code"
  test "$seed_code" = "0"
fi

if [ -n "$agent_image" ]; then
  agent_status="$(aws ecs describe-services --cluster "$cluster" --services vora2-agent --region "$region" --query 'services[0].status' --output text || true)"
  if [ "$agent_status" = "ACTIVE" ]; then
    register vora2-agent "$agent_image" agent
    aws ecs update-service --cluster "$cluster" --region "$region" --service vora2-agent --task-definition vora2-agent --desired-count 1 > /dev/null
    aws ecs wait services-stable --cluster "$cluster" --region "$region" --services vora2-agent
  else
    echo "vora2-agent is not active yet ($agent_status). Infra apply creates it."
  fi
fi
