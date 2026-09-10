# Mock 기준 평가 기록

## 상태

- 문서 목적: 로드맵 3단계의 기준 평가 대상, 선정 근거, 평가 조건, 결과와 분석을 한곳에 이어서 기록한다.
- 현재 단계: 이슈 #9의 후보 분석과 사용자 합의를 완료했다.
- 현재 범위: task 선정과 관찰 기준 정리만 수행한다. 모델 평가 실행과 반복 횟수 결정은 포함하지 않는다.

## 학습 목표와 완료 조건

이번 작업의 목표는 공식 mock task 정의와 실제 evaluator 동작을 연결해 기준 평가에서 무엇을 관찰할지 정하는 것이다. 낮은 점수를 얻거나 task 수를 늘리는 것이 목적이 아니다.

Task를 선정하는 이유는 TaskAgent의 기준 점수만 얻기 위해서가 아니라, 서로 다른 Agent 행동을 관찰하고 이후 분석할 실패 또는 개선할 행동을 특정하기 위해서다. 각 task를 하나의 진단용 실험으로 사용한다.

- 단순 생성과 상태 변경으로 기본 Agent loop와 WRITE 도구 사용을 관찰한다.
- 같은 상태 변경을 message history 유무에 따라 비교해 conversation state 활용의 영향을 분리한다.
- 정책상 처리할 수 없는 요청으로 도구 경계와 escalation 판단을 관찰한다.
- 공식 점수와 trajectory 관찰을 함께 사용해 점수가 보장하는 결과와 보장하지 않는 행동을 구분한다.
- 로드맵 4단계에서 개선 하나를 적용할 때 동일 task와 조건으로 전후를 비교할 기준을 마련한다.

다음 조건을 모두 만족하면 task 선정 작업이 완료된다.

- 사용자와 합의한 task ID 목록과 선정·제외 이유가 명시되어 있다.
- 각 task의 사용자 목표, 초기 조건, 관찰할 행동을 설명할 수 있다.
- 실제 최종 점수에 포함되는 검사와 진단 또는 수동 관찰 항목이 구분되어 있다.
- 생략된 평가 필드의 기본값과 현재 프로젝트의 실행 평가 모드가 확인되어 있다.
- 후속 기준 평가가 이 문서를 입력으로 사용할 수 있다.

## 확인한 환경과 공식 근거

현재 프로젝트는 Python `>=3.12,<3.14`와 로컬 경로 dependency `../tau2-bench`를 사용한다. 조사 시점의 tau2 패키지 버전은 `1.0.1`, 저장소 revision은 `fc0055dc4e0a316c3f83133267fbd6faaa770992`이다.

| 확인 대상 | 근거 경로 | 확인 내용 |
| --- | --- | --- |
| 프로젝트 범위 | `AGENTS.md`, `docs/ROADMAP.md` | 공식 mock domain을 사용하고 tau2-bench 코드는 수정하지 않는다. |
| dependency와 버전 | `pyproject.toml`, `uv.lock` | `tau2`는 `../tau2-bench`에서 가져온다. |
| 후보 task 원문 | `../tau2-bench/data/tau2/domains/mock/tasks.json` | 사용자 목표, 초기 상태, 평가 필드와 reference actions |
| 기본 환경 상태 | `../tau2-bench/data/tau2/domains/mock/db.json` | `user_1`과 pending 상태의 `task_1`이 존재한다. |
| mock 정책 | `../tau2-bench/data/tau2/domains/mock/policy.md` | 생성·상태 규칙과 삭제 금지 및 human transfer 요구 |
| agent 도구 | `../tau2-bench/src/tau2/domains/mock/tools.py` | `create_task`, `update_task_status`, `transfer_to_human_agents`의 동작과 도구 유형 |
| task schema | `../tau2-bench/src/tau2/data_model/tasks.py` | 평가 필드의 기본값과 action 비교 방식 |
| 평가 설명 | `../tau2-bench/docs/evaluation.md` | reward 조합과 reference actions의 의미 |
| evaluator 조합 | `../tau2-bench/src/tau2/evaluator/evaluator.py` | `EvaluationType`별 검사 실행과 reward 조합 |
| 세부 evaluator | `../tau2-bench/src/tau2/evaluator/evaluator_env.py`, `evaluator_action.py`, `evaluator_communicate.py` | DB, action, communicate 검사의 실제 동작 |
| 초기 이력 재생 | `../tau2-bench/src/tau2/environment/environment.py` | message history 안의 mutating tool call을 환경에 재생하는 방식 |
| 공식 실행 진입점 | `../tau2-bench/src/tau2/runner/batch.py` | `run_domain()`에서 `run_tasks()`로 이어지는 평가 모드 |
| 프로젝트 실행 경로 | `scripts/evaluate.py`, `evals/runner.py` | `TextRunConfig`를 만들어 공식 `run_domain()`을 호출한다. |

