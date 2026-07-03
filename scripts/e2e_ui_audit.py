"""Repeatable UI audit runner for public and admin surfaces.

This script uses Microsoft Edge over the Chrome DevTools Protocol so the repo
can run UI checks without a committed Playwright dependency.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import dataclasses
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "app" / "backend"
FRONTEND_ROOT = REPO_ROOT / "app" / "frontend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.auth.security import hash_password  # noqa: E402
from src.db.session import async_session_factory  # noqa: E402
from src.models.user import User  # noqa: E402

from sqlalchemy import delete, func, select, update  # noqa: E402


DEFAULT_FORBIDDEN_TEXT = (
    "Internal Server Error",
    "Not authenticated",
    "Unauthorized",
    "Admin role required",
    "Choose File",
    "mm/dd",
    "release check",
    "Coverage",
    "Faithfulness",
    "FAILED",
    "golden evaluation",
    "observation",
    "review-only",
    "answerable",
    "parser",
    "blocker",
    "incident",
)

DEFAULT_MOJIBAKE_MARKERS = ("Ã¡", "Ã¢", "Ã£", "Ä‘", "Æ¡", "Æ°", "á»", "â€", "ðŸ")
DEFAULT_PLAIN_VIETNAMESE_MARKERS = ("Hieu luc tu",)
DEFAULT_ALLOWED_401_PREFIXES: tuple[str, ...] = ()

PUBLIC_VIEWS = (
    ("view-search", "search", "Tra cứu văn bản"),
    ("view-chat", "chat", "Hỏi đáp pháp luật"),
    ("view-alert", "alert", "Thông báo pháp luật"),
    ("view-bookmarks", "bookmarks", "Đã lưu"),
    ("view-login", "login", "Đăng nhập"),
    ("view-register", "register", "Đăng ký"),
)

ADMIN_VIEWS = (
    ("view-kb", "kb", "Kho văn bản"),
    ("view-hitl", "hitl", "Duyệt văn bản"),
    ("view-dashboard", "dashboard", "Chất lượng AI"),
    ("view-users", "users", "Người dùng"),
)

VIEWPORTS = (
    ("desktop", 1440, 1080, False),
    ("mobile", 390, 844, True),
)

PUBLIC_RESULTS_FILE = REPO_ROOT / "e2e-snapshots-live" / "ui-audit-results.json"
ADMIN_RESULTS_FILE = REPO_ROOT / "e2e-admin-snapshots" / "admin-ui-audit-results.json"


def _bool_env(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.strip() != ""


def detect_text_issues(
    text: str,
    *,
    forbidden_text: tuple[str, ...] = DEFAULT_FORBIDDEN_TEXT,
    mojibake_markers: tuple[str, ...] = DEFAULT_MOJIBAKE_MARKERS,
    plain_vietnamese_markers: tuple[str, ...] = DEFAULT_PLAIN_VIETNAMESE_MARKERS,
) -> list[str]:
    issues: list[str] = []
    lowered = text.lower()

    for phrase in forbidden_text:
        if phrase.lower() in lowered:
            issues.append(f"text_forbidden:{phrase}")

    for marker in mojibake_markers:
        if marker in text:
            issues.append(f"text_mojibake:{marker}")

    for marker in plain_vietnamese_markers:
        if marker.lower() in lowered:
            issues.append(f"text_plain_vietnamese:{marker}")

    return sorted(set(issues))


def detect_overlay_issues(snapshot: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if snapshot.get("has_next_badge"):
        issues.append("overlay:next-badge")
    if snapshot.get("has_next_portal"):
        issues.append("overlay:next-portal")
    if snapshot.get("visible_issue_badges"):
        issues.append("overlay:issue-badge")
    return issues


def detect_network_issues(
    entries: list[dict[str, Any]],
    *,
    allowed_401_prefixes: tuple[str, ...] = DEFAULT_ALLOWED_401_PREFIXES,
) -> list[str]:
    issues: list[str] = []
    for entry in entries:
        status = entry.get("status")
        url = str(entry.get("url") or "")
        if status is None:
            issues.append(f"network:no-status:{url}")
            continue
        if status == 401 and url.startswith(allowed_401_prefixes):
            continue
        if status >= 400:
            issues.append(f"network:{status}:{url}")
    return sorted(set(issues))


def _http_json(url: str, *, method: str = "GET") -> Any:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


async def wait_for_http_ok(url: str, *, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if 200 <= response.status < 400:
                    return
        except Exception as exc:  # pragma: no cover - exercised in live run
            last_error = exc
        await asyncio.sleep(0.25)
    raise RuntimeError(f"Service did not become ready: {url}") from last_error


@dataclasses.dataclass
class ManagedProcess:
    process: subprocess.Popen[str]
    stdout_path: Path
    stderr_path: Path

    def terminate(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)


def start_process(
    command: list[str],
    *,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    env: dict[str, str] | None = None,
) -> ManagedProcess:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
    )
    stdout_handle.close()
    stderr_handle.close()
    return ManagedProcess(process=process, stdout_path=stdout_path, stderr_path=stderr_path)


@dataclasses.dataclass
class AdminCredentialLease:
    email: str
    password: str
    user_id: str
    previous_last_login_at: Any | None
    bootstrap_created: bool


async def prepare_admin_lease(*, allow_bootstrap: bool) -> AdminCredentialLease:
    email = os.getenv("E2E_ADMIN_EMAIL", "").strip()
    password = os.getenv("E2E_ADMIN_PASSWORD", "").strip()

    async with async_session_factory() as session:
        if email and password:
            result = await session.execute(
                select(User.user_id, User.last_login_at).where(func.lower(User.email) == email.lower())
            )
            row = result.one_or_none()
            if row is None:
                raise RuntimeError("E2E_ADMIN_EMAIL does not match an existing user.")
            return AdminCredentialLease(
                email=email,
                password=password,
                user_id=row.user_id,
                previous_last_login_at=row.last_login_at,
                bootstrap_created=False,
            )

        if not allow_bootstrap:
            raise RuntimeError(
                "Missing E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD. "
                "Set both env vars or rerun with --bootstrap-admin-if-missing."
            )

        generated_email = f"e2e-admin-{int(time.time())}-{secrets.token_hex(4)}@example.test"
        generated_password = f"Tmp{secrets.token_hex(8)}A1"
        user = User(
            email=generated_email,
            username=f"E2E Admin {secrets.token_hex(3)}",
            password_hash=hash_password(generated_password),
            role="ADMIN",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return AdminCredentialLease(
            email=generated_email,
            password=generated_password,
            user_id=user.user_id,
            previous_last_login_at=user.last_login_at,
            bootstrap_created=True,
        )


async def rollback_admin_lease(lease: AdminCredentialLease | None) -> None:
    if lease is None:
        return
    async with async_session_factory() as session:
        if lease.bootstrap_created:
            await session.execute(delete(User).where(User.user_id == lease.user_id))
        else:
            await session.execute(
                update(User)
                .where(User.user_id == lease.user_id)
                .values(last_login_at=lease.previous_last_login_at)
            )
        await session.commit()


class CDPPage:
    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process
        self.next_id = 0
        self.pending: dict[int, asyncio.Future[Any]] = {}
        self.listener_task: asyncio.Task[None] | None = None
        self.load_event = asyncio.Event()
        self.network_entries: list[dict[str, Any]] = []
        self.console_entries: list[str] = []
        self.page_errors: list[str] = []
        self.session_id: str | None = None

    async def __aenter__(self) -> "CDPPage":
        self.listener_task = asyncio.create_task(self._listener())
        target = await self.send("Target.createTarget", {"url": "about:blank"})
        attached = await self.send(
            "Target.attachToTarget",
            {"targetId": target["targetId"], "flatten": True},
        )
        self.session_id = attached["sessionId"]
        await self.send("Page.enable", session_id=self.session_id)
        await self.send("Runtime.enable", session_id=self.session_id)
        await self.send("Network.enable", session_id=self.session_id)
        await self.send("Log.enable", session_id=self.session_id)
        await self.send(
            "Page.setLifecycleEventsEnabled",
            {"enabled": True},
            session_id=self.session_id,
        )
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        if self.listener_task is not None:
            self.listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.listener_task
        if self.session_id is not None:
            with contextlib.suppress(Exception):
                await self.send(
                    "Target.detachFromTarget",
                    {"sessionId": self.session_id},
                )

    async def _listener(self) -> None:
        assert self.process.stdout is not None
        while True:
            header = await self.process.stdout.readexactly(4)
            size = int.from_bytes(header, "little")
            payload = await self.process.stdout.readexactly(size)
            message = json.loads(payload.decode("utf-8"))
            if "id" in message:
                future = self.pending.pop(message["id"], None)
                if future is not None and not future.done():
                    if "error" in message:
                        future.set_exception(RuntimeError(str(message["error"])))
                    else:
                        future.set_result(message.get("result"))
                continue

            method = message.get("method")
            params = message.get("params", {})
            if message.get("sessionId") != self.session_id:
                continue
            if method == "Page.loadEventFired":
                self.load_event.set()
            elif method == "Network.responseReceived":
                response = params.get("response", {})
                self.network_entries.append(
                    {
                        "url": response.get("url"),
                        "status": int(response.get("status", 0)),
                        "mime_type": response.get("mimeType"),
                        "resource_type": params.get("type"),
                    }
                )
            elif method == "Network.loadingFailed":
                self.network_entries.append(
                    {
                        "url": params.get("url"),
                        "status": None,
                        "error_text": params.get("errorText"),
                        "resource_type": params.get("type"),
                    }
                )
            elif method == "Runtime.consoleAPICalled":
                args = params.get("args", [])
                rendered = " ".join(str(arg.get("value", "")) for arg in args if "value" in arg)
                if rendered:
                    self.console_entries.append(rendered)
            elif method == "Runtime.exceptionThrown":
                details = params.get("exceptionDetails", {})
                text = details.get("text") or "Runtime exception"
                self.page_errors.append(str(text))
            elif method == "Log.entryAdded":
                entry = params.get("entry", {})
                text = entry.get("text")
                if text:
                    self.page_errors.append(str(text))

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> Any:
        assert self.process.stdin is not None
        self.next_id += 1
        message_id = self.next_id
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self.pending[message_id] = future
        payload = {"id": message_id, "method": method, "params": params or {}}
        if session_id is not None:
            payload["sessionId"] = session_id
        encoded = json.dumps(payload).encode("utf-8")
        self.process.stdin.write(len(encoded).to_bytes(4, "little") + encoded)
        await self.process.stdin.drain()
        return await future

    async def navigate(self, url: str) -> None:
        self.load_event.clear()
        await self.send("Page.navigate", {"url": url}, session_id=self.session_id)
        await asyncio.wait_for(self.load_event.wait(), timeout=30)

    async def evaluate(self, expression: str, *, return_by_value: bool = True) -> Any:
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": return_by_value,
                "awaitPromise": True,
            },
            session_id=self.session_id,
        )
        return result.get("result", {}).get("value")

    async def wait_for_js(self, expression: str, *, timeout: float = 20.0) -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = await self.evaluate(expression)
            if value:
                return value
            await asyncio.sleep(0.1)
        raise RuntimeError(f"Timed out waiting for browser expression: {expression}")

    async def set_viewport(self, *, width: int, height: int, mobile: bool) -> None:
        await self.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": mobile,
                "screenWidth": width,
                "screenHeight": height,
            },
            session_id=self.session_id,
        )

    async def reset_network(self) -> None:
        self.network_entries = []
        self.console_entries = []
        self.page_errors = []

    async def capture_screenshot(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot = await self.send(
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": True},
            session_id=self.session_id,
        )
        output_path.write_bytes(base64.b64decode(screenshot["data"]))


async def wait_for_network_settle(page: CDPPage, *, idle_seconds: float = 1.0, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    previous_count = -1
    stable_since = time.monotonic()
    while time.monotonic() < deadline:
        current_count = len(page.network_entries)
        if current_count != previous_count:
            previous_count = current_count
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= idle_seconds:
            return
        await asyncio.sleep(0.1)


async def browser_snapshot(page: CDPPage) -> dict[str, Any]:
    script = """
