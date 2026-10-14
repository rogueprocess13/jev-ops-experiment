"""Tier 3 testbed helpers: where the kind cluster's endpoints are, health checks.

Host ports come from tier3/testbed/kind.yaml (extraPortMappings) and the NodePorts
in tier3/testbed/values/. They differ from Tier 2's so the two are never confused.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent
TESTBED = ROOT / "testbed"
VERSION_FILE = TESTBED / "VERSION"
# Deployments the fault catalogue addresses by name (fault targets and replica_overload).
REQUIRED_DEPLOYMENTS = ("cart", "valkey-cart", "load-generator")


def kubeconfig() -> str:
    return os.environ.get("TIER3_KUBECONFIG", str(TESTBED / "kubeconfig"))


def namespace() -> str:
    return os.environ.get("TIER3_NAMESPACE", "otel-demo")


def base_url() -> str:
    """frontend-proxy (Envoy): frontend, /jaeger/ui, /loadgen, /feature."""
    return os.environ.get("TIER3_BASE_URL", "http://localhost:18080")


def prometheus_url() -> str:
    return os.environ.get("TIER3_PROMETHEUS_URL", "http://localhost:19090")


def opensearch_url() -> str:
    return os.environ.get("TIER3_OPENSEARCH_URL", "http://localhost:19200")


def versions() -> dict:
    """key=value lines written by tier3/testbed/install.sh from the running cluster."""
    if not VERSION_FILE.exists():
        return {}
    out = {}
    for line in VERSION_FILE.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def _get(url: str, timeout: float = 8.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def run_checks(kube, prom, jaeger, workload, injector, os_url: str | None = None,
               now: float | None = None, get=_get) -> list[Check]:
    """Nodes, deployments, Prometheus, span metrics, Jaeger, OpenSearch, Locust,
    leftovers (in order)."""
    from tier3.collectors.kube import deployment_rows

    now = now or time.time()
    checks: list[Check] = []

    def check(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 - a failed check is a result, not a crash
            ok, detail = False, f"{type(e).__name__}: {e}"
        checks.append(Check(name, bool(ok), detail))

    def nodes():
        items = kube.list_nodes()
        bad = [n["metadata"]["name"] for n in items
               if not any(c.get("type") == "Ready" and c.get("status") == "True"
                          for c in (n.get("status") or {}).get("conditions") or [])]
        return (len(items) == 4 and not bad,
                f"{len(items)} nodes" + (f", not Ready: {', '.join(bad)}" if bad else ""))

    def deployments():
        raw = kube.list_deployments()
        missing = sorted(set(REQUIRED_DEPLOYMENTS) - {d["metadata"]["name"] for d in raw})
        if missing:
            return False, f"missing deployments: {', '.join(missing)} (chart naming changed?)"
        rows = deployment_rows(raw)
        bad = [f"{n} {r['available']}/{r['desired']}" for n, r in sorted(rows.items())
               if r["available"] < r["desired"] or r["desired"] == 0]
        return (bool(rows) and not bad,
                f"{len(rows)} app deployments" + (f", not available: {', '.join(bad)}" if bad else ""))

    def leftovers():
        left = injector.leftovers()
        return (not left, "none" if not left else
                f"{'; '.join(left)} (run: python -m tier3 reset-faults)")

    check("nodes", nodes)
    check("deployments", deployments)
    check("prometheus", lambda: ((s := get(prometheus_url() + "/-/ready")[0]) == 200, f"HTTP {s}"))
    check("span-metrics", lambda: (prom.span_metrics_present(now), "traces_span_metrics_calls_total"))
    check("jaeger", lambda: (bool(jaeger.services()), f"{len(jaeger.services())} services"))
    check("opensearch", lambda: (
        json.loads(get((os_url or opensearch_url()) + "/_cluster/health")[1]).get("status") in
        ("green", "yellow"), "cluster health"))
    check("locust", lambda: (workload.require_running() > 0, "load generator running"))
    check("leftovers", leftovers)
    return checks
