"""Native HTTP boundary checks on disposable random loopback ports only."""
import platform
import json
import socketserver
import subprocess
import tempfile
import threading
from pathlib import Path

root = Path(__file__).resolve().parents[1]
capabilities = [
    "after-class-checkin", "calendar-course-entry", "pet-state", "schedule-reminders",
    "planning-constraints-once", "timetable-recognition", "timetable-text", "planning-today",
    "course-changes", "execution-timers-v1", "profiles-v1", "goals-v1", "weekly-review-v1",
    "planning-core-v1", "b-interaction-v1", "project-completion-v1",
]

class FixtureServer(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def __init__(self, scenario):
        self.scenario = scenario
        self.requests = []
        self.done = threading.Event()
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        assert self.server_address[1] != 5173


class FixtureHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = self.request.recv(4096)
                if not chunk:
                    return
                data += chunk
            self.server.requests.append(data)
            scenario = self.server.scenario
            if scenario == "timeout":
                self.server.done.wait(8)
                return
            identity = {"application": "campus-companion", "mode": "local", "capabilities": capabilities}
            status, extra = 200, b""
            if scenario == "application":
                identity["application"] = "other"
            if scenario == "mode":
                identity["mode"] = "shared"
            if scenario == "capability" or (scenario == "cache" and len(self.server.requests) == 2):
                identity["capabilities"] = capabilities[:-1]
            if scenario == "status":
                status = 503
            if scenario == "redirect":
                status = 302
                extra = b"Location: /redirected\r\n"
            body = b"invalid JSON" if scenario == "malformed" else json.dumps(identity).encode()
            cache = b"max-age=600" if scenario == "cache" else b"no-store"
            self.request.sendall(
                f"HTTP/1.1 {status} Test\r\nContent-Length: {len(body)}\r\n".encode()
                + b"Connection: keep-alive\r\nCache-Control: " + cache
                + b"\r\nSet-Cookie: selected_profile=transport-fixture; Path=/\r\n" + extra + b"\r\n" + body
            )
            # Do not read again: pooled connections stall, fresh ones stay healthy.
            self.server.done.wait(8)
        except OSError:
            pass


output = root / "build/health-transport-tests"
output.mkdir(parents=True, exist_ok=True)
binary = output / "HealthProbe"
# A stable path lets a user approve this project's loopback-only host once,
# instead of receiving a different firewall identity for every temporary folder.
# Compile aside and replace atomically, preserving the prior host on build error.
with tempfile.TemporaryDirectory(prefix=".compile-", dir=output) as temporary:
    staged_binary = Path(temporary) / "HealthProbe"
    sources = [root / "Sources/ServiceController.swift"]
    helper = root / "Sources/LocalHealthTransport.swift"
    if helper.exists():
        sources.append(helper)
    subprocess.run([
        "xcrun", "swiftc", "-parse-as-library", "-swift-version", "5", "-module-cache-path", str(output / "cache"),
        "-target", platform.machine() + "-apple-macosx13.0", "-framework", "AppKit",
        *map(str, sources), str(root / "tests/HealthTransportTests.swift"), "-o", str(staged_binary),
    ], check=True)
    staged_binary.replace(binary)
    print(f"Native health host: {binary}", flush=True)
    failures = []
    for scenario in ("origins", "stale", "cache", "application", "mode", "capability", "status", "malformed", "redirect", "timeout"):
        with FixtureServer(scenario) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            native_scenario = "reject" if scenario in {"application", "mode", "capability", "status", "malformed", "redirect"} else scenario
            try:
                result = subprocess.run([
                    str(binary), str(server.server_address[1]), native_scenario,
                ], capture_output=True, text=True, timeout=10)
                print(f"{scenario}: {result.stdout.strip()}")
                if result.returncode:
                    failures.append(scenario)
                    if result.stderr:
                        print(result.stderr.strip())
                else:
                    expected = 0 if scenario == "origins" else (2 if scenario in {"stale", "cache"} else 1)
                    valid = len(server.requests) == expected
                    valid = valid and all(b"\r\ncookie:" not in request.lower() for request in server.requests)
                    valid = valid and all(request.startswith(b"GET /api/healthz HTTP/1.1\r\n") for request in server.requests)
                    if not valid:
                        print(f"FAIL {scenario}: server observed {len(server.requests)} requests, expected {expected}; no redirect, retry or profile cookies allowed")
                        failures.append(scenario)
            finally:
                server.done.set()
                server.shutdown()
    if failures:
        raise SystemExit("Native health scenarios failed: " + ", ".join(failures))
    print("Native health transport checks passed (10 scenarios)")