(() => {
  const activeSection = document.querySelector('.view-section.active');
  const activeNav = Array.from(document.querySelectorAll('.nav-item.active span'))
    .map((node) => (node.textContent || '').trim())
    .filter(Boolean);
  const rootText = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim();
  const visibleIssueBadges = Array.from(document.querySelectorAll('body *'))
    .filter((node) => {
      if (!(node instanceof HTMLElement)) return false;
      if (node.offsetParent === null) return false;
      const text = (node.textContent || '').trim();
      return text === 'Issues' || /^\\d+ Issues?$/.test(text);
    })
    .map((node) => (node.textContent || '').trim());

  return {
    active_view_id: activeSection?.id || null,
    active_nav_labels: activeNav,
    page_title: document.title,
    text: rootText,
    has_next_portal: Boolean(document.querySelector('nextjs-portal')),
    has_next_badge: Boolean(document.querySelector('[data-next-badge-root], [data-nextjs-toast], [data-next-mark]')),
    visible_issue_badges: visibleIssueBadges,
  };
})()
"""
    return await page.evaluate(script)


async def set_active_view(page: CDPPage, view_id: str) -> None:
    await page.evaluate(
        f"window.dispatchEvent(new CustomEvent('app:navigate', {{ detail: {json.dumps(view_id)} }}));"
    )
    await page.wait_for_js(
        f"document.querySelector('.view-section.active')?.id === {json.dumps(view_id)}",
        timeout=20,
    )
    await wait_for_network_settle(page, idle_seconds=1.0, timeout=10.0)


async def perform_admin_login(page: CDPPage, lease: AdminCredentialLease) -> None:
    await set_active_view(page, "view-login")
    email = json.dumps(lease.email)
    password = json.dumps(lease.password)
    await page.evaluate(
        f"""