## 현재 실행 경로의 실제 채점 방식

### 평가 모드

`evals/runner.py`는 `TextRunConfig`를 구성한 뒤 공식 `run_domain()`을 호출한다. `run_domain()`은 `evaluation_type`을 별도로 전달하지 않으므로 `run_tasks()`의 기본값인 `EvaluationType.ALL`이 적용된다.

공식 `docs/evaluation.md`에는 공식 CLI runner가 `ALL_WITH_NL_ASSERTIONS`를 사용한다고 설명된 부분이 있지만, 현재 프로젝트는 그 CLI 경로가 아니라 위 API 경로를 사용한다. 따라서 현재 기준 평가의 실제 모드는 `ALL`이다.

### 기본값과 최종 reward

- task가 `reward_basis`를 생략하면 `EvaluationCriteria`의 기본값 `[DB, COMMUNICATE]`가 적용된다.
- 최종 reward는 `reward_basis`에 포함된 component reward의 곱이다.
- `ALL`은 environment, action, communicate evaluator를 실행한다.
- NL evaluator는 `ALL_WITH_NL_ASSERTIONS`를 사용하거나 task의 `reward_basis`에 `NL_ASSERTION`이 포함된 경우에만 실행된다.
- `actions`는 gold environment에서 목표 DB 상태를 만드는 reference trajectory로 항상 사용된다.
- reference action과 같은 호출이 trajectory에 있는지는 `action_checks`에 진단값으로 남지만, `ACTION`이 `reward_basis`에 있을 때만 최종 reward에 반영된다.
- `ActionEvaluator`는 AssistantMessage와 UserMessage 양쪽의 tool calls를 모은 뒤 각 reference action과 일치하는 호출이 어디엔가 존재하는지 검사한다. action의 `requestor`나 호출 순서는 비교하지 않는다. 따라서 `actions`를 Agent가 반드시 따라야 할 호출 순서로 해석하지 않는다.
- `communicate_info`가 없거나 비어 있으면 communicate reward는 `1.0`이다.
- `nl_assertions`가 존재해도 현재 `ALL` 모드에서 `NL_ASSERTION`이 reward basis에 없으면 검사 자체가 실행되지 않는다.

## 후보 task 비교

### 요약

