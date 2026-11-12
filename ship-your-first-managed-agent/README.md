<!-- Copyright 2026 Anthropic PBC -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Incident-2277

> **Workshop sample.** Adapted from Gagan Bhat's SRE workshop. [Original workshop](https://github.com/anthropics/cwc-workshops/tree/068b84bb03d2ae87c51edb2837dda25c84c1d686/ship-your-first-managed-agent)

> **It's 2am. PagerDuty fires: checkout p99 latency spikes.**
> You know the drill. Open the dashboard, grep logs, scroll deploys, guess,
> check, repeat. Which commit caused the spike?

A working incident dashboard for a fictional e-commerce stack. The Metrics,
Logs, and Deploys pages run from mock data. The **Investigation** page opens
first and gives the SRE Agent and its tool calls the full width. It starts offline.
Bring it online with seven small functions in `agent.py` using
[Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview).

When you're done, ask it *"what caused the latency spike?"* and watch it grep
a 70k-line log inside its cloud sandbox, call your local tools to pull metrics
and deploys, correlate the timestamps, and inspect the candidate diff.

## Setup

For the live lab, you need **Python 3** and an Anthropic API key from Claude Console or your instructor. The setup below uses uv to create the workshop environment with **Python 3.10.20**, the tested version pinned for this lab. Clone from a fresh parent folder to avoid reusing an older checkout. [API keys](https://platform.claude.com/settings/keys)

```bash
git clone --branch gagan-sre-workshop --single-branch https://github.com/cfregly/cwc-workshops.git cwc-workshops/
```

After the clone succeeds, open the workshop folder.

```bash
cd cwc-workshops/ship-your-first-managed-agent
git branch --show-current
git rev-parse HEAD
```

Expect the branch `gagan-sre-workshop`. Keep the full commit SHA printed by `git rev-parse HEAD` so you can identify your exact checkout. If your instructor gives you a commit SHA, check that it matches.

### Create the virtual environment

Run these commands from `ship-your-first-managed-agent`, the folder containing `requirements.txt`. The [Python pin](.python-version) tells uv which interpreter to use for this workshop's `.venv`. Activating `.venv` makes that Python available as `python` in the current shell.

**macOS or Linux (zsh or Bash)**

If `.venv` already exists, run `.venv/bin/python --version`. If it reports `Python 3.10.20`, reuse it and skip to the package installation below. If the check fails or reports a different version, open a fresh terminal in the workshop folder and move the old environment aside.

```bash
mv .venv ".venv-backup-$(date +%Y%m%d-%H%M%S)"
```

Try your existing uv to create `.venv`.

```bash
uv venv --python 3.10.20 --managed-python .venv
```

If uv is missing or cannot obtain Python 3.10.20, install uv 0.13.7 into the workshop's `.workshop-uv` folder and run that binary directly. [Astral's unmanaged installer](https://docs.astral.sh/uv/reference/installer/#unmanaged-installations)

```bash
curl -LsSf https://astral.sh/uv/0.13.7/install.sh | UV_UNMANAGED_INSTALL="$PWD/.workshop-uv" sh
./.workshop-uv/uv venv --python 3.10.20 --managed-python .venv
```

Check that the environment reports `Python 3.10.20`. Then prepare pip and install the locked packages using that interpreter.

```bash
.venv/bin/python --version
.venv/bin/python -m ensurepip && .venv/bin/python -m pip install --require-hashes -r requirements.lock.txt
```

If you prefer to activate the environment, run `source .venv/bin/activate` and then use `python`. Run `deactivate` to leave it.

**Windows PowerShell (x64)**

If `.venv` already exists, run `& .\.venv\Scripts\python.exe --version`. If it reports `Python 3.10.20`, reuse it and skip to the package installation below. If the check fails or reports a different version, open a fresh PowerShell window in the workshop folder and move the old environment aside.

```powershell
Rename-Item -LiteralPath .venv -NewName ('.venv-backup-' + (Get-Date -Format yyyyMMdd-HHmmss))
```

Try your existing uv to create `.venv`.

```powershell
uv venv --python 3.10.20 --managed-python .venv
```

If uv is missing or cannot obtain Python 3.10.20, install uv 0.13.7 into the workshop's `.workshop-uv` folder and run that binary directly. [Astral's unmanaged installer](https://docs.astral.sh/uv/reference/installer/#unmanaged-installations)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command {
    $env:UV_UNMANAGED_INSTALL = Join-Path $PWD.Path '.workshop-uv'
    irm https://astral.sh/uv/0.13.7/install.ps1 | iex
}
& .\.workshop-uv\uv.exe venv --python 3.10.20 --managed-python .venv
```

Check that the environment reports `Python 3.10.20`. Then prepare pip and install the locked packages using that interpreter.

```powershell
& .\.venv\Scripts\python.exe --version
& .\.venv\Scripts\python.exe -m ensurepip
if ($LASTEXITCODE -eq 0) { & .\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock.txt }
```

If you prefer to activate the environment, run `.\.venv\Scripts\Activate.ps1` and then use `python`. Run `deactivate` to leave it.

The lock pins the workshop packages and their dependencies by version and verifies downloaded wheels against recorded hashes. Anthropic SDK 1.0.0 supports the workshop's `display_title` argument when uploading the skill. [Direct requirements](requirements.txt) · [Dependency lock](requirements.lock.txt) · [Skills API compatibility](https://platform.claude.com/docs/en/build-with-claude/skills-guide#migrate-from-skills-2025-10-02)

### Set the key privately

Create `.env` from the example only if `.env` is missing.

**macOS or Linux**

```bash
if [ ! -e .env ]; then
  cp -n .env.example .env
