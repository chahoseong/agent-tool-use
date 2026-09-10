# tau2-bench 평가 결과 해석

## Simulation Overview

```text
Task ID: create_task_1
Trial: 0
Duration: 21.35s
Mode: half_duplex
Termination Reason: TerminationReason.USER_STOP

Agent Cost: $0.0000
User Cost: $0.0000

Reward: ✅ 1.0000 (COMMUNICATE: 1.0, DB: 1.0)
DB Check: ✅ 1.0

Action Checks:
  - 0: agent create_task [write] ✅ 1.0

Partial Action Reward: 1/1 (100.0%)
  Write: 1/1 (100.0%)

Additional Info:
  env: None
  nl: None
  communicate: {'note': 'No communicate_info to evaluate'}
  action: None
```

`Simulation Overview`는 task를 한 번 실행한 결과를 보여줍니다. 여러 task나 반복 실행 전체를 집계한 요약과는 구분됩니다.

### 실행 정보

| 항목 | 의미 | 이번 결과의 해석 |
| --- | --- | --- |
| `Task ID` | 실행한 task의 식별자 | `create_task_1`을 실행했습니다. |
| `Trial` | 같은 task의 반복 실행 번호. 0부터 시작합니다. | `0`은 첫 번째 실행입니다. |
| `Duration` | Orchestrator가 기록한 시뮬레이션 실행 시간 | 대화와 도구 실행에 `21.35s`가 걸렸습니다. 평가 명령 전체의 소요 시간은 아닙니다. |
| `Mode` | 대화를 진행하는 방식 | `half_duplex`는 사용자와 에이전트가 차례로 응답하는 방식입니다. |
| `Termination Reason` | 시뮬레이션이 종료된 이유 | `USER_STOP`은 사용자 시뮬레이터가 종료 신호를 보냈다는 뜻입니다. 작업 성공 여부는 채점 결과에서 별도로 확인합니다. |

### 평가 결과

| 항목 | 의미 | 이번 결과의 해석 |
| --- | --- | --- |
| `Reward` | task의 `reward_basis`에 지정된 평가 항목으로 계산한 최종 점수 | `DB`와 `COMMUNICATE`를 반영해 `1.0`을 받았습니다. |
| `DB Check` | 기대 행동을 실행한 DB 상태와 실제 실행 기록을 재생한 DB 상태의 일치 여부 | `1.0`은 두 상태가 일치했다는 뜻입니다. task가 존재하는지만 검사하는 것이 아니라 비교 대상 DB 상태를 확인합니다. |
| `Action Checks` | task에 정의된 기대 도구 호출과 실행 기록의 일치 여부 | `create_task` 호출이 기대한 인자와 일치했습니다. `0`은 검사 항목 번호이고, `agent`는 호출 주체, `[write]`는 데이터를 변경하는 도구 유형입니다. |
| `Partial Action Reward` | 기대 행동 중 일치한 행동의 수와 비율 | `1/1`은 기대 행동 1개 중 1개가 일치했다는 뜻입니다. 실제 도구 호출 횟수가 1회였다는 의미는 아닙니다. |
| `Write` | 기대 행동 중 쓰기 도구에 해당하는 항목의 일치 수와 비율 | 기대한 쓰기 행동 1개가 일치했습니다. |

이번 실행은 `get_users`와 `create_task`를 호출했지만, task에 정의된 기대 행동은 `create_task` 하나이므로 `Partial Action Reward`의 분모는 1입니다.

검사 결과가 표시된다고 모두 최종 점수에 반영되는 것은 아닙니다. 이번 task의 `reward_basis`는 `DB`와 `COMMUNICATE`이며, `Action Checks`와 `Partial Action Reward`는 최종 점수에 직접 반영되지 않습니다.

### 비용과 추가 정보

