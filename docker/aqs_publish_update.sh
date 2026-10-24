#!/usr/bin/env bash
#
# Publish a firmware update to the Matter server's OTA provider and install it
# on the given sensor nodes, one at a time.
#
# SOURCE is the image path without its extension, local or scp style. The .ota
# image and its .json manifest next to it are copied into the provider
# directory, older images of the same variant are removed, and the Matter server
# is restarted, since it only reads the manifests at startup. Each node is then
# updated in turn, and the next one is only started once the previous one
# reports the new version, so a bad image stops at the first board.

set -euo pipefail

DOCKER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATES_DIR="$DOCKER_DIR/matter-server-data/updates"
CLIENT_CONTAINER="aqs_matter_client"
KEEP_OLD=0
SOAK_MINUTES=0

usage() {
    cat <<USAGE
Usage: ${0##*/} [options] SOURCE [NODE ...]

SOURCE   image without extension, e.g.
           paavo@pc:Projects/air-quality-sensor/firmware-esp32c6/bin/aqs_001/aqs_001-1.2.0
           ./aqs_001-1.2.0
         The .ota and .json next to it are both needed.
NODE     Matter node ids to update, in order. With none, the image is only
         published: the server's OTA provider runs only while it pushes an
         update, so sensors do not fetch one on their own.

Options:
  -k          keep older images of the same variant in the provider directory
  -s MINUTES  wait this long between nodes, to watch one before the next
  -h          this help

Examples:
  ${0##*/} paavo@pc:Projects/air-quality-sensor/firmware-esp32c6/bin/aqs_001/aqs_001-1.2.0 3 4
  ${0##*/} -s 30 ./aqs_001-1.2.0 3 4
USAGE
}

die() { echo "error: $*" >&2; exit 1; }

while getopts ":ks:h" opt; do
    case "$opt" in
        k) KEEP_OLD=1 ;;
        s) SOAK_MINUTES="$OPTARG" ;;
        h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
shift $((OPTIND - 1))

[[ $# -ge 1 ]] || { usage >&2; exit 2; }
[[ $SOAK_MINUTES =~ ^[0-9]+$ ]] || die "-s takes whole minutes"
SOURCE="${1%.ota}"
SOURCE="${SOURCE%.json}"
shift
NODES=("$@")

STAGING="$(mktemp -d)"
trap 'rm -rf -- "$STAGING"' EXIT

IMAGE_NAME="$(basename "${SOURCE#*:}")"
echo "=== Fetching $IMAGE_NAME ==="
if [[ $SOURCE == *:* && $SOURCE != /* && $SOURCE != ./* ]]; then
    scp "$SOURCE.ota" "$SOURCE.json" "$STAGING/"
else
    cp "$SOURCE.ota" "$SOURCE.json" "$STAGING/"
fi

# Check the manifest describes this very image before the server is restarted
# around it: the right file name, and a checksum that survived the copy.
MANIFEST_INFO="$(python3 - "$STAGING/$IMAGE_NAME.json" "$STAGING/$IMAGE_NAME.ota" <<'PY'
import base64, hashlib, json, sys
manifest = json.load(open(sys.argv[1]))["modelVersion"]
image = open(sys.argv[2], "rb").read()
name = sys.argv[2].rsplit("/", 1)[-1]
if manifest["otaUrl"] != f"file:///{name}":
    sys.exit(f"manifest otaUrl {manifest['otaUrl']} does not name {name}")
if base64.b64encode(hashlib.sha256(image).digest()).decode() != manifest["otaChecksum"]:
    sys.exit("image checksum does not match the manifest")
print(manifest["softwareVersion"], manifest["softwareVersionString"], hex(manifest["pid"]))
PY
)"
read -r VERSION VERSION_STRING PRODUCT_ID <<<"$MANIFEST_INFO"
echo "Version $VERSION_STRING ($VERSION) for product ID $PRODUCT_ID."

# The Matter server container owns its data directory, so it may need root.
SUDO=""
if ! mkdir -p "$UPDATES_DIR" 2>/dev/null || [[ ! -w $UPDATES_DIR ]]; then
    SUDO="sudo"
    $SUDO mkdir -p "$UPDATES_DIR"
fi

VARIANT="${IMAGE_NAME%%-*}"
if [[ $KEEP_OLD -eq 0 && -n $VARIANT ]]; then
    while IFS= read -r -d '' old; do
        echo "Removing older image $(basename "$old")"
        $SUDO rm -f -- "$old"
    done < <(find "$UPDATES_DIR" -maxdepth 1 -type f \( -name "$VARIANT-*.ota" -o -name "$VARIANT-*.json" \) \
                 ! -name "$IMAGE_NAME.ota" ! -name "$IMAGE_NAME.json" -print0)
fi

$SUDO cp "$STAGING/$IMAGE_NAME.ota" "$STAGING/$IMAGE_NAME.json" "$UPDATES_DIR/"
echo "Published to $UPDATES_DIR."

echo "=== Restarting matter-server ==="
docker compose -f "$DOCKER_DIR/docker-compose.yml" restart matter-server

if [[ ${#NODES[@]} -eq 0 ]]; then
    echo "No nodes given, published only. Run again with node ids to install it."
    exit 0
fi

for i in "${!NODES[@]}"; do
    node="${NODES[$i]}"
    if [[ $i -gt 0 && $SOAK_MINUTES -gt 0 ]]; then
        echo "=== Waiting $SOAK_MINUTES min before the next node ==="
        sleep $((SOAK_MINUTES * 60))
    fi
    echo "=== Updating node $node ==="
    if ! docker exec "$CLIENT_CONTAINER" python -u aqs_matter_update.py update "$node" "$VERSION"; then
        die "node $node did not end up on $VERSION_STRING, not updating the remaining nodes"
    fi
done

echo "=== All nodes on $VERSION_STRING ==="
