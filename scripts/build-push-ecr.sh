#!/usr/bin/env bash
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# build-push-ecr.sh
# Build the DevLake server, config-ui, and dashboard (grafana) images and push
# them to AWS ECR using the `default` AWS profile.
#
# The images are built through the repo's existing Makefile targets, with
# IMAGE_REPO pointed at the ECR registry so each image is tagged for ECR
# directly (no re-tag step needed).
#
# Overridable via environment variables:
#   AWS_PROFILE          AWS CLI profile             (default: default)
#   AWS_REGION           ECR region                  (default: profile's region)
#   TAG                  image tag                   (default: git short SHA)
#   DOCKER_DEFAULT_PLATFORM  target arch for images  (default: linux/arm64)
#   SERVER_REPO / UI_REPO / DASHBOARD_REPO   ECR repo names
#
# The server image is built from backend/Dockerfile.arm64 (native single-arch,
# no cross-compile) so an arm64 build host produces an arm64 image with no
# QEMU/binfmt emulation. config-ui and dashboard build natively via their make
# targets. Run this on an arm64 host to get arm64 images.
#
# Usage:
#   scripts/build-push-ecr.sh
#   AWS_REGION=ap-southeast-1 TAG=v1.2.3 scripts/build-push-ecr.sh

set -euo pipefail

# --- resolve repo root (script lives in <root>/scripts) ---------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

# --- config -----------------------------------------------------------------
AWS_PROFILE="${AWS_PROFILE:-default}"
# Build target arch. Default linux/arm64 (native on Graviton/arm64 EC2 build
# hosts). Override to linux/amd64 for x86 runtime targets.
DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/arm64}"
export DOCKER_DEFAULT_PLATFORM

SERVER_REPO="${SERVER_REPO:-devlake}"
UI_REPO="${UI_REPO:-devlake-config-ui}"
DASHBOARD_REPO="${DASHBOARD_REPO:-devlake-dashboard}"

# Tag: prefer explicit TAG, else the git short SHA. The Makefile default
# (`git tag --points-at HEAD`) is empty on an untagged branch, so never rely
# on it here.
SHA="$(git show -s --format=%h)"
TAG="${TAG:-${SHA}}"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# --- preflight --------------------------------------------------------------
command -v aws    >/dev/null 2>&1 || die "aws CLI not found on PATH"
command -v docker >/dev/null 2>&1 || die "docker not found on PATH"
docker info       >/dev/null 2>&1 || die "docker daemon not reachable (is Docker running?)"

# Region: explicit AWS_REGION, else the profile's configured region.
AWS_REGION="${AWS_REGION:-$(aws configure get region --profile "${AWS_PROFILE}" 2>/dev/null || true)}"
[ -n "${AWS_REGION}" ] || die "no region: set AWS_REGION or 'aws configure set region <r> --profile ${AWS_PROFILE}'"

ACCOUNT_ID="$(aws sts get-caller-identity --profile "${AWS_PROFILE}" --query Account --output text 2>/dev/null)" \
  || die "aws sts get-caller-identity failed for profile '${AWS_PROFILE}' (auth expired? run: aws sso login --profile ${AWS_PROFILE})"
[ -n "${ACCOUNT_ID}" ] && [ "${ACCOUNT_ID}" != "None" ] || die "could not resolve AWS account id"

REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

log "profile=${AWS_PROFILE} account=${ACCOUNT_ID} region=${AWS_REGION}"
log "registry=${REGISTRY}"
log "tag=${TAG} sha=${SHA} platform=${DOCKER_DEFAULT_PLATFORM}"

# --- ensure ECR repositories exist ------------------------------------------
ensure_repo() {
  local repo="$1"
  if aws ecr describe-repositories --repository-names "${repo}" \
        --profile "${AWS_PROFILE}" --region "${AWS_REGION}" >/dev/null 2>&1; then
    log "ecr repo exists: ${repo}"
  else
    log "creating ecr repo: ${repo}"
    aws ecr create-repository --repository-name "${repo}" \
      --image-scanning-configuration scanOnPush=true \
      --profile "${AWS_PROFILE}" --region "${AWS_REGION}" >/dev/null
  fi
}
ensure_repo "${SERVER_REPO}"
ensure_repo "${UI_REPO}"
ensure_repo "${DASHBOARD_REPO}"

# --- docker login to ECR ----------------------------------------------------
log "logging in to ECR"
aws ecr get-login-password --profile "${AWS_PROFILE}" --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${REGISTRY}"

# --- build all three images tagged for ECR ----------------------------------
# Server: native build from backend/Dockerfile.arm64 (no cross-compile, no
# emulation) so an arm64 host yields an arm64 image. IMAGE_REPO=<registry> makes
# the make targets tag config-ui/dashboard directly for ECR.
log "building server image (native) from backend/Dockerfile.arm64"
( cd backend && docker build \
    -t "${REGISTRY}/${SERVER_REPO}:${TAG}" \
    --build-arg TAG="${TAG}" \
    --build-arg SHA="${SHA}" \
    --file ./Dockerfile.arm64 . )

log "building config-ui + dashboard images via make"
make build-config-ui-image build-grafana-image IMAGE_REPO="${REGISTRY}" TAG="${TAG}"

# --- push -------------------------------------------------------------------
# Own push loop (the Makefile push-grafana-image target has an indentation bug,
# and pushing here keeps repo->image mapping explicit).
push_image() {
  local repo="$1"
  local ref="${REGISTRY}/${repo}:${TAG}"
  log "pushing ${ref}"
  docker push "${ref}"
}
push_image "${SERVER_REPO}"
push_image "${UI_REPO}"
push_image "${DASHBOARD_REPO}"

log "done. pushed:"
printf '  %s\n' \
  "${REGISTRY}/${SERVER_REPO}:${TAG}" \
  "${REGISTRY}/${UI_REPO}:${TAG}" \
  "${REGISTRY}/${DASHBOARD_REPO}:${TAG}"
