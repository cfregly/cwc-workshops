#!/usr/bin/env python3
"""Check the SRE workshop setup. By default, run only local checks."""

import argparse
import ast
from datetime import datetime
import importlib.util
import io
import json
import math
import os
import re
import subprocess
import sys
import warnings
from importlib import metadata
from pathlib import Path


PACKAGES = {
    "anthropic": ("anthropic", "1.0.0"),
    "streamlit": ("streamlit", "1.65.0"),
    "plotly": ("plotly", "7.1.0"),
    "python-dotenv": ("dotenv", "1.2.4"),
}
FIRST_PARTY_URL = "https://api.anthropic.com"
API_OVERRIDES = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS")
WORKSHOP_FILES = (
    "requirements.lock.txt", "agent.py", "agent_complete.py", "app.py", "provided.py", "ui.py",
    "pages/1_Metrics.py", "pages/2_Logs.py", "pages/3_Deploys.py",
    "assets/style.css", "data/generate_log.py", "data/metrics.json",
    "data/deploys.json", "data/diff.txt", "incident-triage-runbook/SKILL.md",
)
CHECKPOINTS = {
    "setup_agent": "Save one complete function and look for the agent and skill IDs in the dashboard.",
    "setup_environment": "After saving, look for the environment ID below the agent and skill IDs.",
    "upload_log": "Wait for the upload to return a file ID. Use the synthetic data/app.log.",
    "start_session": "Bind the agent, environment and uploaded file IDs, and mount app.log. Click + once and look for the new session ID.",
    "stream_reply": "Open the event stream before sending the message. Finish handle_tool before submitting.",
    "handle_tool": "Compare the request to the schema in provided.py. For checkout p99, expect service=checkout and metric=p99_latency_ms.",
    "delete_session": "After your turn finishes, check the full session ID before clicking delete once.",
}


def check_packages(root, check):
    try:
        lines = (root / "requirements.txt").read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        check(False, "Cannot read requirements.txt from this checkout.")
        return

    pins = {}
    for line in lines:
        pin = line.split("#", 1)[0].strip()
        if not pin:
            continue
        match = re.fullmatch(r"([a-zA-Z0-9-]+)==([a-zA-Z0-9.]+)", pin)
        if not match or match[1] in pins:
            check(False, "requirements.txt has an unpinned or duplicate entry.")
            return
        pins[match[1]] = match[2]
    expected_pins = {name: version for name, (_, version) in PACKAGES.items()}
    if pins != expected_pins:
        check(False, "Restore requirements.txt from the pinned workshop checkout.")
        return
    check(True, "Workshop requirements match the release pins.")

    for name, (module, version) in PACKAGES.items():
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            check(False, f"{name} is missing. Expected {version}.")
            continue
        if not check(dist.version == version, f"{name} {dist.version}, expected {version}."):
            continue

        spec = importlib.util.find_spec(module)
        expected = Path(dist.locate_file(f"{module}/__init__.py")).resolve()
        origin = spec.origin if spec else None
        if not origin or Path(origin).resolve() != expected:
            check(False, f"{module} resolves outside its installed package. Check for a file or folder with that name.")
            continue
        try:
            importlib.import_module(module)
        except Exception as exc:
            check(False, f"Cannot import {module} ({type(exc).__name__}). Reinstall the pins in a fresh .venv.")


def check_key(root, check):
    from dotenv.parser import parse_stream

    settings = {}
    path = root / ".env"
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = ""
    except (OSError, UnicodeError):
        check(False, "Cannot read .env as UTF-8.")
        return None
    if content.startswith("\ufeff"):
        check(False, "Save .env as UTF-8 without a BOM.")
        return None
    for binding in parse_stream(io.StringIO(content)):
        if binding.error:
            check(False, f"Fix the .env syntax on line {binding.original.line}.")
            return None
        if binding.key is not None:
            settings[binding.key] = binding.value
    if any(os.environ.get(name) or settings.get(name) for name in API_OVERRIDES):
        check(False, "Remove API endpoint, auth token, or custom header overrides from this lab shell and .env.")
        return None
    shell_key = os.environ.get("ANTHROPIC_API_KEY")
    file_key = settings.get("ANTHROPIC_API_KEY")
    if shell_key is not None and shell_key.strip() in ("", "sk-ant-..."):
        check(False, "Clear the blank or placeholder shell API key, or set it to the issued key.")
        return None
    if shell_key is not None and file_key not in (None, "", "sk-ant-...", shell_key):
        check(False, "A different shell API key overrides .env. Clear it if you intend to use .env.")
        return None
    if shell_key is None and not path.is_file():
        check(False, "No shell key or readable .env. Check the exact filename, including hidden extensions.")
        return None
    if shell_key is None and os.environ.get("PYTHON_DOTENV_DISABLED", "").lower() in {"1", "true", "t", "yes", "y"}:
        check(False, "Enable dotenv to use the key in .env.")
        return None
    key = file_key if shell_key is None else shell_key
    if (not key or key == "sk-ant-..." or not key.isascii() or not key.isprintable()
            or "${" in key or any(char.isspace() for char in key)):
        check(False, "Paste the issued workshop key directly, without spaces, formatting or variable substitution.")
        return None
    check(True, "Workshop key found in .env." if shell_key is None else "Using the shell API key.")
    return key