| 항목 | 의미 | 이번 결과의 해석 |
| --- | --- | --- |
| `Agent Cost` | 에이전트의 모델 호출에 대해 계산된 비용 | `$0.0000`으로 표시되지만, 이번 모델은 비용 정보 조회에 실패했으므로 실제 비용이 0이라는 근거로 사용할 수 없습니다. |
| `User Cost` | 사용자 시뮬레이터의 모델 호출에 대해 계산된 비용 | 사용자 시뮬레이터도 LLM을 사용합니다. 이번 실행에서는 에이전트와 마찬가지로 비용 정보를 찾지 못했습니다. |
| `Additional Info` | 개별 평가기가 제공하는 부가 정보 | `env`, `nl`, `communicate`, `action`별 설명이나 참고 정보를 확인할 수 있습니다. |

`communicate`의 `No communicate_info to evaluate`는 검사할 전달 정보가 task에 지정되지 않았다는 뜻입니다. 이 경우 `COMMUNICATE`에는 `1.0`이 부여됩니다. 따라서 이 값만 보고 완료 안내의 내용이 올바르다고 검증되었다고 해석하면 안 됩니다.

`env: None`, `nl: None`, `action: None`은 해당 부가 정보가 없다는 뜻이며, 검사 성공이나 미실행 여부를 그 값만으로 판단할 수는 없습니다. 실제로 이번 실행에서는 DB 검사와 행동 검사를 수행했습니다. 자연어 조건 검사는 기본 평가 모드에서 `reward_basis`에 `NL_ASSERTION`이 없어 생략되었으며, 이는 task의 평가 기준과 개별 검사 결과를 함께 확인해야 알 수 있습니다.

## Agent Performance Metrics

```text
═══ Overview ═══
Total Simulations  1
Total Tasks  1

═══ Reward Metrics ═══
🏆 Average Reward  1.0000
Pass^1  1.000
💰 Avg Cost/Conversation  $0.0000

═══ Action Metrics ═══
📖 Read Actions  -
✏️  Write Actions  1/1 (100.0%)

═══ DB Match ═══
🗄️  DB Match  ✓ 1 / ✗ 0 (100.0%)

═══ Authentication ═══
Not Checked  1

═══ Termination ═══
🛑 Normal Stop  1 (👤 1 / 🤖 0)

═══ LLM Judge Review ═══
🤖 Agent Errors  0 errors
  Sims by severity  -
👤 User Errors  0 errors
  Sims by severity  -
```

`Agent Performance Metrics`는 저장된 실행 결과를 모아 보여주는 집계 화면입니다. `Simulation Overview`가 한 번의 실행을 설명한다면, 이 화면은 여러 task와 반복 실행의 성과를 요약합니다.

### 평가 범위

| 항목 | 의미 | 이번 결과의 해석 |
| --- | --- | --- |
| `Total Simulations` | 집계 대상 시뮬레이션 수 | 실행 1개를 집계했습니다. |
| `Total Tasks` | 집계 대상의 서로 다른 task 수 | `create_task_1` 한 가지를 평가했습니다. |

현재 공식 구현은 인프라 오류로 종료된 실행을 성과 지표에서 제외하고 별도로 집계합니다. 따라서 평가 범위를 볼 때는 정상적으로 평가된 실행 수와 인프라 오류 수도 구분해야 합니다.

### 점수와 비용

| 항목 | 의미 | 이번 결과의 해석 |
| --- | --- | --- |
| `Average Reward` | 집계 대상 실행들의 reward 평균 | 실행 1개의 reward가 1.0이므로 평균도 `1.0000`입니다. |
| `Pass^1` | task별 성공 비율을 구한 뒤 task 전체에서 평균한 값 | task 1개를 한 번 실행해 성공했으므로 `1.000`입니다. |
| `Avg Cost/Conversation` | 실행당 에이전트 모델 호출 비용의 평균 | 현재 구현은 사용자 시뮬레이터 비용을 포함하지 않습니다. 이번에는 모델 비용 정보 조회에 실패했으므로 `$0.0000`을 실제 비용으로 해석할 수 없습니다. |

