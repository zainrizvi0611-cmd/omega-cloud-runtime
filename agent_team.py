#!/usr/bin/env python3
"""
Unified Single-Team Multi-Agent AI Orchestration Engine (`agent_team.py`)
=========================================================================
Architecture:
- A single unified team led by **Head of the Team** (`head_of_team`), who acts as
  Supreme Orchestrator, Mission Planner, Task Router, Conflict Resolver, and Final Synthesizer.
- Multiple specialized Agentive AI workers operating concurrently in a shared team
  blackboard (`TeamBlackboard`) across distributed LLM providers (`~/.aria/api_config.json`
  and active Colab GPU tunnels).
- Supports dynamic addition/removal of custom specialist agents into the single team
  persisted at `~/.aria/team_roster.json`.
"""

import argparse
import concurrent.futures
import contextlib
import dataclasses
import fcntl
import json
import os
import re
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

TEAM_ROSTER_PATH = os.path.expanduser("~/.aria/team_roster.json")

BASE_DIRECTIVES = (
    "OPERATING DIRECTIVES (SINGLE UNIFIED AGENTIVE TEAM):\n"
    "1. You operate inside a single unified elite engineering team led by the Head of the Team.\n"
    "2. Deliver complete, working, production-grade code and technical analysis. Never use stubs, TODOs, or placeholders.\n"
    "3. Maintain full compatibility with Rooted Kali Linux ARM64 (aarch64) / Linux environments (/root workspace).\n"
    "4. Focus strictly on your specialized role while aligning with the Head of the Team's mission plan."
)


_CAPABILITY_STOPWORDS = {
    "a", "an", "the", "and", "or", "by", "of", "to", "in", "as", "is",
    "for", "with", "on", "at", "from", "into", "strictly", "assigned",
    "execute", "head", "team", "single", "unified", "agent", "worker",
    "specialist", "tasks",
}


def _normalize_capabilities(capabilities: Any, fallback_text: str = "") -> List[str]:
    """
    Normalize capabilities from a list, tuple, set, or comma/space-separated string into
    deduplicated lowercase keyword tokens, repairing character-split lists if encountered.
    """
    raw_items: List[str] = []
    if isinstance(capabilities, str):
        if "," in capabilities or ";" in capabilities:
            raw_items = [part.strip() for part in re.split(r"[,;]+", capabilities) if part.strip()]
        else:
            raw_items = re.findall(r"[a-zA-Z0-9_+-]+", capabilities)
    elif isinstance(capabilities, (list, tuple, set)):
        seq = [str(x) for x in capabilities if x is not None]
        if len(seq) >= 4 and all(len(x.strip()) <= 1 for x in seq):
            rejoined = "".join(seq)
            raw_items = re.findall(r"[a-zA-Z0-9_+-]+", f"{fallback_text} {rejoined}")
        else:
            for item in seq:
                if "," in item or ";" in item:
                    raw_items.extend(p.strip() for p in re.split(r"[,;]+", item) if p.strip())
                else:
                    raw_items.append(item.strip())

    cleaned: List[str] = []
    seen = set()
    for item in raw_items:
        tok = item.strip().lower()
        if not tok or tok in _CAPABILITY_STOPWORDS:
            continue
        if len(tok) == 1 and tok not in ("c", "r"):
            continue
        if tok not in seen:
            seen.add(tok)
            cleaned.append(tok)

    if not cleaned and fallback_text:
        for w in re.findall(r"[a-zA-Z0-9_+-]+", fallback_text.lower()):
            if len(w) > 2 and w not in _CAPABILITY_STOPWORDS and w not in seen:
                seen.add(w)
                cleaned.append(w)
                if len(cleaned) >= 8:
                    break
    return cleaned


@dataclass
class AgentSpec:
    """Specification for an Agentive AI member in the Single Team."""

    agent_id: str
    name: str
    role: str
    capabilities: List[str]
    system_prompt: str
    is_head: bool = False
    is_builtin: bool = True
    priority: int = 50
    provider_offset: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSpec":
        aid = str(data["agent_id"]).strip()
        role_str = str(data["role"]).strip()
        return cls(
            agent_id=aid,
            name=str(data["name"]).strip(),
            role=role_str,
            capabilities=_normalize_capabilities(data.get("capabilities", []), fallback_text=f"{aid} {role_str}"),
            system_prompt=str(data.get("system_prompt", BASE_DIRECTIVES)),
            is_head=bool(data.get("is_head", False)),
            is_builtin=bool(data.get("is_builtin", False)),
            priority=int(data.get("priority", 50)),
            provider_offset=int(data.get("provider_offset", 0)),
        )



