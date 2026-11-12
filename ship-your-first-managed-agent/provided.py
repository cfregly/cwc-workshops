# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Everything pre-supplied for the workshop: the agent's system prompt, tool
schemas, the local data those tools read, and the side-chat UI. You don't
edit this file — agent.py imports from it.
"""
import json
from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from html import escape
from pathlib import Path
import re
from threading import Lock
from urllib.parse import quote

import anthropic
import streamlit as st
from anthropic.types.beta.sessions import (
    BetaManagedAgentsAgentCustomToolUseEvent,
    BetaManagedAgentsAgentToolResultEvent,
    BetaManagedAgentsAgentToolUseEvent,
    BetaManagedAgentsUserCustomToolResultEvent,
)
from streamlit.delta_generator import DeltaGenerator

DATA = Path("data")

SYSTEM = """\
You are the SRE Agent — an SRE/data-analyst agent embedded in an incident
dashboard. The application log is mounted at /mnt/session/uploads/app.log (large; use
grep/python to analyze it, don't read it whole). You have local tools that
query the same data the dashboard shows. Correlate evidence and state findings
plainly and concisely.
"""

TOOLS = [
    {"type": "agent_toolset_20260401", "default_config": {"enabled": True}},
    {"type": "custom", "name": "get_metrics",
     "description": "Timeseries for a service+metric over the incident window.",
     "input_schema": {"type": "object",
                      "properties": {"service": {"type": "string"}, "metric": {"type": "string"}},
                      "required": ["service", "metric"]}},
    {"type": "custom", "name": "get_recent_deploys", "description": "Deploys in the last 6h.",
     "input_schema": {"type": "object", "properties": {}}},
    {"type": "custom", "name": "get_diff", "description": "Unified diff for a commit SHA.",
     "input_schema": {"type": "object", "properties": {"commit": {"type": "string"}},
                      "required": ["commit"]}},
]

metrics = json.loads((DATA / "metrics.json").read_text())
deploys = (DATA / "deploys.json").read_text()
diff = (DATA / "diff.txt").read_text()


# ── Investigation UI ─────────────────────────────────────────────────────
_ToolRequest = BetaManagedAgentsAgentCustomToolUseEvent | BetaManagedAgentsAgentToolUseEvent
_ToolResult = BetaManagedAgentsAgentToolResultEvent | BetaManagedAgentsUserCustomToolResultEvent
_ToolKey = tuple[str, str]


@dataclass
class _ToolCall:
    request: _ToolRequest
    results: dict[str, _ToolResult]


_ChatPart = str | _ToolCall
_ChatHistory = list[tuple[str, list[_ChatPart]]]


def _tool_key(event: _ToolRequest | _ToolResult) -> _ToolKey:
    if event.type == "user.custom_tool_result":
        return "agent.custom_tool_use", event.custom_tool_use_id
    if event.type == "agent.tool_result":
        return "agent.tool_use", event.tool_use_id
    return event.type, event.id


def _console_url(collection: str, resource_id: str, workspace: str | None) -> str:
    workspace_path = quote(workspace or "default", safe="")
    resource_path = quote(resource_id, safe="")
    return f"https://platform.claude.com/workspaces/{workspace_path}/{collection}/{resource_path}"


def _console_button(url: str, resource: str):
    st.link_button(
        "Console", url, help=f"Open {resource} in Claude Console",
        icon=":material/open_in_new:", icon_position="right",
    )


# The picker changes in the browser before Streamlit finishes its rerun.
# Keep the picker and link together so a fast click cannot use the old URL.
@cache
def _session_console_component():
    return st.components.v2.component(
        "workshop_session_console",
        html="""
            <div class="session-controls">
                <select aria-label="session"></select>
                <a role="link" aria-disabled="true" tabindex="-1" target="_blank"
                   rel="noopener noreferrer" title="Open the selected session in Claude Console">
                    Console <span aria-hidden="true">↗</span>
                </a>
            </div>
        """,
        css="""
            .session-controls { display: flex; align-items: center; gap: 0.75rem; }
            select, a {
                border: 1px solid transparent; border-radius: 0.5rem;
                font: inherit; min-height: 2.5rem; padding: 0.4rem 0.65rem;
            }
            select {
                flex: 1; min-width: 0; color-scheme: dark;
                background: var(--st-secondary-background-color);
                color: var(--st-text-color);
            }
            a {
                display: inline-flex; align-items: center; gap: 0.35rem;
                background: var(--st-primary-color); color: #0b0e14;
                text-decoration: none; white-space: nowrap;
            }
            a[aria-disabled="true"] { opacity: 0.45; cursor: default; }
            select:focus-visible, a:focus-visible {
                outline: 2px solid var(--st-primary-color); outline-offset: 2px;
            }
        """,
        js="""
            export default function ({ parentElement, data, setTriggerValue }) {
                const picker = parentElement.querySelector("select");
                const link = parentElement.querySelector("a");
                const { options, confirmed, url } = data;

                function syncLink() {
                    const ready = Boolean(url && picker.value === confirmed);
                    if (ready) {
                        link.href = url;
                    } else {
                        link.removeAttribute("href");
                    }
                    link.setAttribute("aria-disabled", String(!ready));
                    link.tabIndex = ready ? 0 : -1;
                }

                const placeholder = new Option("Select a session", "");
                placeholder.disabled = true;
                picker.replaceChildren(placeholder, ...options.map(([id, label]) => new Option(label, id)));
                const pending = picker.dataset.pending;
                if (pending === confirmed || !options.some(([id]) => id === pending)) {
                    delete picker.dataset.pending;
                }
                picker.value = picker.dataset.pending || confirmed || "";
                picker.disabled = options.length === 0;
                syncLink();

                picker.onchange = () => {
                    picker.dataset.pending = picker.value;
                    syncLink();
                    setTriggerValue("selected", picker.value);
                };
            }
        """,
    )


def _resource_id(label: str, resource_id: str, resource: str, url: str):
    with st.container(horizontal=True, width="content", vertical_alignment="center", gap="xsmall"):
        st.caption(f"{label} · `{resource_id}`")
        _console_button(url, resource)


def _event_id(label: str, event_id: str, *, console_url: str | None = None):
    with st.container(key=f"tool-event-id-{event_id}", gap=None):
        st.caption(label)
        with st.container(horizontal=True, wrap=False, gap="xsmall"):
            st.code(event_id, language=None, wrap_lines=True)
            if console_url:
                _console_button(console_url, "this call")


def _payload(value: object, *, text: bool = False):
    language = "json"
    if text and isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            language = "text"
    body = json.dumps(value, indent=2, ensure_ascii=False) if language == "json" else str(value)
    st.code(body, language=language, wrap_lines=True)


def _render_tool_heading(heading: DeltaGenerator, call: _ToolCall, *, waiting: bool = False):
    request = call.request
    scope = "Local" if request.type == "agent.custom_tool_use" else "Sandbox"
    if any(result.is_error for result in call.results.values()):
        status, color = "Tool error", "red"
    elif call.results:
        status, color = "Result received", "green"
    elif waiting:
        status, color = "Waiting for result", "gray"
    else:
        status, color = "Result not observed", "orange"
    heading.html(
        '<div class="tool-call-heading">'
        f'<div class="tool-call-name"><strong><code>{escape(request.name)}</code></strong><span>{scope}</span></div>'
        f'<span class="tool-call-state {color}">{status}</span>'
        '</div>'
    )


def _render_tool_result(result: _ToolResult):
    st.markdown("**Result**")
    _event_id("Result event ID", result.id)
    if not result.content:
        st.caption("Empty result")
    for block in result.content or ():
        if block.type == "text":
            _payload(block.text, text=True)
        else:
            _payload(block.model_dump(mode="json", exclude_none=True))
    reference = "custom_tool_use_id" if result.type == "user.custom_tool_result" else "tool_use_id"
    st.caption(f"The result’s `{reference}` matches the call event ID.")


def _render_tool_call(
    call: _ToolCall, session_url: str, *, waiting: bool = False,
) -> tuple[DeltaGenerator, DeltaGenerator]:
    request = call.request
    with st.container(border=True, key=f"tool-card-{request.id}", gap="xsmall"):
        heading = st.empty()
        _render_tool_heading(heading, call, waiting=waiting)
        event_id = quote(request.id, safe="")
        _event_id("Call event ID", request.id, console_url=f"{session_url}?event={event_id}")
        with st.expander("Input and result", key=f"tool-details-{request.id}"):
            st.markdown("**Input**")
            _payload(request.input)
            result_area = st.container(gap="xsmall")
            with result_area:
                for result in call.results.values():
                    _render_tool_result(result)
    return heading, result_area


def _offline(fn: str):
    st.caption(f"agent offline — implement `{fn}()` in `agent.py`")
    st.chat_input("ask…", disabled=True, key=f"off_{fn}")


@st.cache_data
def _agent_details(agent_id: str) -> tuple[list[str], str | None]:
    import agent
    response = agent.client.beta.agents.with_raw_response.retrieve(agent_id)
    skills = [skill.skill_id for skill in (response.parse().skills or [])]
    return skills, response.headers.get("anthropic-workspace-id")


@st.cache_data(ttl=20)
def _list_sessions(agent_id: str):
    import agent
    page = agent.client.beta.sessions.list(agent_id=agent_id, limit=15, order="desc")
    items = sorted(page.data, key=lambda s: s.created_at, reverse=True)
    return [
        (s.id, f"{s.created_at:%H:%M:%S} · {s.status} · {s.id[-6:]}", s.created_at)
        for s in items
    ]


def _load_history(session_id: str) -> _ChatHistory:
    """Replay a session's conversation from the server-side event log."""
    import agent

    history: _ChatHistory = []
    results: dict[_ToolKey, dict[str, _ToolResult]] = defaultdict(dict)
    calls_seen: set[_ToolKey] = set()
    # Iterating the SDK cursor follows later pages, including results for earlier calls.
    for ev in agent.client.beta.sessions.events.list(session_id, order="asc", limit=500):
        if ev.type == "user.message":
            history.append(("user", [_text(ev.content)]))
            continue
        if ev.type in ("agent.tool_result", "user.custom_tool_result"):
            results[_tool_key(ev)][ev.id] = ev
            continue
        if ev.type not in ("agent.message", "agent.tool_use", "agent.custom_tool_use"):
            continue
        if not history or history[-1][0] != "assistant":
            history.append(("assistant", []))
        parts = history[-1][1]
        if ev.type == "agent.message":
            text = _text(ev.content)
            if parts and isinstance(parts[-1], str):
                parts[-1] += text
            else:
                parts.append(text)
        elif (key := _tool_key(ev)) not in calls_seen:
            calls_seen.add(key)
            parts.append(_ToolCall(ev, results[key]))
    return history


def _text(content) -> str:
    if not content:
        return ""
    return "".join(getattr(b, "text", "") for b in content if getattr(b, "type", None) == "text")


def _api_error(error):
    if isinstance(error, anthropic.APIConnectionError):
        return "Could not reach the Claude API. Check your connection and inspect any existing resources before retrying."
    message = f"Claude API returned HTTP {error.status_code}."
    if (request_id := error.request_id) and re.fullmatch(r"req_[A-Za-z0-9_-]+", request_id):
        message += f" Request ID: {request_id}."
    if error.status_code == 400 and "credit balance is too low" in str(error.body).lower():
        return message + " The workshop workspace needs API credits. Ask the instructor to check the workspace."
    return message + " See Troubleshooting in the README before retrying."


@st.cache_resource
def _setup_guard():
    return Lock(), {}


def _setup_resource(name, operation):
    lock, errors = _setup_guard()
    with lock:
        if message := errors.get(name):
            if not st.button("Retry after checking existing resources", key=f"retry-{name}"):
                st.error(message)
                return None
            del errors[name]
        try:
            resource_id = operation()
            if isinstance(resource_id, str) and resource_id:
                return resource_id
            st.error(f"{name}() must return the resource ID. Check the reference and any existing resource before retrying.")
        except NotImplementedError:
            _offline(name)
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as error:
            recovery = (" A Skill may already have uploaded." if name == "setup_agent" else "")
            message = f"{name}(): {_api_error(error)}{recovery} Check existing resources before retrying."
            errors[name] = message
            st.error(message)
            st.rerun()
    return None


def _pending_actions(client, sid, pending):
    if not pending:
        return pending
    results = client.beta.sessions.events.list(
        sid, types=["user.custom_tool_result", "user.tool_confirmation"], order="desc", limit=15,
    )
    for item in results:
        pending.discard(getattr(item, "custom_tool_use_id", None) or getattr(item, "tool_use_id", None))
        if not pending:
            break
    return pending


def _paused_reason(client, sid):
    page = client.beta.sessions.events.list(sid, types=["session.status_idle"], order="desc", limit=1)
    if not page.data:
        return None
    reason = page.data[0].stop_reason
    if reason.type == "requires_action" and _pending_actions(client, sid, set(reason.event_ids)):
        return "requires_action"
    if reason.type == "budget_reached":
        return "budget_reached"
    return None


def chat_panel():
    try:
        _chat_panel()
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as error:
        st.error(_api_error(error))


def _chat_panel():
    import agent  # lazy import to avoid circular dependency

    st.subheader("SRE Agent")

    agent_id = _setup_resource("setup_agent", agent.setup_agent)
    if agent_id is None:
        return
    skills, agent_workspace = _agent_details(agent_id)
    _resource_id("agent", agent_id, "this agent",
                 _console_url("agents", agent_id, agent_workspace))
    for sk in skills:
        st.caption(f"skill · `{sk}`")

    env_id = _setup_resource("setup_environment", agent.setup_environment)
    if env_id is None:
        return
    _resource_id("env", env_id, "this environment",
                 _console_url("environments", env_id, agent_workspace))

    log_id = _setup_resource("upload_log", agent.upload_log)
    if log_id is None:
        return
    st.caption(f"log file · `{log_id}`")

    # ── session picker: sessions are stateful + persisted server-side.
    # Never auto-create — resume the newest existing one, or show an empty state.
    if "sid" not in st.session_state:
        listed = _list_sessions(agent_id)
        if listed:
            st.session_state.sid = listed[0][0]
    sid = st.session_state.get("sid")
    status = None
    paused = None
    missing_sid = None
    workspace = agent_workspace
    if sid:
        try:
            response = agent.client.beta.sessions.with_raw_response.retrieve(sid)
            status = response.parse().status
            workspace = response.headers.get("anthropic-workspace-id") or agent_workspace
            if "chat_history" not in st.session_state:
                st.session_state.chat_history = _load_history(sid)
            if status == "idle":
                paused = _paused_reason(agent.client, sid)
        except anthropic.NotFoundError:
            missing_sid = sid
            _list_sessions.clear()
            st.session_state.sid = None
            st.session_state.chat_history = []
            st.warning(f"Session {sid} is no longer visible. Check the ID and workspace before starting over.")
            sid = None

    listed = _list_sessions(agent_id)
    labels = {session_id: label for session_id, label, _ in listed if session_id != missing_sid}
    if sid and sid not in labels:
        labels = {sid: "just now · current", **labels}

    def _on_pick():
        chosen = st.session_state.workshop_session_console.selected
        if chosen in labels and chosen != st.session_state.get("sid"):
            st.session_state.sid = chosen
            st.session_state.pop("chat_history", None)

    session_url = _console_url("sessions", sid, workspace) if sid else None
    with st.container(horizontal=True, vertical_alignment="center"):
        _session_console_component()(
            key="workshop_session_console", on_selected_change=_on_pick, width=410,
            data={"options": list(labels.items()), "confirmed": sid, "url": session_url},
        )
        new_session = st.button("", icon=":material/add:", help="new session")
        delete_session = st.button(
            "", icon=":material/delete:", help="delete session",
            disabled=paused is not None or status not in ("idle", "terminated"),
        )

    if new_session:
        try:
            st.session_state.sid = agent.start_session(agent_id, env_id, log_id)
        except NotImplementedError:
            st.toast("implement `start_session()` in `agent.py`")
        else:
            st.session_state.chat_history = []
            _list_sessions.clear()
            st.rerun()
    if delete_session:
        try:
            agent.delete_session(st.session_state.sid)
        except NotImplementedError:
            st.toast("implement `delete_session()` in `agent.py`")
        else:
            _list_sessions.clear()
            del st.session_state["sid"]
            st.session_state.pop("chat_history", None)
            st.rerun()

    if not session_url:
        st.caption("Select an existing session or click **+** to start one." if labels
                   else "no sessions — click **+** to start one")
        st.chat_input("ask…", disabled=True, key="off_nosession")
        return

    st.caption(f"Session ID · `{sid}`")

    chat = st.container()
    with chat:
        for role, parts in st.session_state.chat_history:
            with st.chat_message(role):
                for part in parts:
                    if isinstance(part, str):
                        st.markdown(part)
                    else:
                        _render_tool_call(part, session_url)

    if status in ("running", "rescheduling"):
        st.info(f"Session {sid} is {status}. Reopen it after the current work finishes.")
    if paused:
        st.warning(f"Session {sid} is paused ({paused}). Inspect it in Console before sending again.")
    if q := st.chat_input("ask the agent…", disabled=status != "idle" or paused is not None):
        st.session_state.chat_history.append(("user", [q]))
        with chat:
            with st.chat_message("user"):
                st.markdown(q)
            with st.chat_message("assistant"):
                text_ph = None
                buf = ""
                turn: list[_ChatPart] = []
                local_calls = set()
                answered = set()
                tool_cards: dict[_ToolKey, tuple[_ToolCall, DeltaGenerator, DeltaGenerator]] = {}
                results: dict[_ToolKey, dict[str, _ToolResult]] = defaultdict(dict)

                def flush_text():
                    nonlocal buf, text_ph
                    if buf:
                        turn.append(buf)
                    buf = ""
                    text_ph = None

                try:
                    for ev in agent.stream_reply(st.session_state.sid, q):
                        if ev.type == "agent.message":
                            buf += _text(ev.content)
                            if text_ph is None:
                                text_ph = st.empty()
                            text_ph.markdown(buf)
                        elif ev.type in ("agent.tool_use", "agent.custom_tool_use"):
                            key = _tool_key(ev)
                            if key not in tool_cards:
                                flush_text()
                                call = _ToolCall(ev, results[key])
                                turn.append(call)
                                heading, result_area = _render_tool_call(call, session_url, waiting=True)
                                tool_cards[key] = call, heading, result_area
                            if ev.type == "agent.custom_tool_use":
                                local_calls.add(ev.id)
                        elif ev.type in ("agent.tool_result", "user.custom_tool_result"):
                            if ev.type == "user.custom_tool_result":
                                answered.add(ev.custom_tool_use_id)
                            key = _tool_key(ev)
                            if ev.id in results[key]:
                                continue
                            results[key][ev.id] = ev
                            if key in tool_cards:
                                call, heading, result_area = tool_cards[key]
                                _render_tool_heading(heading, call)
                                with result_area:
                                    _render_tool_result(ev)
                        elif ev.type == "span.model_request_start":
                            flush_text()
                        elif ev.type == "session.status_idle":
                            reason = ev.stop_reason
                            reason_type = getattr(reason, "type", "unknown reason")
                            if reason_type == "end_turn":
                                break
                            if reason_type == "requires_action":
                                pending = set(reason.event_ids) - answered
                                if pending and pending <= local_calls:
                                    # The worker posts results before it yields the request. Confirm them
                                    # if the pause arrived ahead of their events on this stream.
                                    pending = _pending_actions(agent.client, sid, pending)
                                if reason.event_ids and not pending:
                                    continue
                            st.warning(f"Session {sid} paused ({reason_type}). Inspect this session before sending again.")
                            break
                        elif ev.type == "session.error":
                            retrying = getattr(getattr(ev.error, "retry_status", None), "type", None) == "retrying"
                            if retrying:
                                st.info("Claude is retrying this session. Keep the dashboard open.")
                                continue
                            st.error(f"Session {sid} reported an error. Inspect its event history before sending again.")
                            break
                        elif ev.type == "session.status_terminated":
                            st.error(f"Session {sid} terminated. Inspect its event history before starting over.")
                            break
                    else:
                        st.warning(f"The event stream closed before the turn ended. Check session {sid} before sending again.")
                except NotImplementedError:
                    st.warning("implement `stream_reply()` / `handle_tool()` in `agent.py`")
                except (KeyError, TypeError, ValueError):
                    st.error(f"The tool handler or event stream returned unexpected data. Check session {sid} and agent.py.")
                finally:
                    flush_text()
                    for call, heading, _ in tool_cards.values():
                        if not call.results:
                            _render_tool_heading(heading, call)
        if turn:
            st.session_state.chat_history.append(("assistant", turn))
