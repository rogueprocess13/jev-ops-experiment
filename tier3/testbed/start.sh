#!/usr/bin/env bash
# Start the kind node containers stopped by stop.sh, then wait for the nodes.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/pins.env"
"$HERE/precheck.sh"
docker start "${CLUSTER}-control-plane" "${CLUSTER}-worker" "${CLUSTER}-worker2" "${CLUSTER}-worker3"
KUBECONFIG="$HERE/kubeconfig" kubectl wait --for=condition=Ready nodes --all --timeout=5m
echo "nodes ready. Wait for the demo pods, then run ./health-check-k8s.sh"