`Average Reward`는 점수의 평균이고, `Pass^1`은 성공 여부를 기준으로 계산합니다. 두 값이 이번에는 같지만, 부분 점수가 있거나 task별 실행 횟수가 다르면 서로 달라질 수 있습니다.

`Pass^k`는 같은 task를 k회 실행했을 때 **모두 성공하는 일관성**을 나타내는 추정 지표입니다. 관측된 반복 실행 중 k개를 골랐을 때 모두 성공하는 비율을 task별로 계산한 뒤 평균합니다. k번 중 한 번이라도 성공하면 되는 지표와는 다릅니다. 이번에는 한 번만 실행했으므로 `Pass^1`만 표시됩니다.

### 행동과 DB 상태

| 항목 | 의미 | 이번 결과의 해석 |
| --- | --- | --- |
| `Read Actions` | 기대한 읽기 행동 중 일치한 행동의 수와 비율 | `-`는 집계할 읽기 행동 검사 항목이 없다는 뜻입니다. |
| `Write Actions` | 기대한 쓰기 행동 중 일치한 행동의 수와 비율 | `1/1 (100.0%)`은 기대한 쓰기 행동 1개가 일치했다는 뜻입니다. |
| `DB Match` | DB 검사에서 일치한 실행 수, 불일치한 실행 수와 일치 비율 | `✓ 1 / ✗ 0 (100.0%)`은 검사한 실행 1개에서 DB 상태가 일치했다는 뜻입니다. |

행동 지표는 실제 도구 호출 횟수를 세는 것이 아니라 task에 정의된 기대 행동의 검사 결과를 집계합니다. 이번에는 `get_users`를 사용했지만 기대한 읽기 행동이 평가 기준에 없으므로 `Read Actions`는 `-`로 표시됩니다.

### 인증과 종료

| 항목 | 의미 | 이번 결과의 해석 |
| --- | --- | --- |
| `Authentication / Not Checked` | 인증 검사 결과가 없는 실행 수 | `1`은 해당 결과가 없는 실행이 1개라는 뜻입니다. 인증에 실패했거나 인증이 불필요하다고 판정되었다는 의미는 아닙니다. |
| `Normal Stop` | 사용자 또는 에이전트의 종료 신호로 끝난 실행 수 | `1 (👤 1 / 🤖 0)`은 사용자 종료 1회, 에이전트 종료 0회를 뜻합니다. |

`Normal Stop`은 종료 방식을 나타냅니다. 작업을 성공적으로 수행했는지는 reward와 개별 검사 결과를 함께 확인해야 합니다.

### LLM 리뷰 결과

| 항목 | 의미 | 이번 결과를 읽을 때 주의할 점 |
| --- | --- | --- |
| `Agent Errors` | 별도 LLM 리뷰에 기록된 에이전트 오류의 총수 | `0 errors`만으로 리뷰를 수행해 문제가 없었다고 판단할 수 없습니다. |
| `User Errors` | 별도 LLM 리뷰에 기록된 사용자 시뮬레이터 오류의 총수 | 사용자 시뮬레이터의 행동에 대한 리뷰 결과이며, 에이전트 오류와 구분됩니다. |
| `Sims by severity` | 리뷰에서 실행별 최대 오류 심각도에 따라 분류한 실행 수 | `-`는 표시할 분류 집계가 없다는 뜻입니다. |

이 항목은 실행 중 발생한 예외나 도구 오류 전체를 세는 것이 아닙니다. 별도 리뷰 기록을 집계하며, 리뷰 기록이 없어도 `0 errors`로 표시될 수 있습니다. 따라서 이 화면의 0만으로 오류가 없었다고 결론 내리기보다, 리뷰 수행 여부를 먼저 확인해야 합니다.
