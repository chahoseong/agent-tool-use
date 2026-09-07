"""Run the official MinimalAgent on mock/create_task_1 exactly once."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import platform
import subprocess
from pathlib import Path
from types import ModuleType
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAU2_ROOT = PROJECT_ROOT.parent / "tau2-bench"
MINIMAL_AGENT_PATH = TAU2_ROOT / "examples" / "agents" / "minimal_text_agent.py"
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "mock" / "task_1"
GENERATED_ARTIFACTS = (
    "run-config.json",
    "simulation.json",
    "final-state.json",
)
TASK_ID = "create_task_1"
SEED = 42


def require_environment_variable(name: str) -> str:
    """Return a non-empty environment variable or fail before inference."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is empty: {name}")
    return value


def validate_base_url(value: str) -> str:
    """Validate and normalize the OpenAI-compatible llama.cpp base URL."""
    normalized = value.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("TAU2_LLM_BASE_URL must be an HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError(
            "TAU2_LLM_BASE_URL must not contain credentials, a query, or a fragment"
        )
    if not parsed.path.endswith("/v1"):
        raise RuntimeError("TAU2_LLM_BASE_URL must end with /v1")
    return normalized


def get_server_models(base_url: str, api_key: str) -> set[str]:
    """Read llama.cpp's model list without starting an inference request."""
    request = Request(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urlopen(request, timeout=10) as response:
        payload = json.load(response)
    return {
        model["id"]
        for model in payload.get("data", [])
        if isinstance(model, dict) and isinstance(model.get("id"), str)
    }


def run_git(*args: str) -> str:
    """Run a read-only Git command against the tau2-bench checkout."""
    result = subprocess.run(
        ["git", "-C", str(TAU2_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def load_minimal_agent_module() -> ModuleType:
    """Load the official example without copying or modifying its Agent code."""
    spec = importlib.util.spec_from_file_location(
        "tau2_official_minimal_text_agent",
        MINIMAL_AGENT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load official MinimalAgent: {MINIMAL_AGENT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    """Write a readable UTF-8 JSON artifact."""
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Validate inputs, run one simulation, and preserve its raw artifacts."""
    if not TAU2_ROOT.is_dir():
        raise RuntimeError(f"tau2-bench checkout not found: {TAU2_ROOT}")
    if not (TAU2_ROOT / "data").is_dir():
        raise RuntimeError(f"tau2-bench data directory not found: {TAU2_ROOT / 'data'}")
    if not MINIMAL_AGENT_PATH.is_file():
        raise RuntimeError(f"Official MinimalAgent not found: {MINIMAL_AGENT_PATH}")
    existing_artifacts = [
        OUTPUT_DIR / name
        for name in GENERATED_ARTIFACTS
        if (OUTPUT_DIR / name).exists()
    ]
    if existing_artifacts:
        raise RuntimeError(f"Refusing to overwrite existing artifacts: {OUTPUT_DIR}")

    base_url = validate_base_url(require_environment_variable("TAU2_LLM_BASE_URL"))
    configured_model = require_environment_variable("TAU2_LLM_MODEL")
    server_model = configured_model.removeprefix("openai/")
    configured_api_key = os.getenv("TAU2_LLM_API_KEY", "").strip()
    api_key = configured_api_key or "sk-no-key-required"

    available_models = get_server_models(base_url, api_key)
    if server_model not in available_models:
        raise RuntimeError(
            f"TAU2_LLM_MODEL {server_model!r} is not exposed by {base_url}/models; "
            f"available models: {sorted(available_models)}"
        )

    tau2_commit = run_git("rev-parse", "HEAD")
    tau2_status = run_git("status", "--porcelain")
    if tau2_status:
        raise RuntimeError(
            "The tau2-bench checkout has uncommitted changes; refusing to run "
            "against a modified reference checkout"
        )

    # The installed tau2 package does not bundle domain data. Point it at the
    # official checkout before importing tau2 or the official example module.
    os.environ["TAU2_DATA_DIR"] = str(TAU2_ROOT / "data")

    from tau2.data_model.simulation import TextRunConfig
    from tau2.evaluator.evaluator import EvaluationType
    from tau2.registry import registry
    from tau2.runner import build_orchestrator, get_tasks, run_simulation

    minimal_agent_module = load_minimal_agent_module()
    registry.register_agent_factory(
        minimal_agent_module.create_minimal_agent,
        "minimal_agent",
    )

    tasks = get_tasks("mock", task_ids=[TASK_ID])
    task = tasks[0]
    litellm_model = f"openai/{server_model}"
    llm_args = {
        "api_base": base_url,
        "api_key": api_key,
        "temperature": 0,
    }
    config = TextRunConfig(
        domain="mock",
        task_ids=[TASK_ID],
        num_tasks=1,
        agent="minimal_agent",
        llm_agent=litellm_model,
        llm_args_agent=llm_args,
        user="user_simulator",
        llm_user=litellm_model,
        llm_args_user=llm_args,
        num_trials=1,
        max_steps=20,
        max_errors=5,
        max_concurrency=1,
        seed=SEED,
        max_retries=0,
        hallucination_retries=0,
        auto_review=False,
    )

    run_config = {
        "domain": "mock",
        "task_id": TASK_ID,
        "agent": "minimal_agent",
        "user": "user_simulator",
        "llm_backend": "llama.cpp",
        "llm_model": server_model,
        "llm_base_url": base_url,
        "llm_api_key_configured": bool(configured_api_key),
        "temperature": 0,
        "seed": SEED,
        "num_trials": 1,
        "evaluation_type": EvaluationType.ALL.value,
        "tau2_bench": {
            "path": str(TAU2_ROOT),
            "commit": tau2_commit,
            "working_tree_clean": True,
        },
        "runtime": {
            "python": platform.python_version(),
            "tau2": importlib.metadata.version("tau2"),
            "litellm": importlib.metadata.version("litellm"),
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_DIR / "run-config.json", run_config)

    orchestrator = build_orchestrator(config, task, seed=SEED)
    simulation = run_simulation(
        orchestrator,
        evaluation_type=EvaluationType.ALL,
    )
    write_json(
        OUTPUT_DIR / "simulation.json",
        simulation.model_dump(mode="json"),
    )

    if orchestrator.environment.tools is None:
        raise RuntimeError("Mock environment did not expose an assistant toolkit")
    final_state = orchestrator.environment.tools.db.model_dump(mode="json")
    write_json(OUTPUT_DIR / "final-state.json", final_state)

    print(f"Saved observation artifacts to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
