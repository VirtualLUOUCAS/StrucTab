"""
Shared base class for the ``ping_*.py`` service-health-check scripts.

Each concrete tester defines its service name, port range, route and a small
piece of test data; this base class loads the endpoint list from a JSON file
(a list of ``"ip:port"`` strings) and probes every endpoint in parallel.
"""

import json
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import requests


class ServiceTester(ABC):
    """Base class that probes a list of HTTP endpoints for a given service."""

    def __init__(self, service_name: str, start_port: int, end_port: int, router: str, request_timeout: int = 20):
        self.service_name = service_name
        self.start_port = start_port
        self.end_port = end_port
        self.router = router
        self.request_timeout = request_timeout
        self.workers = 50
        self._print_lock = Lock()

    @abstractmethod
    def get_test_data(self) -> dict:
        """Return the JSON payload used to probe an endpoint."""

    @abstractmethod
    def check_response_validity(self, response: dict) -> bool:
        """Return True iff the endpoint response is considered valid."""

    def get_success_message(self, response: dict) -> str:
        """Message printed when an endpoint passes (override to customize)."""
        return "OK"

    def load_endpoints(self, json_path: str) -> list[str]:
        """Load a list of ``"ip:port"`` endpoints from a JSON file."""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data or not all(":" in item for item in data):
            print("Invalid endpoint list: expected a list of 'ip:port' strings.")
            return []
        print(f"Loaded {len(data)} endpoints\n")
        return data

    def test_single(self, endpoint: str) -> tuple[str, bool, str]:
        """Probe a single endpoint and return (endpoint, is_available, message)."""
        url = f"http://{endpoint}{self.router}"
        try:
            resp = requests.post(url, json=self.get_test_data(), timeout=self.request_timeout)
            if resp.status_code != 200:
                return endpoint, False, f"HTTP {resp.status_code}"
            data = resp.json()
            if self.check_response_validity(data):
                return endpoint, True, self.get_success_message(data)
            return endpoint, False, "Invalid response content"
        except Exception as e:
            return endpoint, False, str(e)

    def test_all_servers(self, json_path: str) -> None:
        """Probe all endpoints listed in ``json_path`` in parallel."""
        endpoints = self.load_endpoints(json_path)
        if not endpoints:
            print("No endpoints to test.")
            return

        print(f"Testing {len(endpoints)} {self.service_name} endpoints ...")
        available, unavailable = [], []
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self.test_single, ep): ep for ep in endpoints}
            for future in as_completed(futures):
                endpoint, ok, msg = future.result()
                with self._print_lock:
                    if ok:
                        available.append(endpoint)
                        print(f"[OK]   {endpoint}: {msg}")
                    else:
                        unavailable.append(endpoint)
                        print(f"[FAIL] {endpoint}: {msg}")

        print(f"\nDone: {len(available)}/{len(endpoints)} endpoints available.")
