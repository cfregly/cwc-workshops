<!-- Copyright 2026 Anthropic PBC -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Incident-2277

> **Workshop sample.** Adapted from Gagan Bhat's SRE workshop. [Original workshop](https://github.com/anthropics/cwc-workshops/tree/068b84bb03d2ae87c51edb2837dda25c84c1d686/ship-your-first-managed-agent)

> **It's 2am. PagerDuty fires: checkout p99 latency spikes.**
> You know the drill. Open the dashboard, grep logs, scroll deploys, guess,
> check, repeat. Which commit caused the spike?

A working incident dashboard for a fictional e-commerce stack. The Metrics,
Logs, and Deploys pages run out of the box from mock data. There's an
**SRE Agent** chat panel on the side of every page. It starts offline.
Bring it online with seven small functions in `agent.py` using
[Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview).

When you're done, ask it *"what caused the latency spike?"* and watch it grep
a 70k-line log inside its cloud sandbox, call your local tools to pull metrics
and deploys, correlate the timestamps, and inspect the candidate diff.

## Setup

You need Python **3.10+** and an Anthropic API key from Claude Console or your instructor. Clone from a fresh parent folder to avoid reusing an older checkout. If Git is unavailable, extract the source ZIP into a fresh folder and open `ship-your-first-managed-agent`. [API keys](https://platform.claude.com/settings/keys) · [Workshop source ZIP](https://github.com/cfregly/cwc-workshops/archive/refs/heads/gagan-sre-workshop.zip)

```bash
git clone --branch gagan-sre-workshop --single-branch https://github.com/cfregly/cwc-workshops.git cwc-workshops/
```

After the clone succeeds, open the workshop folder.

```bash
cd cwc-workshops/ship-your-first-managed-agent
git branch --show-current
git rev-parse HEAD
```

Expect the branch `gagan-sre-workshop`. Keep the full commit SHA printed by `git rev-parse HEAD` so you can identify your exact checkout. If your instructor gives you a commit SHA, check that it matches. The branch ZIP is a snapshot of the branch when you download it.

### Create the virtual environment

Use the Python **3.10 or newer** already installed on your laptop. Python **3.10.20** is the rehearsal baseline. If `.venv` already exists, check its version and path before reusing it. Use a fresh environment if it points to the wrong interpreter.

**macOS or Linux**

```bash
python3 --version
python3 -m venv .venv
```

If `python3` points to an older interpreter, use the full path to your installed Python 3.10 or newer in the `-m venv` command. Check the new environment and install the pinned packages.

```bash
.venv/bin/python -c "import sys; print(sys.version.split()[0], sys.executable)"
.venv/bin/python -m pip --version
.venv/bin/python -m pip install -r requirements.txt
```

**Windows PowerShell**

```powershell
py -3 --version
py -3 -m venv .venv
```

If the `py` launcher is unavailable, check `python --version` and run `python -m venv .venv` with Python 3.10 or newer. If `py -3` selects an older interpreter, run `py -0p` to see installed versions and choose the one you want. Check the new environment and install the pinned packages without activating it.

```powershell
& .\.venv\Scripts\python.exe -c "import sys; print(sys.version.split()[0], sys.executable)"
& .\.venv\Scripts\python.exe -m pip --version
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The executable and pip paths should both point into `.venv`. The requirements file pins `anthropic==1.0.0`, `streamlit==1.65.0`, `plotly==7.1.0`, and `python-dotenv==1.2.4`. Anthropic SDK 1.0.0 supports the workshop's `display_title` argument when uploading the skill. [Pinned requirements](requirements.txt) · [Skills API compatibility](https://platform.claude.com/docs/en/build-with-claude/skills-guide#migrate-from-skills-2025-10-02)

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

Run the included checker with the venv Python. It checks your current folder, interpreter, installed pins, key setup, files and starter syntax, checks dependency consistency and Managed Agents read access, then opens the dashboard if the checks pass. Keep the key off screen. The stock app generates the synthetic log on first launch if it is missing.

**macOS or Linux**

```bash
.venv/bin/python check_setup.py --check-access --launch
```

**Windows PowerShell**

```powershell
& .\.venv\Scripts\python.exe check_setup.py --check-access --launch
```

Open the **URL** Streamlit prints. The SRE Agent panel on the right says it is offline and asks you to implement `setup_agent()` in `agent.py`. If your key is still being issued, read the local fixtures while the access owner helps. For an error, open [Troubleshooting](#troubleshooting).

## What you build

Open **`agent.py`**. Seven functions, each starting with `raise NotImplementedError`.
Fill them in and the panel comes online one step at a time. Turn off Auto Save
in this workspace. Keep the supplied imports, signatures, and decorators.
Save each completed function once and wait for the next dashboard checkpoint.

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

Session creation begins sandbox provisioning. The first message starts model work. After adding the stream and local handler, send `hey`, then ask **“What caused the latency spike?”**

## The incident

`data/` ships a fictional outage. Checkout latency climbs, the DB connection
pool saturates, and checkouts start failing. The evidence is in four files.

- `app.log` contains about 70,000 lines of JSON logs. The agent can grep the mounted log at `/mnt/session/uploads/app.log` in its sandbox.
- `metrics.json`, `deploys.json`, and `diff.txt` provide the evidence returned by `get_metrics`, `get_recent_deploys`, and `get_diff`. These handlers run on **your** machine.

Compare checkout metrics and recent deploys, inspect the candidate diff, and
confirm a clue in the log. Write your suspect, one checked fixture fact, and
one uncertainty before sharing your answer.

While the turn runs, the dashboard shows tool inputs and result excerpts. Reopening the same session from the picker replays message text and tool names. The picker shows up to 15 sessions for the agent and replay loads one page of up to 500 events. For full inputs and results, find the exact session ID printed below the picker in the same workspace in Claude Console Sessions. Compare the local tool request's `id` with the result's `custom_tool_use_id`. The Console viewer requires Developer or Admin access. [Console Sessions](https://platform.claude.com/sessions) · [Inspect a session](https://platform.claude.com/docs/en/managed-agents/session-observability)

## What this teaches

- **Agent → Environment → Session → Events**. Configure the agent and its environment, bind them in a session, then send and receive events. [Managed Agents quickstart](https://platform.claude.com/docs/en/managed-agents/quickstart)
- **Skills**. `incident-triage-runbook/SKILL.md` packages the team's runbook. Upload and attach it inside `setup_agent()` so the agent has those triage instructions in each session.
- **Sandboxed code execution**. The agent runs file and shell tools in a managed container. It can use Python or shell commands to inspect the mounted log.
- **Custom tools**. The agent in the cloud calls functions on your machine over the event stream. Your local code looks up the evidence and sends the result back.
- **Stateful sessions**. The dropdown above the chat lists recent sessions through `sessions.list()`. Pick the same session and the app reloads its conversation from `events.list()`.

## Troubleshooting

Keep your own folder and Streamlit process. Tell your instructor the **last step that worked** and the **first relevant error line**. For an API error, include the operation, status and request ID if shown. Keep the key and `.env` out of chat. If you already have a session, note its full ID before retrying or restarting.

### Start with the local setup

Run the checker with neither flag for local diagnostics. It reports issues without showing the key or file contents. The checker names your first unfinished function and tells you what to look for after that step. A compiled function still needs a check in the dashboard.

**macOS or Linux**

```bash
.venv/bin/python check_setup.py
```

**Windows PowerShell**

```powershell
& .\.venv\Scripts\python.exe check_setup.py
```

Add `--check-access` to that command to test read access with your issued key without launching the dashboard. The checker sends a single list request to the first-party Claude API. This can catch a 401 or 403 before you create resources. A pass confirms read access, while model access and resource creation have their own checks. Use the dashboard or Console for live session state and tool results.

- **Missing files or no Git.** Open the workshop subfolder in a fresh clone or the [workshop ZIP](https://github.com/cfregly/cwc-workshops/archive/refs/heads/gagan-sre-workshop.zip). Keep your existing edits. `provided.py` reads the fixtures relative to the current directory.
- **Missing venv, wrong Python, or import failure.** Return to [Create the virtual environment](#create-the-virtual-environment). Use Python 3.10 or newer, then install and launch using that venv's executable. The tested presenter version is 3.10.20. If pip reports a wheel, index or network error, share that first error. Let an install continue while it is making progress.
- **Missing or incomplete log.** Run `.venv/bin/python data/generate_log.py` or, in PowerShell, `& .\.venv\Scripts\python.exe data/generate_log.py`. This regenerates the synthetic `data/app.log` and reports its line count. Wait for generation before upload.
- **Dashboard fails to open.** Read the terminal error and use the local URL Streamlit prints. If a previous copy is still running, use its printed URL or close only your own idle process before restarting.
- **A save shows no progress.** Check that you edited `agent.py` in the folder the dashboard runs from. Save one complete function, then use the next checkpoint in [What you build](#what-you-build). Follow the first relevant traceback line. Run the checker again to locate a syntax or indentation error. Compare just the current function with the reference if you need help.

### Three traps

1. **`display_title` raises `TypeError`.** The Skills call is using an incompatible SDK and fails before HTTP. Run the checker with the Python that launches Streamlit. It expects Anthropic SDK **1.0.0**. From this checkout, reinstall the pinned requirements using the same venv interpreter, then run the version check again.

   macOS or Linux:

   ```bash
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python -m pip show anthropic
   ```

   Windows PowerShell:

   ```powershell
   & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   & .\.venv\Scripts\python.exe -m pip show anthropic
   ```

   If a dashboard is running, finish its active turn and record the resource IDs before restarting it with that interpreter. Keep the workshop's `display_title` argument.

2. **The dashboard shows a session ID and no answer.** Clicking **+** creates a session and begins sandbox provisioning. Finish and save both `stream_reply()` and `handle_tool()`, then send your message once from the dashboard. The `user.message` event starts a model turn. If you already sent it, inspect that same session's status and events before sending again. Keep Streamlit running while its local handler is needed.
3. **Refreshing lost the tool inputs or results.** Record the full session ID shown under the picker and capture the tool boxes before you refresh. Let an active turn finish first so the local worker can return pending results. Reselect that same ID to replay messages and tool names. For the detailed trace, open [Console Sessions](https://platform.claude.com/sessions), select the key's workspace and find the ID you recorded. Developer or Admin access is needed. If that view is unavailable, use your retained tool evidence or ask the instructor for a labeled practice trace.

### API access, a quiet stream, or cleanup

- **Missing key or 401.** Set the intended key privately. An exported value can override `.env`, even if that value is blank. Clear a stale value with `unset ANTHROPIC_API_KEY` on macOS or Linux or `Remove-Item Env:ANTHROPIC_API_KEY` in PowerShell. Restart your Streamlit process after correcting it. If resource creation already started, record the IDs first.
- **Read access passes, but creating the agent reports insufficient credits.** Listing environments confirms Managed Agents read access. Creation and model use have separate billing checks. Record the request ID and time, and stop rerunning `setup_agent()`. Its skill upload can succeed before agent creation fails. Ask the instructor to reconcile that upload and confirm the workshop workspace has API credits. After correcting the key or workspace, restart Streamlit using the launch command above.
- **403 or 404.** A 403 means the request lacks permission for that resource. With a 404, check that the ID exists and is visible in the intended workspace. Ask the workspace owner to check access using the operation, status and request ID. Use the local fixtures while access is checked. [Claude API errors](https://platform.claude.com/docs/en/api/errors)
- **Upload is slow, or API returns 429 or a server error.** Let a progressing upload finish. If the API reports an error, keep the resource IDs and request ID. Follow any retry instruction in the response. The SDK makes one attempt per request. After a failed or interrupted create, check whether the resource already exists. If the dashboard paused a setup step, use **Retry after checking existing resources** once you've reconciled the prior attempt.
- **A paused session, missing tool result, or disconnect.** Open the same session and find the last event. Match `agent.custom_tool_use.id` to `user.custom_tool_result.custom_tool_use_id`. A match confirms the reply reached the service. The dashboard marks results missing from its stream and displays reported pause or stop reasons. Reopening history does not resume a pending handler. If the worker is gone, capture the ID and ask the instructor to help reconcile the session before starting a replacement. [Session events](https://platform.claude.com/docs/en/managed-agents/events-and-streaming)
- **Delete is blocked or the run is still active.** Save `delete_session()`, verify the full ID and finished state of your own session, and click delete once. Keep active or ambiguous sessions for follow-up with the instructor. Record file, skill, environment and agent IDs for separate workspace cleanup. `e2e.py` creates another set of resources and is unsuitable as a recovery command. [Session deletion](https://platform.claude.com/docs/en/managed-agents/session-operations#deleting-a-session)

If a hosted step is blocked, check one fixture fact locally and practice matching a request and result with the instructor's trace. Report what you verified and which hosted step you still need to complete.

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