DEFAULT_SINGLE_TEAM_ROSTER: List[AgentSpec] = [
    AgentSpec(
        agent_id="head_of_team",
        name="Head of the Team (Supreme Orchestrator)",
        role="Supreme Team Lead, Mission Decomposer, Multi-Agent Coordinator & Final Synthesizer",
        capabilities=[
            "orchestration",
            "leadership",
            "planning",
            "decomposition",
            "synthesis",
            "decision-making",
            "conflict-resolution",
        ],
        system_prompt=(
            "You are the HEAD OF THE TEAM (Supreme Multi-Agent Orchestrator) leading a single unified team "
            "of specialized agentive AI engineers.\n"
            f"{BASE_DIRECTIVES}\n"
            "As Head of the Team, you:\n"
            "- Decompose complex user requests into precise sub-missions for your specialist agents.\n"
            "- Audit, reconcile, and merge all specialist outputs into a single cohesive, verified deliverable.\n"
            "- Ensure every file, patch, command, and entrypoint is complete, runnable, and verified."
        ),
        is_head=True,
        is_builtin=True,
        priority=1,
        provider_offset=0,
    ),
    AgentSpec(
        agent_id="architect",
        name="Chief Systems Architect",
        role="System Architecture, Module Design, Data Flow & File Structure Specialist",
        capabilities=[
            "architecture",
            "design",
            "structure",
            "api",
            "schema",
            "modularity",
            "system",
            "project",
            "plan",
        ],
        system_prompt=(
            "You are the Chief Systems Architect in the single unified AI team reporting to the Head of the Team.\n"
            f"{BASE_DIRECTIVES}\n"
            "Design clean, modular architectures, exact file layouts, interfaces, and execution flows."
        ),
        is_head=False,
        is_builtin=True,
        priority=10,
        provider_offset=1,
    ),
    AgentSpec(
        agent_id="coder",
        name="Principal Polyglot Engineer",
        role="Full-Stack & Systems Code Implementation (Python, Rust, C/C++, Go, JS/TS, Bash)",
        capabilities=[
            "code",
            "implement",
            "build",
            "python",
            "rust",
            "cpp",
            "c",
            "golang",
            "javascript",
            "typescript",
            "bash",
            "script",
            "tool",
            "cli",
            "app",
        ],
        system_prompt=(
            "You are the Principal Polyglot Engineer in the single unified AI team reporting to the Head of the Team.\n"
            f"{BASE_DIRECTIVES}\n"
            "Write complete, self-contained, immediately runnable production code with proper error handling and clear CLI output."
        ),
        is_head=False,
        is_builtin=True,
        priority=20,
        provider_offset=2,
    ),
    AgentSpec(
        agent_id="security",
        name="Offensive & Defensive Security Specialist",
        role="Red/Blue Team Engineering, Network Protocols, Vulnerability Auditing & Hardening",
        capabilities=[
            "security",
            "pentest",
            "exploit",
            "audit",
            "scanner",
            "network",
            "socket",
            "payload",
            "shell",
            "recon",
            "cve",
            "hardening",
            "firewall",
            "auth",
        ],
        system_prompt=(
            "You are the Offensive & Defensive Security Specialist in the single unified AI team reporting to the Head of the Team.\n"
            f"{BASE_DIRECTIVES}\n"
            "Provide deep technical implementations of security mechanisms, protocol handlers, scanners, and vulnerability analyses."
        ),
        is_head=False,
        is_builtin=True,
        priority=30,
        provider_offset=3,
    ),
    AgentSpec(
        agent_id="crypto_math",
        name="Cryptographic & Web3 Specialist",
        role="Elliptic Curve Cryptography (secp256k1/ECDSA), Lattice/LLL, Kangaroo, Bitcoin & Solana",
        capabilities=[
            "crypto",
            "ecdsa",
            "secp256k1",
            "bitcoin",
            "btc",
            "solana",
            "eth",
            "ethereum",
            "wallet",
            "private",
            "key",
            "pubkey",
            "kangaroo",
            "lattice",
            "lll",
            "nonce",
            "hash",
            "cipher",
            "math",
        ],
        system_prompt=(
            "You are the Cryptographic & Web3 Specialist in the single unified AI team reporting to the Head of the Team.\n"
            f"{BASE_DIRECTIVES}\n"
            "Implement exact mathematical and cryptographic algorithms (secp256k1, ECDSA nonce recovery, Pollard's Kangaroo, baby-step giant-step, lattice reduction, Web3 RPC/transactions)."
        ),
        is_head=False,
        is_builtin=True,
        priority=35,
        provider_offset=4,
    ),
    AgentSpec(
        agent_id="reverse_eng",
        name="Reverse Engineering & Binary Specialist",
        role="Binary Analysis, ELF/PE/APK Internals, Disassembly, Smali & Memory Patching",
        capabilities=[
            "reverse",
            "binary",
            "elf",
            "pe",
            "apk",
            "smali",
            "dex",
            "decompile",
            "disassemble",
            "patch",
            "memory",
            "frida",
            "radare2",
            "ghidra",
            "capstone",
            "unicorn",
        ],
        system_prompt=(
            "You are the Reverse Engineering & Binary Specialist in the single unified AI team reporting to the Head of the Team.\n"
            f"{BASE_DIRECTIVES}\n"
            "Analyze binary formats, disassembly, instruction patching, APK/DEX/ELF structures, and low-level memory tooling."
        ),
        is_head=False,
        is_builtin=True,
        priority=40,
        provider_offset=5,
    ),
    AgentSpec(
        agent_id="devops_healer",
        name="Autonomous Runtime & Dependency Healer",
        role="Environment Provisioning, Package Resolution, Auto-Healing & Execution Stability",
        capabilities=[
            "devops",
            "install",
            "pip",
            "apt",
            "dependency",
            "fix",
            "heal",
            "error",
            "crash",
            "traceback",
            "runtime",
            "environment",
            "docker",
            "systemd",
        ],
        system_prompt=(
            "You are the Autonomous Runtime & Dependency Healer in the single unified AI team reporting to the Head of the Team.\n"
            f"{BASE_DIRECTIVES}\n"
            "Detect missing dependencies, platform incompatibilities, and runtime bugs, providing deterministic fixes and install commands."
        ),
        is_head=False,
        is_builtin=True,
        priority=45,
        provider_offset=6,
    ),
    AgentSpec(
        agent_id="qa_verifier",
        name="Red-Team Critic & QA Verification Agent",
        role="Edge-Case Stress Testing, Syntax/Logic Verification & Anti-Stub Quality Gate",
        capabilities=[
            "test",
            "verify",
            "qa",
            "validate",
            "check",
            "debug",
            "edge-case",
            "assert",
            "unittest",
            "pytest",
            "review",
        ],
        system_prompt=(
            "You are the Red-Team Critic & QA Verification Agent in the single unified AI team reporting to the Head of the Team.\n"
            f"{BASE_DIRECTIVES}\n"
            "Scrutinize code and plans for edge cases, boundary bugs, missing imports, or unimplemented logic, and provide concrete verification checks."
        ),
        is_head=False,
        is_builtin=True,
        priority=50,
        provider_offset=7,
    ),
    AgentSpec(
        agent_id="research_explainer",
        name="Deep Research & Bilingual Documentation Agent",
        role="Algorithmic Synthesis, Technical Documentation & Step-by-Step Run Guides (English + Tanglish)",
        capabilities=[
            "research",
            "explain",
            "guide",
            "docs",
            "tanglish",
            "tamil",
            "instructions",
            "tutorial",
            "summary",
        ],
        system_prompt=(
            "You are the Deep Research & Bilingual Documentation Agent in the single unified AI team reporting to the Head of the Team.\n"
            f"{BASE_DIRECTIVES}\n"
            "Provide crystal-clear technical explanations and step-by-step usage instructions (including Tanglish - Tamil + English in Latin script - when requested)."
        ),
        is_head=False,
        is_builtin=True,
        priority=60,
        provider_offset=8,
    ),
]

BUILTIN_AGENT_IDS = {a.agent_id for a in DEFAULT_SINGLE_TEAM_ROSTER}


