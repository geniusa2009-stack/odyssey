#!/usr/bin/env bash
# Builds a versioned Linux package of ODYSSEY with Pixel Streaming 2, on a remote Ubuntu 22.04/24.04
# build host (never on the Mac). Needs ~32 vCPU / 64 GB RAM / 400 GB disk for a reasonable time.
#
#   GITHUB_TOKEN=... ODYSSEY_REF=deploy/pixel-streaming-kit ./build_linux_package.sh
#
# GITHUB_TOKEN must belong to an account linked to Epic Games (EpicGames/UnrealEngine access) and able
# to read geniusa2009-stack/odyssey. It is passed to git through GIT_ASKPASS for this process only and
# is never written to disk, a remote URL or the package.
set -euo pipefail
: "${GITHUB_TOKEN:?set GITHUB_TOKEN for this shell only}"
UE_TAG="${UE_TAG:-5.8.4-release}"
ODYSSEY_REPO="${ODYSSEY_REPO:-https://github.com/geniusa2009-stack/odyssey.git}"
ODYSSEY_REF="${ODYSSEY_REF:-deploy/pixel-streaming-kit}"
WORK="${WORK:-$HOME/odyssey-build}"
CONFIG="${CONFIG:-Development}"   # Development keeps the local-backend environment allowed
mkdir -p "$WORK"

ASKPASS="$(mktemp)"; trap 'rm -f "$ASKPASS"' EXIT
printf '#!/bin/sh\necho "$GITHUB_TOKEN"\n' >"$ASKPASS"; chmod 700 "$ASKPASS"
export GIT_ASKPASS="$ASKPASS" GIT_TERMINAL_PROMPT=0

sudo apt-get update -y
sudo apt-get install -y git git-lfs build-essential python3 curl xdg-user-dirs

# 1. Engine (stock Epic release tag; the project has no dependency on the local engine fork)
if [[ ! -d "$WORK/UE/.git" ]]; then
  git -c credential.username=x-access-token clone --depth 1 --branch "$UE_TAG" \
    https://github.com/EpicGames/UnrealEngine.git "$WORK/UE"
fi
cd "$WORK/UE"
./Setup.sh
./GenerateProjectFiles.sh

# 2. Project at the exact ref (LFS content included)
if [[ ! -d "$WORK/odyssey/.git" ]]; then
  git -c credential.username=x-access-token clone --branch "$ODYSSEY_REF" "$ODYSSEY_REPO" "$WORK/odyssey"
else
  git -C "$WORK/odyssey" fetch origin "$ODYSSEY_REF" && git -C "$WORK/odyssey" checkout --detach FETCH_HEAD
fi
git -C "$WORK/odyssey" lfs install --local
git -c credential.username=x-access-token -C "$WORK/odyssey" lfs pull
REV="$(git -C "$WORK/odyssey" rev-parse --short HEAD)"
VERSION="odyssey-linux-$(date -u +%Y%m%d-%H%M)-$REV"
PROJECT="$WORK/odyssey/Odyssey.uproject"

# 3. Editor (needed by the cook) + package
Engine/Build/BatchFiles/Linux/Build.sh ShaderCompileWorker Linux Development
Engine/Build/BatchFiles/Linux/Build.sh OdysseyEditor Linux Development -Project="$PROJECT"
Engine/Build/BatchFiles/RunUAT.sh BuildCookRun -project="$PROJECT" -noP4 -utf8output -unattended \
  -platform=Linux -clientconfig="$CONFIG" -build -cook -stage -pak -prereqs \
  -archive -archivedirectory="$WORK/out/$VERSION"

# 4. Versioned tarball + checksum; upload it to the stream host (scp) or object storage
cd "$WORK/out"
tar -C "$VERSION" -czf "$VERSION.tar.gz" .
sha256sum "$VERSION.tar.gz" >"$VERSION.tar.gz.sha256"
echo "package: $WORK/out/$VERSION.tar.gz"
