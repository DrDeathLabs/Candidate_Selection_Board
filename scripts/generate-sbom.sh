#!/usr/bin/env bash
#
# generate-sbom.sh — produce a full CycloneDX SBOM for AI-Assisted Selection Board.
#
# Captures exact pinned dependency versions AND container OS packages for every
# component: the three first-party images (backend, frontend, ocr) plus the six
# pinned third-party images (nginx, postgres, redis, minio, opensearch, clamav).
#
# Tooling is run via Docker so nothing needs to be installed on the host:
#   - anchore/syft          generates per-image CycloneDX SBOMs
#   - cyclonedx/cyclonedx-cli  merges them into one document
#
# Output: sbom/*.cdx.json  +  sbom/selection-board.cdx.json (merged)
#
# Usage:  bash scripts/generate-sbom.sh
#
set -euo pipefail

# Keep Git Bash from mangling /work and /sbom into Windows paths when they are
# passed to `docker run` (no-op on Linux/macOS).
export MSYS_NO_PATHCONV=1

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SBOM_DIR="${REPO_ROOT}/sbom"
# Temp dir lives under the repo so the path is shared with Docker Desktop on
# Windows (the MSYS /tmp tree is not a shared drive).
TMP_DIR="${SBOM_DIR}/.tmp"
SYFT_IMAGE="anchore/syft:latest"
CDX_IMAGE="cyclonedx/cyclonedx-cli:latest"

trap 'rm -rf "${TMP_DIR}"' EXIT

# Run from the repo root so `docker build` receives a relative context path,
# which is not affected by MSYS_NO_PATHCONV (an absolute /c/... context would
# fail to resolve under Docker Desktop on Windows).
cd "${REPO_ROOT}"

mkdir -p "${SBOM_DIR}" "${TMP_DIR}"

# name=image-reference. First-party images are built locally below; third-party
# images are pulled at their pinned tags from docker-compose.yml.
FIRST_PARTY=(
  "backend=services/backend"
  "frontend=services/frontend"
  "ocr=services/ocr"
)
THIRD_PARTY=(
  "nginx=nginx:1.27-alpine"
  "postgres=postgres:16-alpine"
  "redis=redis:7-alpine"
  "minio=minio/minio:RELEASE.2025-01-20T14-49-07Z"
  "opensearch=opensearchproject/opensearch:2.17.1"
  "clamav=clamav/clamav:1.4"
)

echo "==> Building first-party images"
for entry in "${FIRST_PARTY[@]}"; do
  name="${entry%%=*}"; ctx="${entry#*=}"
  echo "    building sb-${name} from ${ctx}"
  docker build -t "sb-${name}:sbom" "${ctx}"
done

echo "==> Pulling third-party images"
for entry in "${THIRD_PARTY[@]}"; do
  ref="${entry#*=}"
  echo "    pulling ${ref}"
  docker pull "${ref}"
done

# scan <name> <image-ref> — save the image to a docker-archive tarball and run
# syft against it. Scanning the saved tar avoids mounting the Docker socket,
# which keeps this portable (including Docker Desktop on Windows).
scan() {
  local name="$1" ref="$2"
  echo "    scanning ${name} (${ref})"
  # Use a path relative to the repo root for `docker save -o`: an absolute
  # /c/... path would be passed verbatim (MSYS_NO_PATHCONV) and rejected by
  # docker save on Windows. The bind mount below uses the absolute path, which
  # Docker Desktop does accept for -v sources.
  docker save "${ref}" -o "sbom/.tmp/${name}.tar"
  docker run --rm -v "${TMP_DIR}:/work" "${SYFT_IMAGE}" \
    "docker-archive:/work/${name}.tar" \
    -o "cyclonedx-json=/work/${name}.cdx.json"
  cp "${TMP_DIR}/${name}.cdx.json" "${SBOM_DIR}/${name}.cdx.json"
}

echo "==> Generating per-component SBOMs"
for entry in "${FIRST_PARTY[@]}"; do
  name="${entry%%=*}"
  scan "${name}" "sb-${name}:sbom"
done
for entry in "${THIRD_PARTY[@]}"; do
  name="${entry%%=*}"; ref="${entry#*=}"
  scan "${name}" "${ref}"
done

# The production frontend image ships only Vite-bundled static assets — the app's
# npm dependency tree (react, axios, ...) is not present in the runtime image, so
# the image scan above only sees the `serve`/npm runtime packages. Recover the
# real application dependencies by scanning the frontend source (package-lock.json
# + node_modules) and merge them into the frontend SBOM alongside the runtime OS
# packages from the image scan.
echo "==> Augmenting frontend SBOM with source dependencies"
docker run --rm -v "$(pwd)/services/frontend:/src:ro" -v "${TMP_DIR}:/work" "${SYFT_IMAGE}" \
  "dir:/src" -o "cyclonedx-json=/work/frontend-src.cdx.json"
cp "${SBOM_DIR}/frontend.cdx.json" "${TMP_DIR}/frontend-img.cdx.json"
docker run --rm -v "${TMP_DIR}:/work" "${CDX_IMAGE}" merge \
  --input-files /work/frontend-src.cdx.json /work/frontend-img.cdx.json \
  --output-file /work/frontend.cdx.json
cp "${TMP_DIR}/frontend.cdx.json" "${SBOM_DIR}/frontend.cdx.json"

echo "==> Writing third-party image manifest"
{
  echo "# Pinned third-party container images (from docker-compose.yml)"
  for entry in "${THIRD_PARTY[@]}"; do echo "${entry#*=}"; done
} > "${SBOM_DIR}/thirdparty-images.txt"

echo "==> Merging into selection-board.cdx.json"
MERGE_ARGS=()
for entry in "${FIRST_PARTY[@]}" "${THIRD_PARTY[@]}"; do
  name="${entry%%=*}"
  MERGE_ARGS+=("/sbom/${name}.cdx.json")
done
docker run --rm -v "${SBOM_DIR}:/sbom" "${CDX_IMAGE}" merge \
  --input-files "${MERGE_ARGS[@]}" \
  --output-file "/sbom/selection-board.cdx.json"

echo "==> Done. SBOMs written to ${SBOM_DIR}/"
ls -1 "${SBOM_DIR}"