(() => {{
  const emailInput = document.querySelector('#view-login input[type="email"]');
  const passwordInput = document.querySelector('#view-login input[type="password"]');
  const submitButton = document.querySelector('#view-login .auth-submit');
  if (!(emailInput instanceof HTMLInputElement) || !(passwordInput instanceof HTMLInputElement) || !(submitButton instanceof HTMLButtonElement)) {{
    throw new Error('Login form is unavailable.');
  }}
  emailInput.focus();
  emailInput.value = {email};
  emailInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
  passwordInput.focus();
  passwordInput.value = {password};
  passwordInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
  submitButton.click();
}})();
"""
    )
    await page.wait_for_js(
        """
(() => {
  const stored = window.localStorage.getItem('legalai_auth');
  if (!stored) return false;
  try {
    const parsed = JSON.parse(stored);
    return parsed?.user?.role === 'ADMIN';
  } catch {
    return false;
  }
})()
""",
        timeout=20,
    )
    await wait_for_network_settle(page, idle_seconds=1.0, timeout=10.0)


async def clear_browser_auth(page: CDPPage) -> None:
    await page.evaluate(
        """
(() => {
  window.localStorage.removeItem('legalai_auth');
  window.dispatchEvent(new Event('legalai-auth-changed'));
  window.dispatchEvent(new CustomEvent('app:navigate', { detail: 'view-search' }));
})();
"""
    )
    await page.wait_for_js("document.querySelector('.view-section.active')?.id === 'view-search'")


async def record_view(
    page: CDPPage,
    *,
    output_dir: Path,
    viewport_name: str,
    width: int,
    height: int,
    mobile: bool,
    view_id: str,
    slug: str,
    expected_heading: str,
) -> dict[str, Any]:
    await page.set_viewport(width=width, height=height, mobile=mobile)
    await page.reset_network()
    await set_active_view(page, view_id)
    if view_id in {"view-kb", "view-hitl"}:
        await page.wait_for_js(
            f"""
