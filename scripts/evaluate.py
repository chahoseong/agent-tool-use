"""Command-line entry point for official tau2-bench evaluations."""

import argparse
import os
import sys
from pathlib import Path

EVALUATION_TEMPLATE = """# 공식 tau2-bench 평가 설정 (llama.cpp 서버 전용)
[evaluation]
# 평가할 domain을 지정하세요.
domain = "mock"
# 평가할 task ID를 하나 이상 직접 지정하세요. 기본 task는 없습니다.
task_ids = []
seed = 42
num_trials = 1
max_concurrency = 1
# 생략하면 tau2-bench의 기본 실행 제한을 사용합니다.
# max_steps = 200
# max_errors = 10

[agent]
# 서버가 제공하는 모델 ID로 수정하세요. openai/ 접두사는 붙이지 않습니다.
model = "your-agent-model"
base_url = "http://localhost:8080/v1"
# 인증이 필요한 경우 키 값 대신 환경변수 이름을 지정하세요.
# api_key_env = "EVAL_AGENT_API_KEY"

# 필요한 생성 옵션만 주석을 해제하세요.
# [agent.generation]
# temperature = 0.0
# top_p = 1.0
# max_tokens = 1024

[user]
# 공식 사용자 시뮬레이터에 사용할 모델과 서버 주소입니다.
model = "your-user-model"
base_url = "http://localhost:8081/v1"
# api_key_env = "EVAL_USER_API_KEY"

# [user.generation]
# temperature = 0.0
# top_p = 1.0
# max_tokens = 1024

# 출력 상위 디렉토리입니다. 상대 경로는 프로젝트 루트 기준입니다.
# 실행마다 별도 하위 디렉토리를 생성합니다.
# [output]
# directory = "artifacts/evaluations"
"""


def _create_template() -> None:
    """Create a template in the working directory without replacing an existing file."""
    path = Path("evaluation.toml")
    template_file = path.open("x", encoding="utf-8")
    try:
        with template_file:
            template_file.write(EVALUATION_TEMPLATE)
    except BaseException:
        path.unlink()
        raise


def _validate_data_directory() -> None:
    """Require an explicit data directory before tau2 chooses its import-time path."""
    from evals.errors import EvaluationPreparationError

    value = os.environ.get("TAU2_DATA_DIR")
    if value is None or not value.strip():
        raise EvaluationPreparationError(
            "Set TAU2_DATA_DIR to the tau2-bench data directory."
        )
    try:
        is_directory = Path(value).is_dir()
    except (OSError, ValueError):
        is_directory = False
    if not is_directory:
        raise EvaluationPreparationError(
            "TAU2_DATA_DIR must point to an existing directory."
        )


def _build_parser() -> argparse.ArgumentParser:
    """Define commands without loading evaluation dependencies."""
    parser = argparse.ArgumentParser(
        description="Evaluate TaskAgent on official tau2-bench tasks."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create an evaluation.toml template.")
    tasks = commands.add_parser("tasks", help="List domains or tasks in a domain.")
    tasks.add_argument("domain", nargs="?", help="Domain whose tasks to list.")
    show = commands.add_parser("show", help="Show the details of a task.")
    show.add_argument("domain", help="Domain containing the task.")
    show.add_argument("task_id", help="ID of the task to inspect.")
    run = commands.add_parser("run", help="Run an evaluation using a TOML file.")
    run.add_argument("config_path", type=Path, help="Path to the evaluation TOML file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch supported commands and report failures on standard error."""
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "init":
        try:
            _create_template()
        except FileExistsError:
            print("error: evaluation.toml already exists.", file=sys.stderr)
            return 1
        except OSError:
            print("error: Cannot create evaluation.toml.", file=sys.stderr)
            return 1
        return 0
    from evals.errors import EvaluationPreparationError

    try:
        _validate_data_directory()
    except EvaluationPreparationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if arguments.command in {"tasks", "show"}:
        from evals.tasks import (
            format_task_detail,
            format_task_list,
            get_task,
            list_domains,
            list_tasks,
        )

        try:
            if arguments.command == "tasks":
                output = (
                    "\n".join(list_domains())
                    if arguments.domain is None
                    else format_task_list(list_tasks(arguments.domain))
                )
            else:
                output = format_task_detail(
                    get_task(arguments.domain, arguments.task_id)
                )
        except EvaluationPreparationError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        print(output)
        return 0
    from evals.config import ConfigError, load_config
    from evals.runner import EvaluationInfrastructureError, run_evaluation

    try:
        config = load_config(arguments.config_path)
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    try:
        results_path = run_evaluation(config, config_path=arguments.config_path)
    except EvaluationPreparationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except EvaluationInfrastructureError as error:
        print(f"error: {error}", file=sys.stderr)
        print(f"Results: {error.results_path}", file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 -- CLI boundary must not print external exception data.
        # External exceptions can contain credentials or server response bodies.
        print("error: Evaluation failed.", file=sys.stderr)
        return 1
    print(results_path)
    return 0


if __name__ == "__main__":
    # Direct script execution otherwise exposes scripts/, not the project root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
