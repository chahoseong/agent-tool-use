# Mock 기준 평가 기록

## 목적

공식 mock task로 TaskAgent의 서로 다른 행동을 관찰하고, 이후 분석할 실패 또는 개선할 행동을 특정한다. Task 수를 늘리거나 낮은 점수를 얻는 것이 목적은 아니다. 실제 평가 조건·결과·분석은 이 문서에 필요한 결론만 이어서 기록한다.

## 공식 근거

- Task와 초기 상태: `../tau2-bench/data/tau2/domains/mock/tasks.json`, `db.json`
- 정책과 도구: `../tau2-bench/data/tau2/domains/mock/policy.md`, `../tau2-bench/src/tau2/domains/mock/tools.py`
- 채점 방식: `../tau2-bench/docs/evaluation.md`, `../tau2-bench/src/tau2/evaluator/`
- 현재 실행 경로: `evals/runner.py`, `../tau2-bench/src/tau2/runner/batch.py`

## 채점 해석

- 현재 `run_domain()` 경로는 기본 `EvaluationType.ALL`을 사용한다.
- 생략된 reward basis의 기본값은 `DB + COMMUNICATE`이며, `communicate_info`가 없으면 communicate 검사는 자동 통과한다.
- `actions`는 목표 DB 상태를 만드는 reference trajectory다. 호출 순서를 뜻하지 않으며 `ACTION`이 reward basis에 있을 때만 action match가 최종 점수에 반영된다.
- `ALL`은 action checks를 진단값으로 남기지만, reward basis에 없는 `nl_assertions`는 실행하지 않는다.
- 따라서 공식 점수와 별도로 도구 선택·인자, 불필요한 호출, 이전 맥락 활용, 사용자 안내를 trajectory에서 관찰한다.

## 확정 Task

| Task ID | 사용자 목표와 초기 조건 | 선정 이유와 관찰 행동 | 실제 점수와 한계 |
| --- | --- | --- | --- |
| `create_task_1` | 기존 `user_1`에게 `Important Meeting` 생성 | 기본 WRITE 도구 선택, 인자 구성, 결과 안내 관찰 | 사실상 목표 DB 상태만 판별하며 성공 확인 문장은 검사하지 않음 |
| `update_task_1` | pending 상태의 기존 `task_1`을 completed로 변경 | 대화 이력 없는 기본 상태 변경 기준점 | 사실상 목표 DB 상태만 판별하며 결과 안내는 별도 관찰 |
| `update_task_with_message_history` | 이전 대화에서 생성된 `task_2`를 completed로 변경 | 이전 tool result 활용, 중복 생성 여부를 기본 update와 비교 | 초기 이력을 재생한 목표 DB를 판별하며 맥락 인정 문장은 검사하지 않음 |
| `impossible_task_1` | 정책상 금지된 전체 task 삭제 요청 | 삭제를 시도하지 않고 human transfer하는지 관찰 | `DB + ACTION`; transfer 호출은 검사하지만 `compare_args=[]`이므로 summary 품질은 보장하지 않음 |

2026-09-10 사용자와 네 task를 모두 선정하기로 합의했다. 두 update task를 함께 유지해 message history 유무의 영향을 비교한다.

## 기준 평가 조건

- 설정 파일: `configs/baseline.toml`
- 평가 규모: 4 tasks × 3 trials = 총 12회
- seed: `42`
- 실행 제한: `max_steps=200`, `max_errors=10`
- 동시 실행 수: `1`
- Agent와 User Simulator의 모델·서버는 설정 파일의 기존 값을 유지한다.
- 역할별 generation 옵션은 생략한다. 생략된 값을 `0`이나 고정값으로 추정하지 않는다.
- 동일 설정과 seed가 동일한 모델 응답을 보장하지 않는다.

이 단계에서는 설정만 검증하고 실제 모델 평가를 실행하지 않는다. 실행 시 생성되는 `metadata.toml`을 prompt, project commit, 실제 적용 설정의 근거로 사용한다.
