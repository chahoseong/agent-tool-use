# AGENTS.md

## 평가 환경

- `tau2-bench`의 공식 mock domain
- 공식 policy, tools, tasks, user simulator, orchestrator, evaluator
- `tau2-bench` 코드는 수정하지 않음

## Commands

프로젝트 루트에서 실행한다.

- `uv run ruff check <path>`
- `uv run ruff format --check <path>`
- `uv run mypy <path>`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy`
- `uv run python -m pytest`
- `uv run python -m pytest <path>`

## Testing

### Principles

- Do not force a one-to-one mapping between checklist items and tests. Before adding a test, identify the requirement or risk it covers, the specific failure or regression it catches, and why existing tests would not catch that failure.
- Do not add or retain a test that has no distinct failure-detection value.
- Prefer assertions about outcomes and state over implementation interactions. Assert call order or another interaction only when that interaction is itself part of the contract.

### Naming

- Test functions start with `test_` and use English ASCII `snake_case`.
- Name tests after the behavior they guarantee, not an internal method or implementation step.
- After `test_`, express the stable subject or capability, the expected observable behavior or outcome, and then any condition needed to distinguish that behavior.
- Express expected behavior with an active present-tense verb such as `returns`, `raises`, `rejects`, `preserves`, or `stops`. Choose a verb that matches the actual observable contract.
- Use `when` for general conditions. Use a more precise connector such as `before`, `after`, `without`, or `from` when it expresses the relationship more accurately. Omit the condition when it is unnecessary.
- Include only conditions that distinguish the expected result. Include a concrete ID or value only when that value is itself part of the contract or a boundary condition.
- Mention calls, ordering, or data transfer only when that interaction is an explicit protocol or acceptance contract.
- Treat `and` as a signal to check whether the test covers multiple independent behaviors. Keep it only when both clauses form one indivisible workflow contract.
- For parametrized tests, let the function name describe the behavior shared by every case. Add an explicit domain-oriented parameter ID only when pytest's generated ID does not identify the case clearly.
- Do not impose a fixed character limit. Preserve the expected behavior and important condition, and investigate multiple behaviors or irrelevant setup details before shortening a long name with abbreviations.
- Use canonical project and domain terminology consistently. Do not introduce a synonym for an existing concept, and use abbreviations only when they are established in the project or broadly understood.
- Apply these rules to new or meaningfully modified tests. Do not bulk-rename existing tests solely for stylistic consistency.

Examples:

- `test_agent_returns_final_text_without_tool_calls`
- `test_get_order_returns_not_found_when_order_id_is_unknown`
- `test_agent_stops_before_executing_tool_from_fifth_model_call`

Avoid:

- `test_get_order_works`
- `test_should_return_error`
- `test_customer_001_order_999`

These rules are based on [pytest's test discovery conventions](https://docs.pytest.org/en/stable/explanation/goodpractices.html#conventions-for-python-test-discovery), [PEP 8](https://peps.python.org/pep-0008/#function-and-variable-names), the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#s3.16-naming), [*Software Engineering at Google*](https://abseil.io/resources/swe-book/html/ch12.html#name-tests-after-the-behavior-being-tested), and [Microsoft unit testing best practices](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#follow-test-naming-standards).