@contextlib.contextmanager
def _roster_file_lock(roster_path: str, exclusive: bool = True) -> Iterator[None]:
    """Process-safe and thread-safe file lock around team_roster.json operations."""
    abs_roster = os.path.abspath(roster_path)
    os.makedirs(os.path.dirname(abs_roster), exist_ok=True)
    lock_path = f"{abs_roster}.lock"
    with open(lock_path, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def _load_custom_agents_unlocked(roster_path: str = TEAM_ROSTER_PATH) -> List[AgentSpec]:
    if not os.path.isfile(roster_path):
        return []
    try:
        with open(roster_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw_list = data.get("custom_agents", []) if isinstance(data, dict) else []
        agents = []
        for item in raw_list:
            if isinstance(item, dict) and item.get("agent_id"):
                spec = AgentSpec.from_dict(item)
                spec.is_head = False  # Only head_of_team is Head of the Team
                spec.is_builtin = False
                agents.append(spec)
        return agents
    except Exception:
        return []


def load_custom_agents(roster_path: str = TEAM_ROSTER_PATH) -> List[AgentSpec]:
    """Load user-added custom specialist agents from disk with shared file lock."""
    if not os.path.isfile(roster_path):
        return []
    try:
        with _roster_file_lock(roster_path, exclusive=False):
            return _load_custom_agents_unlocked(roster_path)
    except Exception:
        return _load_custom_agents_unlocked(roster_path)


def _save_custom_agents_unlocked(custom_agents: List[AgentSpec], roster_path: str = TEAM_ROSTER_PATH) -> None:
    abs_roster = os.path.abspath(roster_path)
    roster_dir = os.path.dirname(abs_roster)
    os.makedirs(roster_dir, exist_ok=True)
    payload = {
        "team_name": "OMEGA Unified Single Agentive AI Team",
        "head_of_team": "head_of_team",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "custom_agents": [a.to_dict() for a in custom_agents if not a.is_head],
    }
    fd, tmp_path = tempfile.mkstemp(prefix=".team_roster_", suffix=".tmp", dir=roster_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, abs_roster)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def save_custom_agents(custom_agents: List[AgentSpec], roster_path: str = TEAM_ROSTER_PATH) -> None:
    """Persist custom specialist agents to disk atomically with exclusive file lock."""
    with _roster_file_lock(roster_path, exclusive=True):
        _save_custom_agents_unlocked(custom_agents, roster_path)


def get_single_team_roster(roster_path: str = TEAM_ROSTER_PATH) -> List[AgentSpec]:
    """Return the unified single team roster with Head of the Team first, followed by all specialists."""
    roster_map: Dict[str, AgentSpec] = {}
    for builtin in DEFAULT_SINGLE_TEAM_ROSTER:
        roster_map[builtin.agent_id] = dataclasses.replace(builtin)

    for custom in load_custom_agents(roster_path):
        if custom.agent_id not in BUILTIN_AGENT_IDS:
            roster_map[custom.agent_id] = custom

    all_agents = list(roster_map.values())
    all_agents.sort(key=lambda a: (0 if a.is_head else 1, a.priority, a.agent_id))
    return all_agents


def add_agent_to_team(
    agent_id: str,
    name: str,
    role: str,
    capabilities: Optional[List[str]] = None,
    system_prompt: Optional[str] = None,
    priority: int = 55,
    roster_path: str = TEAM_ROSTER_PATH,
) -> AgentSpec:
    """Add a new specialized agentive AI worker into the single team under the Head of the Team."""
    clean_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", (agent_id or "").strip().lower()).strip("_")
    if not clean_id:
        raise ValueError("agent_id must be a non-empty alphanumeric identifier.")
    if clean_id == "head_of_team":
        raise ValueError("Cannot overwrite 'head_of_team'; Head of the Team is the supreme team lead.")
    if clean_id in BUILTIN_AGENT_IDS:
        raise ValueError(
            f"Cannot overwrite built-in specialist '{clean_id}'. Choose a unique agent_id to add more agents to the single team."
        )
    if not name or not name.strip():
        raise ValueError("Agent name must not be empty.")
    if not role or not role.strip():
        raise ValueError("Agent role must not be empty.")

    caps = _normalize_capabilities(capabilities, fallback_text=f"{clean_id} {role}")

    prompt = system_prompt or (
        f"You are {name.strip()} ({role.strip()}) in the single unified AI team reporting to the Head of the Team.\n"
        f"{BASE_DIRECTIVES}\n"
        f"Execute your specialized domain responsibilities ({', '.join(caps)}) with 100% precision."
    )

    with _roster_file_lock(roster_path, exclusive=True):
        existing_custom = _load_custom_agents_unlocked(roster_path)
        existing_match = next((a for a in existing_custom if a.agent_id == clean_id), None)
        used_offsets = {a.provider_offset for a in DEFAULT_SINGLE_TEAM_ROSTER} | {
            a.provider_offset for a in existing_custom if a.agent_id != clean_id
        }
        if existing_match is not None and existing_match.provider_offset not in used_offsets:
            offset = existing_match.provider_offset
        else:
            offset = max(used_offsets, default=0) + 1

        new_spec = AgentSpec(
            agent_id=clean_id,
            name=name.strip(),
            role=role.strip(),
            capabilities=caps,
            system_prompt=prompt,
            is_head=False,
            is_builtin=False,
            priority=priority,
            provider_offset=offset,
        )

        updated = [a for a in existing_custom if a.agent_id != clean_id]
        updated.append(new_spec)
        _save_custom_agents_unlocked(updated, roster_path)
    return new_spec


def remove_agent_from_team(agent_id: str, roster_path: str = TEAM_ROSTER_PATH) -> bool:
    """Remove a custom agent from the single team. Built-in core agents and head_of_team are protected."""
    clean_id = (agent_id or "").strip().lower()
    if clean_id == "head_of_team":
        raise ValueError("Cannot remove 'head_of_team' (Head of the Team).")
    with _roster_file_lock(roster_path, exclusive=True):
        existing_custom = _load_custom_agents_unlocked(roster_path)
        filtered = [a for a in existing_custom if a.agent_id != clean_id]
        if len(filtered) == len(existing_custom):
            return False
        _save_custom_agents_unlocked(filtered, roster_path)
        return True


@dataclass
class AgentContribution:
    """Output produced by a single specialist agent during a team mission."""

    agent_id: str
    agent_name: str
    role: str
    sub_mission: str
    output: str
    status: str = "ok"  # "ok", "fallback", "error"
    latency_ms: int = 0


@dataclass
class MissionPlan:
    """Decomposed mission plan created by the Head of the Team."""

    mission_goal: str
    head_agent_id: str
    head_strategy: str
    selected_agents: List[AgentSpec]
    sub_missions: Dict[str, str]  # agent_id -> specific sub-directive


@dataclass
class TeamMissionResult:
    """Complete result of a Single-Team multi-agent execution led by the Head of the Team."""

    mission_goal: str
    head_agent: AgentSpec
    plan: MissionPlan
    contributions: List[AgentContribution]
    final_output: str
    elapsed_sec: float
    boost_mode: bool

    def format_summary_report(self) -> str:
        lines = [
            "=" * 76,
            f" 👑 SINGLE TEAM EXECUTION REPORT — HEAD OF TEAM: {self.head_agent.name}",
            "=" * 76,
            f" 🎯 Mission       : {self.mission_goal[:120]}",
            f" ⚡ Mode          : {'BOOST (Full Parallel Squad)' if self.boost_mode else 'Standard Single-Team'}",
            f" 👥 Active Squad  : {len(self.plan.selected_agents)} specialists + 1 Head of Team",
            f" ⏱️  Total Elapsed : {self.elapsed_sec:.2f}s",
            "-" * 76,
            " 📋 SPECIALIST CONTRIBUTIONS:",
        ]
        for c in self.contributions:
            icon = "✅" if c.status == "ok" else ("⚠️" if c.status == "fallback" else "❌")
            snippet = (c.output or "").strip().splitlines()
            first_line = snippet[0][:75] if snippet else "(no output)"
            lines.append(
                f"   {icon} [{c.agent_id}] {c.agent_name} ({c.latency_ms}ms) -> {first_line}"
            )
        lines.append("=" * 76)
        return "\n".join(lines)


class TeamBlackboard:
    """Thread-safe shared memory blackboard for the single agentive AI team."""

    def __init__(self, mission_goal: str):
        self.mission_goal = mission_goal
        self._lock = threading.Lock()
        self._notes: List[Tuple[str, str]] = []
        self._contributions: Dict[str, AgentContribution] = {}

    def post_note(self, author_id: str, note: str) -> None:
        with self._lock:
            self._notes.append((author_id, note))

    def record_contribution(self, contrib: AgentContribution) -> None:
        with self._lock:
            self._contributions[contrib.agent_id] = contrib

    def get_contributions(self) -> List[AgentContribution]:
        with self._lock:
            return list(self._contributions.values())

    def dump_shared_context(self) -> str:
        with self._lock:
            if not self._contributions:
                return ""
            blocks = []
            for cid, c in self._contributions.items():
                if c.output:
                    blocks.append(
                        f"--- [SPECIALIST REPORT: {c.agent_name} ({cid})] ---\n"
                        f"Assigned Sub-Mission: {c.sub_mission}\n"
                        f"Findings / Output:\n{c.output}\n"
                    )
            return "\n".join(blocks)


class HeadOfTeamOrchestrator:
    """
    Supreme Coordinator for the Single Agentive AI Team.
    Decomposes tasks, selects and dispatches specialist agents in parallel,
    reviews their outputs on the TeamBlackboard, and synthesizes the final deliverable.
    """

    def __init__(
        self,
        roster_path: str = TEAM_ROSTER_PATH,
        call_fn: Optional[Callable[..., Optional[str]]] = None,
    ):
        self.roster_path = roster_path
        self.roster = get_single_team_roster(roster_path)
        self.head_agent = next((a for a in self.roster if a.is_head), DEFAULT_SINGLE_TEAM_ROSTER[0])
        self.specialists = [a for a in self.roster if not a.is_head]
        self._call_fn = call_fn

    def reload_roster(self) -> None:
        self.roster = get_single_team_roster(self.roster_path)
        self.head_agent = next((a for a in self.roster if a.is_head), DEFAULT_SINGLE_TEAM_ROSTER[0])
        self.specialists = [a for a in self.roster if not a.is_head]

    def _resolve_caller(self) -> Callable[..., Optional[str]]:
        if self._call_fn is not None:
            return self._call_fn
        # Dynamically load call_ai from /root/ai if available
        try:
            import importlib.machinery
            import importlib.util

            ai_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai")
            if os.path.isfile(ai_path):
                loader = importlib.machinery.SourceFileLoader("_omega_ai_mod", ai_path)
                spec = importlib.util.spec_from_loader("_omega_ai_mod", loader)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "call_ai"):
                        self._call_fn = mod.call_ai
                        return self._call_fn
        except Exception:
            pass

        def _noop_caller(prompt: str, **kwargs: Any) -> Optional[str]:
            return None

        return _noop_caller

    def select_squad(
        self,
        task_text: str,
        max_specialists: int = 4,
        boost_mode: bool = False,
        explicit_agent_ids: Optional[List[str]] = None,
    ) -> List[AgentSpec]:
        """
        Head of the Team selects the optimal squad of specialists from the single team.
        - Always includes core builders (`architect` and `coder`) unless explicit_agent_ids overrides.
        - Scores domain specialists (`crypto_math`, `security`, `reverse_eng`, `devops_healer`,
          `qa_verifier`, `research_explainer`, plus any custom agents) by keyword & capability match.
        - In `boost_mode`, expands the active squad up to 6 specialists for maximum parallel coverage.
        """
        self.reload_roster()
        if explicit_agent_ids:
            wanted = {aid.strip().lower() for aid in explicit_agent_ids if aid.strip()}
            selected = [a for a in self.specialists if a.agent_id in wanted]
            if selected:
                return selected

        text_lower = (task_text or "").lower()
        tokens = set(re.findall(r"[a-z0-9_+-]+", text_lower))

        target_count = max(max_specialists, 6) if boost_mode else max(2, max_specialists)
        scored: List[Tuple[int, int, AgentSpec]] = []

        for spec in self.specialists:
            score = 0
            # Core implementation roles get baseline priority
            if spec.agent_id == "coder":
                score += 50
            elif spec.agent_id == "architect":
                score += 40
            elif spec.agent_id == "qa_verifier":
                score += 25 if boost_mode else 15
            elif spec.agent_id == "research_explainer":
                score += 20 if ("tanglish" in text_lower or "explain" in text_lower or boost_mode) else 5

            # Capability keyword matching (avoid false-positive short substring collisions like 'pe' in 'open' or 'eth' in 'method')
            matched_caps = 0
            for cap in dict.fromkeys(spec.capabilities):
                cap_clean = cap.strip().lower()
                if not cap_clean:
                    continue
                if cap_clean in tokens:
                    score += 30
                    matched_caps += 1
                elif (" " in cap_clean or "-" in cap_clean) and cap_clean in text_lower:
                    score += 24
                    matched_caps += 1
                elif len(cap_clean) >= 4 and any(
                    tok.startswith(cap_clean) or (len(tok) >= 4 and cap_clean.startswith(tok))
                    for tok in tokens
                ):
                    score += 18
                    matched_caps += 1

            # Custom agents added by the user get a relevance boost when matching, or a smaller baseline boost
            if not spec.is_builtin:
                score += 22 if matched_caps > 0 else 8

            scored.append((-score, spec.priority, spec))

        scored.sort(key=lambda item: (item[0], item[1], item[2].agent_id))
        chosen = [item[2] for item in scored[:target_count]]
        # Sort chosen squad by priority so execution order is logical
        chosen.sort(key=lambda a: (a.priority, a.agent_id))
        return chosen

    def plan_mission(
        self,
        task_text: str,
        project_context: str = "",
        boost_mode: bool = False,
        max_specialists: int = 4,
        explicit_agent_ids: Optional[List[str]] = None,
    ) -> MissionPlan:
        """
        Head of the Team creates the MissionPlan and assigns tailored sub-missions
        to each selected specialist in the single team.
        """
        clean_task = (task_text or "").strip() or "Complete and verify the project in the working directory."
        squad = self.select_squad(
            clean_task,
            max_specialists=max_specialists,
            boost_mode=boost_mode,
            explicit_agent_ids=explicit_agent_ids,
        )

        sub_missions: Dict[str, str] = {}
        for agent in squad:
            if agent.agent_id == "architect":
                sub_missions[agent.agent_id] = (
                    f"Design the architecture, file layout, module interfaces, and execution entrypoint for: {clean_task}"
                )
            elif agent.agent_id == "coder":
                sub_missions[agent.agent_id] = (
                    f"Write complete, runnable, zero-stub production code (<FILE> / <PATCH> / <ENTRYPOINT>) to fulfill: {clean_task}"
                )
            elif agent.agent_id == "security":
                sub_missions[agent.agent_id] = (
                    f"Provide offensive/defensive security mechanisms, protocol handling, and vulnerability checks for: {clean_task}"
                )
            elif agent.agent_id == "crypto_math":
                sub_missions[agent.agent_id] = (
                    f"Verify and implement exact cryptographic/mathematical algorithms and optimizations for: {clean_task}"
                )
            elif agent.agent_id == "reverse_eng":
                sub_missions[agent.agent_id] = (
                    f"Analyze binary/low-level structures, memory handling, and reverse-engineering logic for: {clean_task}"
                )
            elif agent.agent_id == "devops_healer":
                sub_missions[agent.agent_id] = (
                    f"Identify required packages, environment setup, and self-healing runtime safeguards for: {clean_task}"
                )
            elif agent.agent_id == "qa_verifier":
                sub_missions[agent.agent_id] = (
                    f"Identify edge cases, failure modes, syntax/runtime pitfalls, and verification checks for: {clean_task}"
                )
            elif agent.agent_id == "research_explainer":
                sub_missions[agent.agent_id] = (
                    f"Prepare clear technical documentation and step-by-step Tanglish & English run instructions for: {clean_task}"
                )
            else:
                sub_missions[agent.agent_id] = (
                    f"Apply your specialized role ({agent.role}) to deliver concrete code and insights for: {clean_task}"
                )

        strategy = (
            f"Head of the Team ({self.head_agent.name}) is coordinating {len(squad)} specialists in a single unified team "
            f"({', '.join(a.agent_id for a in squad)}). Specialists execute in parallel across distributed LLM providers, "
            "post findings to the TeamBlackboard, and the Head of the Team synthesizes and verifies the final deliverable."
        )

        return MissionPlan(
            mission_goal=clean_task,
            head_agent_id=self.head_agent.agent_id,
            head_strategy=strategy,
            selected_agents=squad,
            sub_missions=sub_missions,
        )

    def _run_single_specialist(
        self,
        agent: AgentSpec,
        sub_mission: str,
        mission_goal: str,
        project_context: str,
        require_xml_actions: bool,
        blackboard: TeamBlackboard,
        caller: Callable[..., Optional[str]],
    ) -> AgentContribution:
        t0 = time.time()
        xml_hint = ""
        if require_xml_actions and agent.agent_id in ("coder", "architect", "crypto_math", "security", "reverse_eng"):
            xml_hint = (
                "\nIf proposing file creations, patches, or commands, format them with:\n"
                '<FILE path="relative/path.py">\n...complete runnable code...\n</FILE>\n'
                '<ENTRYPOINT>python3 main.py</ENTRYPOINT>\n'
            )

        ctx_block = f"\nPROJECT CONTEXT:\n{project_context[:6000]}\n" if project_context else ""
        prompt = (
            f"[SINGLE TEAM MISSION — DIRECTIVE FROM HEAD OF THE TEAM]\n"
            f"YOUR AGENT IDENTITY: {agent.name} (`{agent.agent_id}`)\n"
            f"YOUR SPECIALIZED ROLE: {agent.role}\n"
            f"OVERALL TEAM MISSION: {mission_goal}\n"
            f"YOUR ASSIGNED SUB-MISSION: {sub_mission}\n"
            f"{ctx_block}"
            f"{xml_hint}\n"
            "Provide a focused, high-density, complete technical response for the Head of the Team."
        )

        needed_tokens = 2500 if agent.agent_id in ("coder", "architect", "crypto_math", "security") else 1400
        try:
            out = caller(
                prompt,
                temp=0.15,
                offset=agent.provider_offset,
                needed_tokens=needed_tokens,
                sys_prompt=agent.system_prompt,
            )
            dt_ms = int((time.time() - t0) * 1000)
            if out and out.strip():
                contrib = AgentContribution(
                    agent_id=agent.agent_id,
                    agent_name=agent.name,
                    role=agent.role,
                    sub_mission=sub_mission,
                    output=out.strip(),
                    status="ok",
                    latency_ms=dt_ms,
                )
            else:
                contrib = AgentContribution(
                    agent_id=agent.agent_id,
                    agent_name=agent.name,
                    role=agent.role,
                    sub_mission=sub_mission,
                    output=f"[{agent.name}] Provider returned empty response; deferring synthesis to Head of Team.",
                    status="fallback",
                    latency_ms=dt_ms,
                )
        except Exception as e:
            dt_ms = int((time.time() - t0) * 1000)
            contrib = AgentContribution(
                agent_id=agent.agent_id,
                agent_name=agent.name,
                role=agent.role,
                sub_mission=sub_mission,
                output=f"[{agent.name}] Error during specialist execution: {e}",
                status="error",
                latency_ms=dt_ms,
            )

        blackboard.record_contribution(contrib)
        return contrib

    def execute_specialists_parallel(
        self,
        plan: MissionPlan,
        project_context: str = "",
        require_xml_actions: bool = False,
        blackboard: Optional[TeamBlackboard] = None,
    ) -> List[AgentContribution]:
        """Dispatch all selected specialist agents in the single team concurrently."""
        if blackboard is None:
            blackboard = TeamBlackboard(plan.mission_goal)
        caller = self._resolve_caller()

        if not plan.selected_agents:
            return []

        max_workers = max(1, min(len(plan.selected_agents), 8))
        results_by_id: Dict[str, AgentContribution] = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    self._run_single_specialist,
                    agent,
                    plan.sub_missions.get(agent.agent_id, plan.mission_goal),
                    plan.mission_goal,
                    project_context,
                    require_xml_actions,
                    blackboard,
                    caller,
                ): agent
                for agent in plan.selected_agents
            }
            for fut in concurrent.futures.as_completed(future_map):
                agent = future_map[fut]
                try:
                    results_by_id[agent.agent_id] = fut.result()
                except Exception as exc:
                    results_by_id[agent.agent_id] = AgentContribution(
                        agent_id=agent.agent_id,
                        agent_name=agent.name,
                        role=agent.role,
                        sub_mission=plan.sub_missions.get(agent.agent_id, ""),
                        output=f"Unhandled specialist exception: {exc}",
                        status="error",
                        latency_ms=0,
                    )

        # Return ordered according to squad priority
        return [results_by_id[a.agent_id] for a in plan.selected_agents if a.agent_id in results_by_id]

    @staticmethod
    def _reconcile_xml_actions(
        head_out: Optional[str],
        valid_contribs: List[AgentContribution],
    ) -> str:
        """
        Reconcile and deduplicate <FILE>, <PATCH>, <CMD>, and <ENTRYPOINT> blocks across
        Head of the Team output and specialist contributions.
        - Head of the Team's <FILE path="X"> takes precedence for path X.
        - If Head omitted path Y that one or more specialists produced, select the single best
          specialist implementation (preferring non-stub code and `coder`, then largest complete body)
          so conflicting specialist <FILE> blocks never overwrite each other in arbitrary order.
        """
        file_pattern = re.compile(r'<FILE\s+path=["\']([^"\']+)["\']\s*>([\s\S]*?)</FILE>')
        patch_pattern = re.compile(r'<PATCH\s+path=["\']([^"\']+)["\']\s*>([\s\S]*?)</PATCH>')
        cmd_pattern = re.compile(r"<CMD>([\s\S]*?)</CMD>")
        ep_pattern = re.compile(r"<ENTRYPOINT>([\s\S]*?)</ENTRYPOINT>")
        stub_pattern = re.compile(r"(\bTODO\b|\bFIXME\b|NotImplementedError|pass\s*#\s*(?:todo|stub))", re.IGNORECASE)

        def _norm_path(raw_p: str) -> str:
            return raw_p.strip().lstrip("./")

        head_text = (head_out or "").strip()
        head_files = {
            _norm_path(m.group(1))
            for m in file_pattern.finditer(head_text)
            if m.group(2).strip()
        }
        head_patches = {
            _norm_path(m.group(1))
            for m in patch_pattern.finditer(head_text)
            if m.group(2).strip()
        }
        head_cmds = {m.group(1).strip() for m in cmd_pattern.finditer(head_text) if m.group(1).strip()}
        head_has_ep = bool(ep_pattern.search(head_text))

        # Collect specialist <FILE> candidates grouped by normalized path
        file_candidates: Dict[str, List[Tuple[int, str, str]]] = {}
        path_order: List[str] = []
        for c in valid_contribs:
            for m in file_pattern.finditer(c.output):
                raw_p = m.group(1).strip()
                body = m.group(2).strip()
                if not raw_p or not body:
                    continue
                norm_p = _norm_path(raw_p)
                if norm_p in head_files:
                    continue
                if norm_p not in file_candidates:
                    file_candidates[norm_p] = []
                    path_order.append(norm_p)
                no_stub_bonus = 1000 if not stub_pattern.search(body) else 0
                coder_bonus = 500 if c.agent_id == "coder" else (200 if c.agent_id in ("crypto_math", "security", "reverse_eng") else 0)
                quality_score = no_stub_bonus + coder_bonus + len(body)
                file_candidates[norm_p].append((quality_score, raw_p, body))

        reconciled_blocks: List[str] = []
        chosen_specialist_files = set()
        for norm_p in path_order:
            candidates = file_candidates[norm_p]
            # Pick highest quality_score candidate for this file path
            best_score, best_raw_p, best_body = max(candidates, key=lambda item: item[0])
            reconciled_blocks.append(f'<FILE path="{best_raw_p}">\n{best_body}\n</FILE>')
            chosen_specialist_files.add(norm_p)

        # Collect specialist <PATCH> blocks for files not already replaced by <FILE> or patched by Head
        seen_patches = set(head_patches)
        for c in valid_contribs:
            for m in patch_pattern.finditer(c.output):
                raw_p = m.group(1).strip()
                body = m.group(2).strip()
                norm_p = _norm_path(raw_p)
                if not raw_p or not body or norm_p in head_files or norm_p in chosen_specialist_files:
                    continue
                patch_key = (norm_p, body)
                if patch_key not in seen_patches:
                    seen_patches.add(patch_key)
                    reconciled_blocks.append(f'<PATCH path="{raw_p}">\n{body}\n</PATCH>')

        # Collect deduplicated <CMD> blocks
        seen_cmds = set(head_cmds)
        for c in valid_contribs:
            for m in cmd_pattern.finditer(c.output):
                cmd_str = m.group(1).strip()
                if cmd_str and cmd_str not in seen_cmds:
                    seen_cmds.add(cmd_str)
                    reconciled_blocks.append(f"<CMD>{cmd_str}</CMD>")

        # Collect <ENTRYPOINT> if Head did not emit one (prefer `coder` first)
        if not head_has_ep:
            chosen_ep: Optional[str] = None
            for c in sorted(valid_contribs, key=lambda item: (0 if item.agent_id == "coder" else 1)):
                ep_m = ep_pattern.search(c.output)
                if ep_m and ep_m.group(1).strip():
                    chosen_ep = ep_m.group(1).strip()
                    break
            if chosen_ep:
                reconciled_blocks.append(f"<ENTRYPOINT>{chosen_ep}</ENTRYPOINT>")

        if reconciled_blocks and head_text:
            return "\n\n".join(reconciled_blocks) + "\n\n" + head_text
        if reconciled_blocks:
            return "\n\n".join(reconciled_blocks)
        return head_text

    def synthesize_team_output(
        self,
        plan: MissionPlan,
        contributions: List[AgentContribution],
        project_context: str = "",
        require_xml_actions: bool = False,
    ) -> str:
        """
        Head of the Team reviews all specialist contributions and synthesizes the final authoritative output.
        If `require_xml_actions` is True and the Head synthesis call fails or omits XML tags that a specialist
        already produced, the Head of the Team automatically reconciles, deduplicates, and preserves the XML blocks.
        """
        caller = self._resolve_caller()
        valid_contribs = [c for c in contributions if c.status == "ok" and c.output.strip()]

        specialist_reports = []
        for c in contributions:
            specialist_reports.append(
                f"=== SPECIALIST AGENT: {c.agent_name} (`{c.agent_id}`) | STATUS: {c.status} ===\n"
                f"Sub-Mission: {c.sub_mission}\n"
                f"{c.output[:5000]}\n"
            )
        reports_text = "\n".join(specialist_reports)

        xml_instructions = ""
        if require_xml_actions:
            xml_instructions = (
                "\nCRITICAL OUTPUT FORMAT REQUIREMENTS (FOR AUTOMATED PROJECT EXECUTION):\n"
                "1. Output complete runnable files using:\n"
                '<FILE path="main.py">\ncomplete runnable code\n</FILE>\n'
                "2. Or surgical patches to existing files using:\n"
                '<PATCH path="relative/path.ext">\n<<<<<<< SEARCH\nexact existing lines\n=======\nreplacement lines\n>>>>>>> REPLACE\n</PATCH>\n'
                "3. Optional shell commands:\n"
                "<CMD>command here</CMD>\n"
                "4. Final command to run the project:\n"
                "<ENTRYPOINT>python3 main.py</ENTRYPOINT>\n"
                "5. Also include clear TANGLISH (Tamil + English in Latin script) instructions explaining how to run the tool.\n"
            )

        ctx_section = f"\nPROJECT CONTEXT:\n{project_context[:6000]}\n" if project_context else ""

        synthesis_prompt = (
            f"You are {self.head_agent.name}, the SUPREME HEAD OF THE TEAM leading a single unified multi-agent AI team.\n"
            f"USER MISSION / GOAL:\n{plan.mission_goal}\n"
            f"{ctx_section}\n"
            f"REPORTS FROM YOUR SPECIALIST TEAM MEMBERS:\n{reports_text}\n"
            f"{xml_instructions}\n"
            "SYNTHESIS DIRECTIVE:\n"
            "As Head of the Team, combine the best architecture, complete implementation code, security/crypto optimizations, "
            "and QA verification fixes from your team into ONE authoritative, complete, runnable response. "
            "Never leave placeholders or stubs."
        )

        try:
            head_out = caller(
                synthesis_prompt,
                temp=0.15,
                offset=self.head_agent.provider_offset,
                needed_tokens=3000,
                sys_prompt=self.head_agent.system_prompt,
            )
        except Exception:
            head_out = None

        if require_xml_actions:
            reconciled = self._reconcile_xml_actions(head_out, valid_contribs)
            if reconciled:
                return reconciled

        if head_out and head_out.strip():
            return head_out.strip()

        # If head synthesis call failed completely, synthesize deterministically from valid specialist outputs
        if valid_contribs:
            sections = [
                f"# 👑 Head of the Team Synthesis ({self.head_agent.name})",
                f"**Mission:** {plan.mission_goal}\n",
            ]
            for c in valid_contribs:
                sections.append(f"## [{c.agent_id}] {c.agent_name}\n{c.output}")
            return "\n\n".join(sections)

        return ""

    def run_mission(
        self,
        task_text: str,
        project_context: str = "",
        boost_mode: bool = True,
        require_xml_actions: bool = False,
        max_specialists: int = 4,
        explicit_agent_ids: Optional[List[str]] = None,
        verbose: bool = True,
    ) -> TeamMissionResult:
        """
        Execute a full Single-Team mission led by the Head of the Team:
        1. Head of the Team plans the mission and selects the specialist squad.
        2. Specialist agents execute in parallel across distributed providers.
        3. Head of the Team synthesizes all specialist outputs into the final deliverable.
        """
        t0 = time.time()
        plan = self.plan_mission(
            task_text=task_text,
            project_context=project_context,
            boost_mode=boost_mode,
            max_specialists=max_specialists,
            explicit_agent_ids=explicit_agent_ids,
        )

        if verbose:
            print("=" * 76)
            print(f" 👑 HEAD OF THE TEAM: {self.head_agent.name}")
            print(f" 🤝 SINGLE TEAM SQUAD ({len(plan.selected_agents)} Specialists): "
                  + ", ".join(f"{a.name} [{a.agent_id}]" for a in plan.selected_agents))
            print(f" 🎯 MISSION: {plan.mission_goal[:120]}")
            print("=" * 76)

        blackboard = TeamBlackboard(plan.mission_goal)
        blackboard.post_note(self.head_agent.agent_id, plan.head_strategy)
        contributions = self.execute_specialists_parallel(
            plan=plan,
            project_context=project_context,
            require_xml_actions=require_xml_actions,
            blackboard=blackboard,
        )

        if verbose:
            print(f" 🧠 [Head of Team] Synthesizing {len(contributions)} specialist reports into final deliverable...")

        final_output = self.synthesize_team_output(
            plan=plan,
            contributions=contributions,
            project_context=project_context,
            require_xml_actions=require_xml_actions,
        )

        elapsed = time.time() - t0
        result = TeamMissionResult(
            mission_goal=plan.mission_goal,
            head_agent=self.head_agent,
            plan=plan,
            contributions=contributions,
            final_output=final_output,
            elapsed_sec=elapsed,
            boost_mode=boost_mode,
        )

        if verbose:
            print(result.format_summary_report())

        return result