fi
```

**Windows PowerShell**

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    New-Item -Path .env -ItemType File -Value (Get-Content -Raw -LiteralPath .env.example) | Out-Null
}
```

Open `.env` privately and set `ANTHROPIC_API_KEY` to the intended key. If your shell already has a different API key, clear it before running the checker. Keep the value out of chat and off the shared screen.

### Check setup and start the dashboard

Run the checker with the venv Python. It checks the pinned Python and packages, verifies that the SDK accepts `display_title`, and flags edited resource functions with no value return. Verify the resource IDs in the dashboard. The command below also generates and validates a missing synthetic log, checks Managed Agents read access, and opens the dashboard. Keep the key off screen.

**macOS or Linux**

```bash
.venv/bin/python check_setup.py --check-access --launch
```

**Windows PowerShell**

```powershell
& .\.venv\Scripts\python.exe check_setup.py --check-access --launch
```

Open the **URL** Streamlit prints. The Investigation page says the SRE Agent is offline and asks you to implement `setup_agent()` in `agent.py`. Expand **Diagnostics** to see the workshop folder, Python executable, and Anthropic SDK version used by the dashboard. If you are waiting for a key or the access check fails, [check a fixture while access is blocked](#check-a-fixture-while-access-is-blocked). For other errors, open [Troubleshooting](#troubleshooting).

## What you build

Open **`agent.py`**. Seven functions, each starting with `raise NotImplementedError`.
Fill them in and the panel comes online one step at a time. Turn off Auto Save
in this workspace. Keep the supplied imports, signatures, and decorators.
Save each completed function once. The dashboard shows the resource IDs as you finish steps 1 through 3.

| # | Function | API call | What to implement and check |
|---|---|---|---|
| 1 | `setup_agent()` | `client.beta.skills.create` + `client.beta.agents.create` | Upload the Incident Triage Runbook skill. Attach it to a Claude Opus 4.8 agent with the supplied prompt and tools. Check the agent and skill IDs. |
| 2 | `setup_environment()` | `client.beta.environments.create` | Create the cloud environment. Check the environment ID. |
| 3 | `upload_log()` | `client.beta.files.upload` | Upload `data/app.log`. Check the file ID. |
| 4 | `start_session()` | `client.beta.sessions.create` | Bind the agent ID, environment ID, and file ID. Mount the file as `app.log`. Return the session ID. Click **+** and check the ID. |
| 5 | `stream_reply()` | `client.beta.sessions.events.stream` + `.send` | Open the stream, send `user.message`, and yield events. For each `agent.custom_tool_use`, call the local handler and send `user.custom_tool_result` with `custom_tool_use_id` set to the request's `id`. |
| 6 | `handle_tool()` | Runs locally | Read the supplied fixtures. Return text for `get_metrics` with `service` and `metric`, `get_recent_deploys` with no arguments, and `get_diff` with `commit`. |
| 7 | `delete_session()` | `client.beta.sessions.delete` | After your demo turn finishes, verify the selected session is yours and delete it once. |

The system prompt, tool schemas, runbook skill, chat UI, and session picker are provided.
Stuck? `agent_complete.py` has the finished versions. Compare just the function
you're working on. [Starter](agent.py) · [Reference](agent_complete.py)

Session creation begins sandbox provisioning. The dashboard shows **Session created. Send a message to start a turn.** Finish and save `stream_reply()`, `handle_tool()`, and `delete_session()` before sending your first message. Send `hey` and wait for **Turn finished.** Then ask **“What caused the latency spike?”** and wait for **Turn finished.** again. Stay on **Investigation** and leave the code unchanged while a turn is running.

## The incident

`data/` ships a fictional outage. Checkout latency climbs, the DB connection
pool saturates, and checkouts start failing. The evidence is in four files.

- `app.log` contains about 70,000 lines of JSON logs. The agent can grep the mounted log at `/mnt/session/uploads/app.log` in its sandbox.
- `metrics.json`, `deploys.json`, and `diff.txt` provide the evidence returned by `get_metrics`, `get_recent_deploys`, and `get_diff`. These handlers run on **your** machine.

Compare checkout metrics and recent deploys, inspect the candidate diff, and
confirm a clue in the log. Write your suspect, one checked fixture fact, and
one uncertainty before sharing your answer.

Each tool card shows where the call ran (**Local** or **Sandbox**) and its full event ID. Expand **Input and result** to see the formatted payloads, the result's event ID, and its reference back to the call. Match `custom_tool_use_id` for a local result or `tool_use_id` for a sandbox result to the call's `id`. Use **Copy ID** for event IDs and **Copy Contents** for payloads. The same cards appear when you reopen a session from the picker.

The **Console** button next to the picker opens the selected session. The agent, environment, uploaded log, and Runbook Skill each have a **Console** button beside the ID for resource details. On a tool card, the buttons beside the call and result IDs open those events in **Inspector → Events**. Sign in with your own Console account and use a session workspace where you have Developer or Admin access. [Console Sessions](https://platform.claude.com/sessions) · [Inspect a session](https://platform.claude.com/docs/en/managed-agents/session-observability#inspect-a-session-in-the-console)

## What this teaches

- **Agent → Environment → Session → Events**. Configure the agent and its environment, bind them in a session, then send and receive events. [Managed Agents quickstart](https://platform.claude.com/docs/en/managed-agents/quickstart)
- **Skills**. `incident-triage-runbook/SKILL.md` packages the team's runbook. Upload and attach it inside `setup_agent()` so the agent has those triage instructions in each session.
- **Sandboxed code execution**. The agent runs file and shell tools in a managed container. It can use Python or shell commands to inspect the mounted log.
- **Custom tools**. The agent in the cloud calls functions on your machine over the event stream. Your local code looks up the evidence and sends the result back.
- **Stateful sessions**. The dropdown above the chat lists recent sessions through `sessions.list()`. Pick the same session and the app reloads its conversation from `events.list()`.

## Troubleshooting

Keep your own folder and Streamlit process. Tell your instructor the **last step that worked** and the **first relevant error line**. For an API error, include the operation, status and request ID if shown. Keep the key and `.env` out of chat. If you already have a session, note its full ID before retrying or restarting.

### Start with the local setup

With your workshop key set, run the checker with neither flag for local diagnostics. It reports issues without making an API request or showing the key or file contents. Follow its first fix or unfinished function cue, then verify the result in the dashboard.

**macOS or Linux**

```bash
.venv/bin/python check_setup.py
```

**Windows PowerShell**

```powershell
& .\.venv\Scripts\python.exe check_setup.py
```

Add `--check-access` to that command to test read access with your issued key without launching the dashboard. The checker sends a single list request to the first-party Claude API. This can catch a 401 or 403 before you create resources. A pass confirms read access, while model access and resource creation have their own checks. Use the dashboard or Console for live session state and tool results.

- **Missing files.** Open the workshop subfolder in a fresh clone. Keep your existing edits and run the checker from the folder containing `app.py`.
- **Missing venv, wrong Python, or import failure.** Return to [Create the virtual environment](#create-the-virtual-environment) and use Python 3.10.20. If your existing uv is missing or cannot obtain that Python version, follow the `.workshop-uv` fallback for your platform. If the fallback or pip fails, share the first error.
- **Missing or incomplete log.** The launch command generates a missing log. If the dashboard is already open or the checker reports an incomplete log, run `.venv/bin/python data/generate_log.py` or, in PowerShell, `& .\.venv\Scripts\python.exe data/generate_log.py` from the workshop folder. Wait for 69,740 lines, then look for the file ID after upload.
- **Dashboard fails to open.** Read the terminal error and use the local URL Streamlit prints. If a previous copy is still running, use its printed URL or close only your own idle process before restarting.
- **A save shows no progress.** Check the folder and interpreter in **Diagnostics**. Save one complete function, then use the next checkpoint in [What you build](#what-you-build). If the dashboard pauses because a function returned no resource ID, fix its return value and check for a resource from the first attempt before choosing **Retry after checking existing resources**. For syntax or indentation errors, run the checker again.

### Three traps

1. **`display_title` raises `TypeError`.** An incompatible SDK can reject this argument before HTTP. Check **Diagnostics** for the Python and SDK running Streamlit. The checker expects Anthropic SDK **1.0.0**. Reinstall the pinned requirements with the same venv interpreter, then run the version check again.

   macOS or Linux:

   ```bash
   .venv/bin/python -m pip install --require-hashes -r requirements.lock.txt
   .venv/bin/python -m pip show anthropic
   ```

   Windows PowerShell:

   ```powershell
   & .\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock.txt
   & .\.venv\Scripts\python.exe -m pip show anthropic
   ```

   If a dashboard is running, finish its active turn and record the resource IDs before restarting it with that interpreter. Keep the workshop's `display_title` argument.

2. **The dashboard shows a session ID and no answer.** Clicking **+** creates a session and begins sandbox provisioning. Finish and save the last three functions in [What you build](#what-you-build), then send your message once from **Investigation**. The `user.message` event starts a model turn. If you already sent it, inspect that same session's status and events before sending again. Keep Streamlit running on **Investigation** while its local handler is needed.
3. **A tool result is missing after reopening.** Record the full session ID and let the turn finish so the local worker can return pending results. Refresh the browser and reselect that exact session in the picker. **+** creates a new session. Match the card's call ID to the result reference. If the result is still missing, use **Console** beside the picker to inspect the same session. If the link does not open it, select the key's workspace in [Console Sessions](https://platform.claude.com/sessions) and find the full session ID shown below the dashboard picker. If access is blocked, [check a fixture or ask to see a saved instructor session](#check-a-fixture-while-access-is-blocked).

### API access, a quiet stream, or cleanup

- **Missing key or 401.** Set the intended key privately. An exported value can override `.env`, even if that value is blank. Clear a stale value with `unset ANTHROPIC_API_KEY` on macOS or Linux or `Remove-Item Env:ANTHROPIC_API_KEY` in PowerShell. Restart your Streamlit process after correcting it. If resource creation already started, record the IDs first.
- **Read access passes, but creating the agent reports insufficient credits.** Listing environments confirms Managed Agents read access. Creation and model use have separate billing checks. Record the request ID, time, and Runbook Skill ID if shown. Ask the instructor to reconcile the upload and confirm the workshop workspace has API credits before retrying. After correcting the key or workspace, restart Streamlit using the launch command above.
- **403 or 404.** A 403 means the request lacks permission for that resource. With a 404, check that the ID exists and is visible in the intended workspace. Ask the workspace owner to check access using the operation, status and request ID. [Check a fixture while access is blocked](#check-a-fixture-while-access-is-blocked). [Claude API errors](https://platform.claude.com/docs/en/api/errors)
- **Upload is slow, or API returns 429 or a server error.** Let a progressing upload finish. If the API reports an error, keep the resource IDs and request ID. Follow any retry instruction in the response. The SDK makes one attempt per request. After a failed or interrupted create, check whether the resource already exists. If the dashboard paused a setup step, use **Retry after checking existing resources** once you've reconciled the prior attempt.
- **A paused session, missing tool result, or disconnect.** Let an active turn finish before sending again or deleting the session. When the dashboard reports a pending turn or tool reply, it disables those controls. Open the same session and find the last event. Match `agent.custom_tool_use.id` to `user.custom_tool_result.custom_tool_use_id`. A match confirms the reply reached the service. The dashboard marks results missing from its stream and displays reported pause or stop reasons. Reopening history does not resume a pending handler. If the worker is gone, capture the ID and ask the instructor to help reconcile the session before starting a replacement. [Session events](https://platform.claude.com/docs/en/managed-agents/events-and-streaming)
- **Delete is blocked or the run is still active.** Save `delete_session()`, verify the full ID and finished state of your own session, and click delete once. Keep active or ambiguous sessions for follow-up with the instructor. Record the file, Skill, environment, and agent IDs for [optional workspace cleanup](#optional-workspace-cleanup). `e2e.py` creates another set of resources and is unsuitable as a recovery command. [Session deletion](https://platform.claude.com/docs/en/managed-agents/session-operations#deleting-a-session)

### Check a fixture while access is blocked

Open [`data/metrics.json`](data/metrics.json) in your browser or editor and find the largest `value` under `checkout.p99_latency_ms`. Note its UTC timestamp. If you already installed the workshop packages, you can open the standalone Metrics page from the workshop folder. It reads the fixture directly and needs no API key.

**macOS or Linux**

```bash
.venv/bin/python -m streamlit run pages/1_Metrics.py --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
```

**Windows PowerShell**

```powershell
& .\.venv\Scripts\python.exe -m streamlit run pages/1_Metrics.py --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
```

If you launched Metrics, open the URL Streamlit prints. The checkout p99 peak and its UTC time appear below the latency chart. Compare the checkout deploy time in [`data/deploys.json`](data/deploys.json) with when checkout latency starts to rise. If your instructor shows a saved session in Claude Console, match one tool call to its result in **Inspector → Events**. Report what you verified and which hosted step you still need to complete.

## Optional workspace cleanup

Record the full session, agent, environment, uploaded `app.log` file, and
custom Runbook Skill IDs in **Investigation** as you create them. When your
turns finish, use the same API key and workspace as setup. Check that you
created each resource and that nobody else is using it. If ownership or
turn state is unclear, keep the IDs and ask your instructor.

Delete each finished session you own with the dashboard's trash button. The
SDK call is `client.beta.sessions.delete(session_id)`. Then stop Streamlit
with **Ctrl+C**.

From the workshop folder, open Python with `.venv/bin/python` on macOS or
Linux, or `& .\.venv\Scripts\python.exe` in PowerShell. Use the key from your
workshop shell or `.env`.

```python
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(".env")
client = Anthropic(base_url="https://api.anthropic.com", max_retries=0)
```

Set `agent_id`, `environment_id`, `file_id`, and `skill_id` to the exact IDs
you recorded, as strings. Agent archiving is permanent. Run these calls in
order and check each response.

```python
client.beta.agents.archive(agent_id)
client.beta.environments.delete(environment_id)
client.beta.files.delete(file_id)
```

With the workshop's Anthropic SDK 1.0.0, list all versions of your custom
Skill first, delete each version including the last one, then delete the
Skill itself. Keep the Skill ID until the final call succeeds. If a call
fails, check the resource's state before retrying. [Skills API migration guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide#migrate-from-skills-2025-10-02)

```python
versions = list(client.beta.skills.versions.list(skill_id=skill_id))
for version in versions:
    client.beta.skills.versions.delete(version.version, skill_id=skill_id)

client.beta.skills.delete(skill_id)
```

## Maintaining the setup

When changing Python, update `.python-version` and the version in the setup commands. When Python or a direct dependency changes, regenerate `requirements.lock.txt` using the command in its header. On macOS, build a fresh `.venv` from the updated lock and run `check_setup.py`. After changes to the SDK or session flow, verify a hosted incident turn, replay, and cleanup.

## Repo layout

```
agent.py            ← the only file you edit
agent_complete.py   ← reference implementation
provided.py         ← system prompt, tool schemas, chat UI, session picker
check_setup.py      ← setup checks and dashboard launcher
e2e.py              ← headless test of the full path (creates cloud resources)

app.py              ← incident overview
pages/              ← Metrics, Logs, Deploys
incident-triage-runbook/  ← the team's runbook skill (SKILL.md)
data/               ← log + metrics + deploys + diff fixtures
ui.py, assets/      ← styling
```

## License

Apache License 2.0. See the repository [LICENSE](../LICENSE).