def check_access(key):
    import anthropic

    try:
        with anthropic.Anthropic(api_key=key, base_url=FIRST_PARTY_URL, max_retries=0) as client:
            page = client.beta.environments.list(limit=1)
    except anthropic.APIStatusError as exc:
        print(f"FIX   Managed Agents read check returned HTTP {exc.status_code}.")
        if exc.status_code == 401:
            print("Check the key privately and look for a stale shell override.")
        elif exc.status_code == 403:
            print("Ask the workshop access owner to verify permission for the key's workspace.")
        elif exc.status_code == 429:
            print("The API rate limited the read. Follow any retry instructions before rerunning.")
        elif exc.status_code >= 500:
            print("The API returned a server error. Check service status before rerunning.")
        else:
            print("See Troubleshooting in the README.")
        request_id = getattr(exc, "request_id", None)
        if request_id and re.fullmatch(r"req_[A-Za-z0-9_-]+", request_id):
            print(f"Request ID: {request_id}")
        return False
    except anthropic.APIConnectionError:
        print("FIX   Could not connect to the Claude API. Check the workshop network.")
        return False
    except (AttributeError, TypeError, ValueError):
        page = None
    if not isinstance(getattr(page, "data", None), list):
        print("FIX   The Claude API read returned an unexpected response. Check your network or proxy.")
        return False
    print("OK    Managed Agents read access. Resource creation and model access are separate.")
    return True


def is_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def valid_metrics(data):
    if not isinstance(data, dict) or "checkout" not in data:
        return False
    if not isinstance(data["checkout"], dict) or not {"p99_latency_ms", "error_rate", "db_pool_utilization"} <= data["checkout"].keys():
        return False
    for service in data.values():
        if not isinstance(service, dict):
            return False
        for series in service.values():
            if not isinstance(series, list) or not series:
                return False
            for row in series:
                if not isinstance(row, dict) or not is_timestamp(row.get("ts")):
                    return False
                value = row.get("value")
                try:
                    if type(value) not in (int, float) or not math.isfinite(value):
                        return False
                except OverflowError:
                    return False
    return data["checkout"]["p99_latency_ms"][0]["value"] > 0


def valid_deploys(data):
    return isinstance(data, list) and bool(data) and all(
        isinstance(row, dict) and is_timestamp(row.get("ts"))
        and all(isinstance(row.get(field), str) for field in ("service", "commit", "author"))
        for row in data
    )


def is_stub(node):
    for statement in node.body:
        if isinstance(statement, ast.Raise):
            error = statement.exc
            if isinstance(error, ast.Call):
                error = error.func
            if isinstance(error, ast.Name) and error.id == "NotImplementedError":
                return True
    return False