(() => {{
  const view = document.querySelector('#{view_id}');
  if (!(view instanceof HTMLElement)) return false;
  const loading = Array.from(view.querySelectorAll('.kb-loading-copy'))
    .some((node) => node instanceof HTMLElement && node.offsetParent !== null);
  return !loading && !view.querySelector('.kb-list-skeleton');
}})()
""",
            timeout=20,
        )
        await wait_for_network_settle(page, idle_seconds=0.5, timeout=5.0)
    snapshot = await browser_snapshot(page)
    screenshot_path = output_dir / f"{viewport_name}-{slug}.png"
    await page.capture_screenshot(screenshot_path)

    issues = []
    issues.extend(detect_text_issues(snapshot["text"]))
    issues.extend(detect_overlay_issues(snapshot))
    issues.extend(detect_network_issues(page.network_entries))

    if snapshot.get("active_view_id") != view_id:
        issues.append(f"active-view:{snapshot.get('active_view_id')}!= {view_id}")
    if expected_heading and expected_heading not in snapshot["text"]:
        issues.append(f"missing-heading:{expected_heading}")

    return {
        "view_id": view_id,
        "slug": slug,
        "viewport": viewport_name,
        "width": width,
        "height": height,
        "mobile": mobile,
        "screenshot": str(screenshot_path),
        "active_view_id": snapshot.get("active_view_id"),
        "active_nav_labels": snapshot.get("active_nav_labels"),
        "network": page.network_entries,
        "console_entries": page.console_entries,
        "page_errors": page.page_errors,
        "issues": sorted(set(issues)),
    }


async def run_view_group(
    page: CDPPage,
    *,
    output_dir: Path,
    views: tuple[tuple[str, str, str], ...],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for viewport_name, width, height, mobile in VIEWPORTS:
        for view_id, slug, expected_heading in views:
            results.append(
                await record_view(
                    page,
                    output_dir=output_dir,
                    viewport_name=viewport_name,
                    width=width,
                    height=height,
                    mobile=mobile,
                    view_id=view_id,
                    slug=slug,
                    expected_heading=expected_heading,
                )
            )
    return results


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [result for result in results if result["issues"]]
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "items": results,
    }


def cleanup_previous_outputs() -> None:
    for directory in (REPO_ROOT / "e2e-snapshots-live", REPO_ROOT / "e2e-admin-snapshots"):
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.glob("*.png"):
            path.unlink(missing_ok=True)
        for path in directory.glob("*.json"):
            path.unlink(missing_ok=True)


def read_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "total": 0,
            "passed": 0,
            "failed": 0,
            "items": [],
            "missing": str(path),
        }
    return json.loads(path.read_text(encoding="utf-8"))


async def main_async(args: argparse.Namespace) -> int:
    public_output = REPO_ROOT / "e2e-snapshots-live"
    admin_output = REPO_ROOT / "e2e-admin-snapshots"
    public_output.mkdir(parents=True, exist_ok=True)
    admin_output.mkdir(parents=True, exist_ok=True)

    backend_process: ManagedProcess | None = None
    frontend_process: ManagedProcess | None = None
    edge_profile_dir = Path(tempfile.mkdtemp(prefix="legalai-edge-"))
    lease: AdminCredentialLease | None = None

    try:
        cleanup_previous_outputs()

        if args.start_backend:
            backend_process = start_process(
                [
                    str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"),
                    "-m",
                    "uvicorn",
                    "src.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.backend_port),
                ],
                cwd=BACKEND_ROOT,
                stdout_path=BACKEND_ROOT / "backend-e2e-out.log",
                stderr_path=BACKEND_ROOT / "backend-e2e-err.log",
                env=os.environ.copy(),
            )

        if args.start_frontend:
            frontend_process = start_process(
                [
                    "node",
                    "node_modules/next/dist/bin/next",
                    "start",
                    "-H",
                    "127.0.0.1",
                    "-p",
                    str(args.frontend_port),
                ],
                cwd=FRONTEND_ROOT,
                stdout_path=FRONTEND_ROOT / "frontend-e2e-out.log",
                stderr_path=FRONTEND_ROOT / "frontend-e2e-err.log",
                env=os.environ.copy(),
            )

        await wait_for_http_ok(f"http://127.0.0.1:{args.backend_port}/health", timeout=60.0)
        await wait_for_http_ok(f"http://127.0.0.1:{args.frontend_port}/", timeout=60.0)

        lease = await prepare_admin_lease(allow_bootstrap=args.bootstrap_admin_if_missing)
        env = os.environ.copy()
        env["E2E_ADMIN_EMAIL"] = lease.email
        env["E2E_ADMIN_PASSWORD"] = lease.password
        env["PLAYWRIGHT_FRONTEND_URL"] = f"http://127.0.0.1:{args.frontend_port}"
        env["PLAYWRIGHT_RESULTS_ROOT"] = str(REPO_ROOT)
        env["PLAYWRIGHT_DISABLE_HTML_REPORT"] = "1"
        playwright_command = [
            "node",
            "node_modules/@playwright/test/cli.js",
            "test",
            "-c",
            "playwright.config.ts",
        ]
        playwright = await asyncio.create_subprocess_exec(
            *playwright_command,
            cwd=str(FRONTEND_ROOT),
            env=env,
        )
        playwright_exit_code = await playwright.wait()

        public_summary = read_summary(PUBLIC_RESULTS_FILE)
        admin_summary = read_summary(ADMIN_RESULTS_FILE)

        total_failures = public_summary["failed"] + admin_summary["failed"]
        print(
            json.dumps(
                {
                    "public_failed": public_summary["failed"],
                    "admin_failed": admin_summary["failed"],
                    "public_result": str(PUBLIC_RESULTS_FILE),
                    "admin_result": str(ADMIN_RESULTS_FILE),
                    "playwright_exit_code": playwright_exit_code,
                },
                ensure_ascii=False,
            )
        )
        return 0 if playwright_exit_code == 0 and total_failures == 0 else 1
    finally:
        await rollback_admin_lease(lease)
        if frontend_process is not None:
            frontend_process.terminate()
        if backend_process is not None:
            backend_process.terminate()
        shutil.rmtree(edge_profile_dir, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run repeatable UI audit snapshots.")
    parser.add_argument(
        "--edge-path",
        default=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    )
    parser.add_argument("--edge-port", type=int, default=9222)
    parser.add_argument("--frontend-port", type=int, default=3017)
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--start-backend", action="store_true")
    parser.add_argument("--start-frontend", action="store_true")
    parser.add_argument("--bootstrap-admin-if-missing", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
