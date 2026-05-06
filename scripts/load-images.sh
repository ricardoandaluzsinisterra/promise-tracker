#!/bin/bash
set -e

CLUSTER_NAME="promise-tracker"

# Each entry is "image-name:Directory Name" matching the repo folders exactly
SERVICES=(
  "promises-service:Promises Service"
  "politicians-service:Politicians Service"
  "sources-service:Sources Service"
  "trackers-service:Trackers Service"
  "projection-service:Projection Service"
  "api-gateway:API Gateway"
)

for entry in "${SERVICES[@]}"; do
  IMAGE="${entry%%:*}"
  CONTEXT="${entry##*:}"
  echo ">>> Building $IMAGE from './$CONTEXT'..."
  docker build -t "$IMAGE:latest" "./$CONTEXT"
  echo ">>> Loading $IMAGE into KinD cluster '$CLUSTER_NAME'..."
  kind load docker-image "$IMAGE:latest" --name "$CLUSTER_NAME"
  echo ">>> Done: $IMAGE"
  echo ""
done

echo "All application images built and loaded into KinD."
echo "Run: kubectl apply -k k8s/"