| Task ID | 사용자 목표와 초기 조건 | Reference action | 실제 reward basis | 최종 점수가 직접 확인하는 것 | 점수 밖에서 관찰할 것 |
| --- | --- | --- | --- | --- | --- |
| `create_task_1` | 기본 DB의 `user_1`에게 `Important Meeting` task 생성 | `create_task(user_id="user_1", title="Important Meeting")` | 생략 → `DB`, `COMMUNICATE` | reference action을 재생한 것과 같은 최종 DB. communicate 항목이 없어 communicate 검사는 자동 통과한다. | 적절한 WRITE 도구 선택, 인자 구성, 불필요한 호출, 성공 확인 표현 |
| `update_task_1` | 기본 DB에 있는 pending `task_1`을 completed로 변경 | `update_task_status(task_id="task_1", status="completed")` | 생략 → `DB`, `COMMUNICATE` | `task_1`의 최종 상태를 포함한 전체 DB 일치. communicate 검사는 자동 통과한다. | 기존 task를 새로 만들지 않는지, 올바른 ID·상태 사용, 성공 확인 표현 |
| `update_task_with_message_history` | 이전 대화에서 생성한 `task_2`를 completed로 변경 | `update_task_status(task_id="task_2", status="completed")` | 생략 → `DB`, `COMMUNICATE` | 초기 이력을 재생한 뒤 `task_2`가 completed인 목표 DB와의 일치. communicate 검사는 자동 통과한다. | 이전 대화와 tool result에서 `task_2`를 이어받는지, 중복 생성·불필요한 조회 여부, 맥락 인정과 성공 확인 표현 |
| `impossible_task_1` | 모든 task 삭제 요청. 정책상 삭제 금지이며 human transfer 필요 | `transfer_to_human_agents(...)` | 명시 → `DB`, `ACTION` | DB를 변경하지 않았고 `transfer_to_human_agents` 호출이 존재하는지 | 삭제 불가 이유를 정확히 설명하는지, transfer summary가 충분한지, 잘못된 대안 안내 여부 |

### `create_task_1`

- 정책 관련 조건: task에는 title이 필요하고 기존 사용자만 task를 만들 수 있다.
- `create_task`는 WRITE 도구이며 성공 시 새 task를 pending 상태로 만들고 사용자의 task 목록에도 추가한다.
- `env_assertions`와 `communicate_info`는 없고, 성공 확인에 관한 `nl_assertions` 하나가 있다.
- 하지만 실제 모드가 `ALL`이고 `NL_ASSERTION`이 reward basis에 없으므로 성공 확인 문장은 검사되지 않는다.
- 따라서 최종 점수 `1.0`은 목표 DB 상태를 만들었다는 사실은 보여주지만, 사용자에게 생성을 확인해 주었다는 사실은 보여주지 않는다.

### `update_task_1`

- 기본 DB에는 `task_1`이 pending 상태로 존재한다.
- `update_task_status`는 WRITE 도구이며 상태는 정책상 `pending` 또는 `completed`만 허용된다.
- `env_assertions`와 `communicate_info`는 없고, 성공 확인에 관한 `nl_assertions` 하나가 있다.
- 최종 점수는 사실상 DB 상태 변경만 판별한다. 올바른 사용자 안내는 trajectory에서 별도로 읽어야 한다.
- 이 task는 message history가 없는 단순 상태 변경 기준점으로 사용할 수 있다.

### `update_task_with_message_history`

- 초기 message history에는 `create_task` 호출과 그 결과인 `task_2`가 기록되어 있다.
- environment의 `set_state()`는 message history에서 mutating tool call과 tool result를 찾아 재생하므로 평가 시작 상태에 `task_2`가 생성된다.
- reference action은 그 `task_2`를 completed로 변경한다.
- `nl_assertions`는 이전 맥락 인정과 성공 확인을 요구하지만 현재 평가 모드에서는 실행되지 않는다.
- 따라서 점수와 별개로 agent가 이전 대화의 task ID를 실제로 사용했는지, task를 중복 생성하지 않았는지, 맥락을 사용자에게 올바르게 이어 설명했는지를 trajectory에서 확인해야 한다.

### `impossible_task_1`

- mock policy는 task 삭제를 금지하고 human agent로 transfer하도록 요구한다. 삭제 도구도 제공되지 않는다.
- `transfer_to_human_agents`는 GENERIC 도구라 DB를 변경하지 않는다.
- 이 task만 `reward_basis`에 `ACTION`을 명시하므로 reference action의 일치 여부가 최종 점수에 포함된다.
- reference action의 `compare_args`는 빈 목록이다. `Action.compare_with_tool_call()`의 구현상 이는 tool 이름만 같으면 summary 인자 내용, 호출 순서, action의 `requestor`와 관계없이 action match가 된다는 뜻이다.
- 최종 점수는 `DB × ACTION`이다. 즉 DB를 변경하지 않고 transfer 도구를 호출하면 통과할 수 있지만, 삭제 불가 설명의 정확성이나 transfer summary의 품질은 보장하지 않는다.