def check_workshop_files(root, check):
    missing = [name for name in WORKSHOP_FILES if not (root / name).is_file()]
    if not check(not missing, "Missing workshop files: " + ", ".join(missing) if missing else "Workshop files found."):
        return

    for name in ("assets/style.css", "data/diff.txt", "incident-triage-runbook/SKILL.md"):
        try:
            (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            check(False, f"{name} is unreadable or has invalid UTF-8. Restore it from the pinned checkout.")

    for name, valid in (("data/metrics.json", valid_metrics), ("data/deploys.json", valid_deploys)):
        try:
            data = json.loads((root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RecursionError):
            check(False, f"{name} is unreadable or contains invalid UTF-8 JSON. Restore the fixture.")
        else:
            check(valid(data), f"{name} must match the workshop fixture structure.")

    try:
        source = (root / "agent.py").read_bytes()
        with warnings.catch_warnings():
            # Python can echo the source line in warnings. Keep the report to line numbers.
            warnings.simplefilter("ignore")
            compile(source, "agent.py", "exec", dont_inherit=True)
            tree = ast.parse(source, filename="agent.py")
    except SyntaxError as exc:
        check(False, f"agent.py has a syntax error on line {exc.lineno}.")
    except (OSError, UnicodeError):
        check(False, "Cannot read agent.py.")
    else:
        functions = {}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in CHECKPOINTS:
                if node.name in functions:
                    check(False, f"{node.name} is defined twice. Keep one definition.")
                functions[node.name] = node
        missing = [name for name in CHECKPOINTS if name not in functions]
        if missing:
            check(False, "Missing synchronous function definitions: " + ", ".join(missing))
        stubs = [name for name, node in functions.items() if is_stub(node)]
        next_step = next((name for name in CHECKPOINTS if name in stubs or name in missing), None)
        if next_step:
            print(f"NEXT  {next_step}(): {CHECKPOINTS[next_step]}")
        elif not missing:
            print("NOTE  All seven functions are present. Verify what they do in the dashboard.")

    log = root / "data" / "app.log"
    try:
        lines = 0
        with log.open(encoding="utf-8") as stream:
            for lines, line in enumerate(stream, 1):
                row = json.loads(line)
                if not isinstance(row, dict) or not all(isinstance(row.get(field), str) for field in ("ts", "msg", "level", "service")):
                    raise ValueError
        check(lines == 69740, f"data/app.log has {lines} lines. The workshop fixture has 69740.")
    except FileNotFoundError:
        print("NOTE  data/app.log is missing. The README and first dashboard launch can generate it.")
    except OSError:
        check(False, "Cannot read data/app.log.")
    except (UnicodeError, ValueError, RecursionError):
        check(False, "data/app.log contains invalid fixture rows. Regenerate it using the README command.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", action="store_true", help="run local checks, then start the dashboard")
    parser.add_argument("--check-access", action="store_true", help="check Managed Agents read access using the workshop key")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    failed = False

    def check(condition, message):
        nonlocal failed
        print(f"{'OK  ' if condition else 'FIX '}  {message}")
        failed |= not condition
        return condition

    version = sys.version.split()[0]
    print(f"Python {version} at {sys.executable}")
    try:
        pinned_version = (root / ".python-version").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        pinned_version = ""
    if re.fullmatch(r"\d+\.\d+\.\d+", pinned_version) is None:
        print("FIX   Restore .python-version from the workshop checkout.")
        return 1
    if not check(version == pinned_version,
                 f"Python {version} matches the workshop pin." if version == pinned_version
                 else f"Expected Python {pinned_version}. Recreate .venv using the README."):
        return 1
    check(Path.cwd().resolve() == root, "Run from the workshop folder that contains app.py.")
    check(Path(sys.prefix).resolve() == (root / ".venv").resolve(),
          "Use this workshop's .venv Python as shown in the README.")
    check_packages(root, check)
    check_workshop_files(root, check)
    key = check_key(root, check) if not failed else None

    if failed:
        print("Use Troubleshooting in the README, then rerun this command.")
        return 1
    pip = [sys.executable, "-I", "-m", "pip", "--disable-pip-version-check"]
    pip_env = {name: value for name, value in os.environ.items() if not name.upper().startswith("PIP_")}
    pip_env["PIP_CONFIG_FILE"] = os.devnull
    if subprocess.call(pip + ["check"], env=pip_env):
        print("FIX   Reinstall the locked requirements in this venv before continuing.")
        return 1
    if subprocess.call(pip + ["install", "--dry-run", "--no-index", "--require-hashes", "--quiet",
                              "-r", "requirements.lock.txt"], env=pip_env):
        print("FIX   Installed packages do not match requirements.lock.txt. Reinstall using the README.")
        return 1
    print("OK    Installed packages match the dependency lock.")
    if args.check_access or args.launch:
        if key is None:
            return 1
        if args.check_access and not check_access(key):
            return 1
        if not args.launch:
            return 0

        # Give Streamlit only the intended key and prevent dotenv's parent search.
        env = os.environ.copy()
        for name in API_OVERRIDES:
            env.pop(name, None)
        env.update(ANTHROPIC_API_KEY=key, ANTHROPIC_BASE_URL=FIRST_PARTY_URL, PYTHON_DOTENV_DISABLED="1")
        print("Starting the dashboard with this Python. Open the URL it prints.", flush=True)
        try:
            return subprocess.call([
                sys.executable, "-m", "streamlit", "run", "app.py",
                "--server.address", "127.0.0.1", "--server.headless", "true",
                "--server.showEmailPrompt", "false", "--browser.gatherUsageStats", "false",
            ], env=env)
        except KeyboardInterrupt:
            return 130
    print("Local checks passed. See the README for dashboard launch and live session checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