def format_team_roster_table(roster_path: str = TEAM_ROSTER_PATH) -> str:
    """Format a human-readable hierarchy table of the Single Team led by the Head of the Team."""
    roster = get_single_team_roster(roster_path)
    head = next((a for a in roster if a.is_head), roster[0])
    specialists = [a for a in roster if not a.is_head]

    lines = [
        "=" * 84,
        " 👑 OMEGA UNIFIED SINGLE-TEAM AGENTIVE AI ROSTER",
        "=" * 84,
        f" [HEAD OF THE TEAM] ★ {head.agent_id:<18} | {head.name}",
        f"                      Role: {head.role}",
        "-" * 84,
        f" [SPECIALIST AGENTS IN SINGLE TEAM] ({len(specialists)} Active Agentive AI Workers):",
    ]
    for idx, agent in enumerate(specialists, start=1):
        origin = "Built-in" if agent.is_builtin else "Custom  "
        caps_str = ", ".join(agent.capabilities[:6])
        lines.append(
            f"  {idx:2d}. [{origin}] {agent.agent_id:<18} | {agent.name}"
        )
        lines.append(f"      Role        : {agent.role}")
        lines.append(f"      Capabilities: {caps_str} (Provider Offset: +{agent.provider_offset})")
    lines.append("=" * 84)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    slash_boost_tokens = {"/boost", "/team"}
    has_slash_boost = any(tok.lower() in slash_boost_tokens for tok in raw_argv)
    cleaned_argv = [tok for tok in raw_argv if tok.lower() not in slash_boost_tokens]

    parser = argparse.ArgumentParser(
        description="Unified Single-Team Multi-Agent AI Orchestrator led by the Head of the Team."
    )
    parser.add_argument(
        "task",
        nargs="*",
        help="Task or mission for the Head of the Team and specialist squad to execute.",
    )
    parser.add_argument(
        "--roster",
        "--list",
        "--list-agents",
        "--status",
        dest="show_roster",
        action="store_true",
        help="Display the Single Team hierarchy with Head of the Team and all specialist agents.",
    )
    parser.add_argument(
        "--boost",
        "--team",
        dest="boost_mode",
        action="store_true",
        default=True,
        help="Run in full multi-agent parallel Boost mode (default: True).",
    )
    parser.add_argument(
        "--standard",
        dest="standard_mode",
        action="store_true",
        help="Run with standard squad size instead of full Boost squad.",
    )
    parser.add_argument(
        "--max-specialists",
        type=int,
        default=4,
        help="Base number of specialist agents to dispatch in parallel (default: 4, boost: 6).",
    )
    parser.add_argument(
        "--agents",
        type=str,
        default="",
        help="Comma-separated list of specific specialist agent IDs to dispatch.",
    )
    parser.add_argument(
        "--add-agent",
        type=str,
        default="",
        metavar="AGENT_ID",
        help="Add a new specialist agentive AI into the single team under the Head of the Team.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="",
        help="Display name when adding a new agent with --add-agent.",
    )
    parser.add_argument(
        "--role",
        type=str,
        default="",
        help="Specialized role description when adding a new agent with --add-agent.",
    )
    parser.add_argument(
        "--capabilities",
        type=str,
        default="",
        help="Comma-separated capabilities when adding a new agent with --add-agent.",
    )
    parser.add_argument(
        "--remove-agent",
        type=str,
        default="",
        metavar="AGENT_ID",
        help="Remove a custom specialist agent from the single team.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the mission and select the single-team squad without making network LLM calls.",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output mission plan or roster in JSON format.",
    )

    args = parser.parse_args(cleaned_argv)

    if args.add_agent:
        name = args.name or f"{args.add_agent.replace('_', ' ').title()} Specialist"
        role = args.role or f"Specialized Agentive AI for {name}"
        caps = [c.strip() for c in args.capabilities.split(",") if c.strip()] if args.capabilities else None
        try:
            added = add_agent_to_team(
                agent_id=args.add_agent,
                name=name,
                role=role,
                capabilities=caps,
            )
            if args.json_output:
                print(json.dumps(added.to_dict(), indent=2))
            else:
                print(f"✅ Added Agentive AI `{added.agent_id}` ({added.name}) to the Single Team under Head of the Team!")
                print(format_team_roster_table())
            return 0
        except ValueError as e:
            print(f"❌ Error adding agent: {e}", file=sys.stderr)
            return 1

    if args.remove_agent:
        try:
            removed = remove_agent_from_team(args.remove_agent)
            if removed:
                print(f"✅ Removed custom agent `{args.remove_agent}` from the Single Team.")
                return 0
            else:
                print(f"⚠️ Custom agent `{args.remove_agent}` not found (or is a protected built-in agent).", file=sys.stderr)
                return 1
        except ValueError as e:
            print(f"❌ Error removing agent: {e}", file=sys.stderr)
            return 1

    task_tokens = list(args.task)
    if task_tokens and task_tokens[0].lower() in ("boost", "team"):
        has_slash_boost = True
        task_tokens = task_tokens[1:]

    if args.show_roster and not task_tokens:
        if args.json_output:
            roster = get_single_team_roster()
            print(
                json.dumps(
                    {
                        "head_of_team": next(a.to_dict() for a in roster if a.is_head),
                        "specialists": [a.to_dict() for a in roster if not a.is_head],
                        "total_agents": len(roster),
                    },
                    indent=2,
                )
            )
        else:
            print(format_team_roster_table())
        return 0

    task_text = " ".join(task_tokens).strip()
    if not task_text:
        print(format_team_roster_table())
        print("\nUsage Examples:")
        print('  agent_team.py --roster                                         # View Single Team & Head of Team')
        print('  agent_team.py --boost "Build a multi-threaded port scanner"    # Execute task with Full Squad')
        print('  agent_team.py --add-agent web3_auditor --name "Web3 Auditor" --role "Smart Contract Security"')
        return 0

    boost = False if args.standard_mode else bool(args.boost_mode or has_slash_boost)
    explicit_ids = [x.strip() for x in args.agents.split(",") if x.strip()] if args.agents else None

    orchestrator = HeadOfTeamOrchestrator()

    if args.dry_run:
        plan = orchestrator.plan_mission(
            task_text=task_text,
            boost_mode=boost,
            max_specialists=args.max_specialists,
            explicit_agent_ids=explicit_ids,
        )
        if args.json_output:
            print(
                json.dumps(
                    {
                        "mission_goal": plan.mission_goal,
                        "head_of_team": orchestrator.head_agent.to_dict(),
                        "head_strategy": plan.head_strategy,
                        "selected_squad": [a.to_dict() for a in plan.selected_agents],
                        "sub_missions": plan.sub_missions,
                    },
                    indent=2,
                )
            )
        else:
            print("=" * 76)
            print(f" 👑 [DRY-RUN MISSION PLAN] HEAD OF THE TEAM: {orchestrator.head_agent.name}")
            print("=" * 76)
            print(f" 🎯 Goal    : {plan.mission_goal}")
            print(f" 🧠 Strategy: {plan.head_strategy}")
            print("-" * 76)
            for idx, ag in enumerate(plan.selected_agents, 1):
                print(f"  {idx}. [{ag.agent_id}] {ag.name}")
                print(f"     Directive: {plan.sub_missions[ag.agent_id]}")
            print("=" * 76)
        return 0

    result = orchestrator.run_mission(
        task_text=task_text,
        boost_mode=boost,
        max_specialists=args.max_specialists,
        explicit_agent_ids=explicit_ids,
        verbose=not args.json_output,
    )
    if args.json_output:
        print(
            json.dumps(
                {
                    "mission_goal": result.mission_goal,
                    "head_of_team": result.head_agent.agent_id,
                    "selected_squad": [a.agent_id for a in result.plan.selected_agents],
                    "elapsed_sec": round(result.elapsed_sec, 3),
                    "final_output": result.final_output,
                },
                indent=2,
            )
        )
    else:
        if result.final_output:
            print("\n" + result.final_output)
        else:
            print("❌ [Head of Team] No output returned from providers.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