## 선정안과 근거

### 확정 목록

1. `create_task_1`
2. `update_task_1`
3. `update_task_with_message_history`
4. `impossible_task_1`

네 task를 모두 선정한다.

- `create_task_1`은 새 객체 생성과 생성 인자 구성을 관찰한다.
- `update_task_1`은 대화 이력 없이 기존 객체를 변경하는 단순 기준점이다.
- `update_task_with_message_history`는 같은 상태 변경을 이전 대화에 의존하는 조건으로 반복하므로, `update_task_1`과 비교해 conversation state 활용의 영향을 분리해 볼 수 있다.
- `impossible_task_1`은 성공적인 DB 쓰기가 아니라 정책 준수와 escalation을 관찰하며, 네 후보 중 유일하게 `ACTION`이 최종 점수에 포함된다.

평가 수만 최소화한다면 `update_task_1`을 제외하고 history가 있는 변형만 남길 수 있다. 그러나 그러면 동일한 update 도구에서 message history 유무를 비교할 기준점이 사라진다. 현재 학습 목표에는 네 task를 모두 유지하는 편이 더 적합하므로 제외하지 않았다.

### 합의 기록

- 합의일: 2026-09-10
- 최종 task 목록: `create_task_1`, `update_task_1`, `update_task_with_message_history`, `impossible_task_1`
- 제외 task: 없음
- 합의 근거: 생성, 기본 상태 변경, message history 기반 상태 변경, 정책상 불가능한 요청을 각각 관찰하고, 두 update task를 비교해 conversation state 활용의 영향을 분리하기 위해 네 후보를 모두 유지한다.

## 후속 기준 평가에서 사용할 관찰 체크리스트

공통으로 다음을 trajectory와 `reward_info`에서 분리해 확인한다.

- 사용자 요청과 Agent의 첫 판단
- 호출한 도구 이름, arguments, 호출 주체와 실제 순서
- 도구 result 또는 error와 이어지는 Agent 응답
- 종료 사유
- 최종 reward와 `reward_breakdown`
- DB check, action checks, communicate checks 및 NL assertion 검사 실행 여부
- 점수가 직접 보장하지 않는 잘못된 안내, 불필요한 호출, 맥락 누락
- 확인된 사실과 원인 가설의 구분

Task별 핵심 관찰점은 다음과 같다.

| Task ID | 핵심 관찰점 |
| --- | --- |
| `create_task_1` | `user_1`과 정확한 title을 사용해 한 번만 생성하는가, 결과를 사용자에게 사실대로 확인하는가 |
| `update_task_1` | `task_1`을 새로 만들지 않고 completed로 변경하는가, 결과를 사실대로 설명하는가 |
| `update_task_with_message_history` | 이전 tool result의 `task_2`를 활용하는가, 이미 수행된 생성을 반복하지 않는가, 이전 맥락을 자연스럽게 이어가는가 |
| `impossible_task_1` | 삭제를 시도하거나 가능하다고 말하지 않는가, 정책 근거로 transfer하는가, summary가 요청을 충분히 전달하는가 |

## 후속 기록 영역

다음 항목은 task 목록 합의 이후의 별도 설정·평가 작업에서 채운다.

### 기준 평가 조건

- Agent 코드와 프롬프트:
- Agent 모델과 생성 옵션:
- User Simulator 모델과 생성 옵션:
- seed:
- 반복 횟수:
- 실행 제한:
- 실행 명령:

### 실행별 결과

- 실행 artifact 경로:
- task별 실행 수와 종료 사유:
- task별 공식 점수와 세부 검사:

### 분석

- 관찰 사실:
- 분석할 실패 또는 개선할 행동:
- 원인 가설:
- 확인하지 못한 내용:
