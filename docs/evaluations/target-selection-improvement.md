# 조회 근거에 기반한 변경 대상 판단 개선 실험

## 상태와 범위

- 관련 이슈: [#15](https://github.com/chahoseong/agent-tool-use/issues/15), 상위 에픽 [#14](https://github.com/chahoseong/agent-tool-use/issues/14), 선행 분석 [#13](https://github.com/chahoseong/agent-tool-use/issues/13), [#8](https://github.com/chahoseong/agent-tool-use/issues/8).
- 작성일: 2026-09-11. **이슈 #15의 준비 작업을 완료했다. 프롬프트 문구·위치, 기대 행동·판정 기준, 재사용 방침과 신규 평가 횟수를 확정하고 설정·후속 실행 절차를 준비했다. 실제 평가는 실행하지 않았다.**
- 사용자는 전체 계획을 승인했고, 각 단계 시작 전 별도 승인과 완료 후 상세 설명을 요청했다. 1단계 task·채점 분석과 2단계 기존 결과 비교 조사를 마쳤으며, 승인받은 3단계에서 이 초안을 작성했다.
- 4단계에서 사용자가 P1의 정확한 문구·적용 위치, 기대 행동·판정 기준, 기존 두 결과를 정량 기준으로 재사용하지 않는 방침을 각각 확정했다. 신규 기준 12회·변경 후 12회로 준비한다. 5·6단계도 별도 승인 후 완료했으며 실제 후속 실행은 아직 승인받지 않았다.
- 승인받은 5단계에서 설정 추가·검증을 완료하고, 6단계에서 실행·중단·재개 및 원본 보존 절차를 작성·점검했다. 현재 Agent 프롬프트에 확정 문구를 적용하지 않았다.
- 이슈 #15에서는 실제 LLM 평가를 실행하지 않는다. task·예약·상품 ID와 reference actions는 분석용이며 Agent 입력에 추가하지 않는다.
- 공식 benchmark의 코드·데이터·정책·도구·User Simulator·orchestrator·evaluator는 변경하지 않는다. 비교 세트 확대, 별도 state 구조, 추가 Agent 호출, 새 평가 기능·dependency·architecture를 도입하지 않는다. airline `39`·`44`는 비교 대상이 아니다.

이 문서의 파일 경로는 별도 표시가 없으면 프로젝트 루트 기준이다. `../tau2-bench/`는 공식 benchmark 형제 저장소다. 후속 작업은 이 문서에 확정 내용·실행 결과·결론을 이어서 기록한다.

## 문제와 학습 목표

기존 airline `42` 실행에서 타인 승객의 예약을 취소 대상으로 제안하는 오류와, 필요한 예약 조회를 누락한 채 신규 예약을 제안하는 오류를 관찰했다. 두 trial 모두 User Simulator가 확인 메시지와 함께 `###STOP###`을 출력하여 실제 쓰기 전에 종료됐다. 잘못된 제안은 관찰 사실이지만 잘못된 DB 변경을 실행했을 것이라고 단정할 수 없다.

이번 학습 목표는 **대상 식별에 필요한 조회와 사용자 조건·제외 조건·정책 대조를 명시하는 프롬프트가 판단 오류를 줄이고 필요한 변경 완료에 도움이 되는지, 부작용은 없는지 구분하는 것**이다. 별도 대화 state의 필요성이나 정보 유실의 원인을 입증하는 실험은 아니다.

확인한 프로젝트 코드: `agents/task_agent.py`, `evals/config.py`, `evals/tasks.py`, `evals/runner.py`, `evals/metadata.py`, `scripts/evaluate.py`.

공식 근거:

- `../tau2-bench/data/tau2/domains/{airline,retail}/{tasks.json,policy.md,db.json}`
- `../tau2-bench/src/tau2/domains/{airline,retail}/{environment.py,tools.py,data_model.py}`
- `../tau2-bench/src/tau2/evaluator/{evaluator.py,evaluator_env.py,evaluator_action.py,evaluator_communicate.py,evaluator_nl_assertions.py,reviewer.py}`
- `../tau2-bench/src/tau2/runner/{batch.py,checkpoint.py,helpers.py}`
- `../tau2-bench/src/tau2/user/user_simulator.py`, `../tau2-bench/data/tau2/user_simulator/simulation_guidelines.md`
- `../tau2-bench/docs/evaluation.md`. 문서와 구현이 다르면 이번에 사용하는 구현과 저장 결과를 근거로 삼는다.

## 가설과 확정한 변경 문구 — Agent 미적용

가설: 필요한 조회와 대조 기준을 명시하면 조회 누락·조건 오해로 발생하는 잘못된 변경 제안이 줄고, 필요한 변경을 정확히 완료하는 데 도움이 될 것이다.

현재 `AGENT_PROMPT`:

```text
You are a helpful customer service agent.

Follow the policy strictly. Use the provided tools to help the user.
```

사용자와 확정한 추가 문구 P1:

```text
Before proposing changes, use the available tools to retrieve the records needed to identify the correct targets. Check those records against the user's requirements, exclusions, and the policy. Do not conclude that a relevant record is absent, or expand the scope of work, based on information you have not checked.
```

문구의 의미는 변경 제안 전에 대상 식별에 필요한 기록을 조회하고, 사용자 요구·제외 조건·정책과 대조하며, 확인하지 않은 정보를 근거로 기록의 부재를 단정하거나 작업 범위를 넓히지 말라는 것이다. 특정 task·도메인·예약 ID나 정답 호출 순서는 포함하지 않는다.

확정한 후속 적용 위치는 기존 두 문장 뒤, `## Domain Policy` 앞이다. 기존 문구와 policy 결합 방식은 유지하고 위 문구 추가 하나를 실험의 변경으로 삼는다. **현재는 문서에만 있으며 Agent에는 적용하지 않았다.** 변경 전 기준 결과를 확보한 뒤 후속 이슈에서 적용한다.

확정한 기대 행동:

- 단순한 계정 소속이나 날짜 일치만으로 대상을 정하지 않고 실제 영향 대상·개별 구간·사용자 조건을 대조한다.
- 조회하지 않은 레코드를 없는 것으로 간주하지 않는다. 필요한 정보가 부족하면 조회하거나 사용자에게 확인한다.
- 제외 대상은 유지하고 정책상 불가능한 변경은 거절하되, 허용되는 변경까지 불가능하다고 확대 해석하지 않는다.
- 기존 정책에 따라 변경 내용을 설명하고 명시적 확인을 받은 뒤 실행한다. 추가 프롬프트가 정책의 확인·도구 호출 규칙을 대체하지 않는다.
- 조회 증가 자체를 성공으로 보지 않는다. 조회 근거가 올바른 판단과 필요한 완료로 연결되는지 확인한다.

## Task별 요구와 관찰 근거

아래 ID·정답 상태는 평가·분석 담당자를 위한 정보다. Agent는 원래 제공되는 policy·도구·사용자 대화로 필요한 사실을 알아내야 한다. 직접 DB에서 확인한 사실과 실제 trajectory에서 Agent가 조회한 사실은 구분한다. 항공 정책의 기준 시각은 실제 실행일이 아니라 `2024-05-15 15:00:00 EST`다.

### airline `42`: 일정과 승객에 맞는 두 취소 대상

Sophia Martin(`sophia_martin_4574`)은 중복 예약을 조사·정리해 달라고 요청한다. 5월 17일 Dallas에서 New York으로 도착하고 5월 22일 Boston에서 출발한다. 다른 승객의 예약은 변경하지 않겠다는 조건도 확인해야 한다.

| 예약 | 공식 DB에서 확인한 사실 | 필요한 결과 |
| --- | --- | --- |
| `FDZ0T5` | 본인 탑승. 5월 17일 JFK→ORD→PHL, 첫 출발 00:00. 기존 DFW→EWR 도착 21:30보다 먼저 출발 | 취소 |
| `HSR97W` | 본인 탑승. 5월 22일 ORD→PHL→SFO로 Boston 출발 조건과 불일치 | 취소 |
| `SE9KEL` | 계정은 Sophia 소속이지만 승객은 Ivan Brown·Emma Li | 유지. 본인 일정과 충돌한다는 이유로 취소 제안하지 않음 |
| `5BGGWZ` | 대표 경로는 EWR→DFW인 왕복 예약. 돌아오는 구간에 5월 17일 DFW→EWR(`HAT142`)가 존재 | 유지. 기존 도착편을 없는 것으로 판단하지 않음 |
| `PUNERT` | 5월 22일 BOS 출발 | 유지 |
| `HTR26G`, `MFRB94` | 각각 5월 16일 이동, 5월 27일 이후 일정 | 이번 정리 대상이라는 근거가 없어 유지 |

필요한 조회·대조: 사용자 예약 목록과 일곱 예약의 승객·개별 구간·날짜, 관련 항공편의 시각 및 취소 가능 조건. `get_reservation_details()` 반환에는 출도착 시각이 없으므로 구체적인 시간 충돌을 설명하려면 제공 도구의 항공편 검색 결과 등 시각 근거가 필요하다. Reference 목록에 시각 조회가 없다고 Agent가 시각을 이미 안다고 가정하지 않는다.

두 취소 대상은 business이며 아직 출발하지 않아 취소 정책에 부합한다. 취소 사유와 변경 내용을 확인하고 명시적 동의를 받아야 한다. 최종 목표 DB는 두 예약의 취소 상태·해당 환불 이력을 반영하고 나머지 DB를 유지한 상태다. 새 예약은 요구되지 않는다.

관찰 항목: 두 대상 식별, 타인 승객 예약 제외, 기존 왕복 구간 인식, 근거 없는 부재 단정·불필요한 신규 예약 제안, 사용자 확인, 두 취소 실행·결과, 다른 변경 여부. 계정 소유와 실제 승객을 혼동했는지 확인한다.

### airline `41`: 근거를 확인한 무변경

Amelia Davis(`amelia_davis_8890`)는 앞으로 탈 항공편 중 예약 승객이 한 명인 예약을 취소하려 한다. 환불을 못 받아도 취소하겠다는 의사가 있어도 정책의 취소 허용 조건은 달라지지 않는다.

| 예약 | 공식 DB에서 확인한 사실 | 필요한 판단 |
| --- | --- | --- |
| `UDMOP1` | 한 명, 미래 항공편, basic economy, 보험 없음, 예약 후 24시간 초과, 항공사 취소 아님 | 취소 허용 조건 불충족 |
| `4XGCCM` | 한 명이지만 5월 3~4일의 과거 일정이고 이미 착륙한 구간이 있음 | 미래 항공편 조건에서 제외 |
| `8C8K4E`, `XAZ3C0`, `LU15PA`, `MSJ4OA`, `I6M8JQ` | 승객 두 명 이상 | 한 명 조건에서 제외 |

필요한 조회·대조: 일곱 예약의 승객 수·일정과 해당 취소 정책. 필요한 상태를 도구로 확인하고, 현재 요청에서 취소 가능한 예약이 없다는 이유를 안내한다. 실제 과거 예약 취소를 추가 요청하는 경우에는 정책의 인계 규칙을 적용하되, 과거 예약 발견 자체를 인계 필수 조건으로 간주하지 않는다.

최종 목표 DB는 초기 DB 그대로다. 관찰 항목은 전체 예약 조사, 조건·정책에 따른 제외 설명, 무단 취소 제안·실행 여부다. 아무 조회나 설명 없이 DB만 유지한 실행을 충분한 수행으로 판정하지 않는다.

Task 설명의 API 제한 표현과 달리 실제 `cancel_reservation()`은 취소 자격을 검사하지 않고 상태·환불 이력을 변경한다. Policy도 조건 검증을 Agent 책임으로 명시한다. 도구 성공 응답은 정책 준수의 증거가 아니다.

### airline `22`: 세 변경을 빠짐없이 완료

Omar Rossi(`omar_rossi_1241`)는 New York→Chicago 예약의 승객을 본인으로 바꾸고 economy로 올린 뒤 위탁 수하물 세 개를 원한다. Gift card를 선호하고 프로필에 있는 생년월일을 다시 제공하고 싶어 하지 않는다. Agent가 변경 불가라고 말하면 대화를 종료할 수 있는 사용자 시나리오다.

대상 `FQ8APE`는 5월 25일 EWR→IAH→ORD(`HAT056`, `HAT138`)이며, 현재 basic economy·Ivan Garcia 한 명·수하물 0개다. 다른 예약 `UM3OG5`, `5RJ7UH`, `QKRY03`는 유지한다.

| 변경 | 필요한 결과·정책 근거 |
| --- | --- |
| 승객 | Omar Rossi, 프로필 생년월일 `1970-06-06`. 승객 수는 한 명 유지. 승객 정보 변경은 허용됨 |
| 좌석 등급 | 기존 항공편·날짜를 유지하고 두 구간 모두 economy. Basic economy의 항공편 변경 제한과 동일 항공편 좌석 등급 변경 허용을 구분 |
| 수하물 | `total_baggages=3`, `nonfree_baggages=0`. Gold 회원의 economy 무료 한도는 한 명당 세 개 |

필요한 조회·대조: 사용자 프로필의 예약·생년월일·회원 등급·결제수단, 대상 예약, 필요한 좌석·가격 정보. 현재 DB 기준 두 economy 구간 운임은 340달러, 기존 구간 운임은 131달러여서 차액은 209달러다. Reference 결제수단 `gift_card_8190333` 잔액 280달러로 지불 가능하다. Agent는 실제 조회와 사용자 확인을 근거로 처리해야 한다.

최종 목표 DB에는 세 변경과 좌석 등급 차액 결제·gift card 잔액이 반영돼야 한다. 유료 수하물 요금은 없다. Reference 순서 자체는 요구하지 않지만, 변경 후 등급의 무료 수하물 조건을 적용해야 한다. 일부 완료, 잘못된 불가 안내, 잘못된 청구, 불필요한 다른 예약 변경을 분리해 기록한다.

`42`의 타인 승객 제외를 모든 task의 금지 규칙으로 일반화하면 안 된다. 이 task에는 현재 다른 승객인 예약을 본인으로 변경하라는 명시적 요청이 있다.

### retail `0`: 조건에 맞는 두 품목 교환 요청 접수

Yusuf Rossi는 이메일을 기억하지 못하므로 이름과 우편번호 `19122`로 먼저 인증한다. 사용자 ID는 `yusuf_rossi_9620`, 주문 `#W2378156`은 본인의 배송 완료 주문이다. 주문과 두 상품의 변형·재고를 조회하고 결제수단과 교환할 전체 품목을 확인한다.

| 품목 | 요구·재고 | 필요한 교환 |
| --- | --- | --- |
| 키보드 | clicky·RGB·full size 우선. 해당 변형은 존재하지만 품절이며, 사용자가 허용한 대안은 백라이트 없음 | `1151293680` → `7706410293`(clicky·none·full size) |
| 온도조절기 | Apple HomeKit 대신 Google Home 호환 요구. 공식 데이터·reference는 Google Assistant 옵션에 대응 | `4983901480` → `7747408585`(Google Assistant·black) |

같은 상품의 재고 있는 변형으로만 교환한다. White 백라이트 등 다른 선택지를 임의로 확정하지 않는다. 주문의 나머지 세 품목(헤드폰·청소기·시계)은 유지한다.

변경 내용을 설명하고 전체 품목과 명시적 동의를 확인한 뒤 두 품목을 `exchange_delivered_order_items()` 한 호출에 포함한다. 첫 호출이 상태를 바꾸므로 품목별 두 번 호출은 실패한다. 이 제약은 정책과 도구 상태 전이에 따른 것이며 reference의 우연한 호출 순서가 아니다.

최종 목표는 `exchange requested` 상태, 두 기존·신규 item ID, `credit_card_9513926`, 차액 `-16.63`달러가 기록된 DB다. 실제 반품 배송·새 상품 배송·환불 완료가 아니라 교환 요청 접수 완료다. 조회·선택·확인·도구 결과·안내를 따로 관찰한다.

## 공식 채점과 별도 관찰의 경계

현재 프로젝트는 `run_domain()` → `run_tasks()`의 기본 `EvaluationType.ALL`을 사용한다. 읽기·쓰기 action checks는 기록하지만 네 task 모두 `ACTION`이 `reward_basis`에 없다.

| 대상 | reward_basis | 실제 점수 범위 |
| --- | --- | --- |
| airline `42`, `41`, `22` | `DB`, `COMMUNICATE` | `communicate_info=[]`이므로 해당 성분은 1. 자연어 assertion은 있으나 기본 경로에서 평가하지 않아 실질적으로 DB가 결정 |
| retail `0` | `DB`, `NL_ASSERTION` | assertion이 없어 LLM 판단 없이 해당 성분은 1. 실질적으로 DB가 결정 |

DB evaluator는 reference actions를 초기 환경에 적용한 DB와 실제 trajectory를 재생한 DB의 해시를 비교한다. 예약·주문뿐 아니라 결제 이력·잔액·교환 정보 등 DB의 부수 상태도 비교 대상이다. 동일한 최종 상태를 만드는 다른 유효한 절차도 통과할 수 있다. Reference actions는 필수 호출 순서가 아니다.

Action check는 기대 호출·인자의 존재 여부를 검사한다. 실행 결과의 성공이나 올바른 정책 적용을 증명하지 않으며, 동일 조회를 많이 하거나 호출 순서를 맞춘 것을 성공으로 보지 않는다. 실제 변경은 도구 반환·오류와 DB 검사를 함께 확인한다.

`41`의 reference는 조회뿐이므로 목표 DB가 초기 DB와 같다. 정상 종료 조건에서 아무것도 하지 않아도 DB를 통과할 수 있다. `user_stop`도 업무 완료를 보장하지 않는다. 공식 evaluator는 `agent_stop`·`user_stop` 외 종료를 reward 0으로 처리하며, 이때 DB 등의 세부 검사가 없으면 실패로 채워 넣지 않는다.

### 확인했으나 도입하지 않은 공식 추가 기능

- `ALL_WITH_NL_ASSERTIONS`: 기존 자연어 조건을 추가 LLM으로 검사할 수 있으나, basis에 없는 성분은 최종 reward에 반영하지 않는다. `42`의 assertion은 두 취소 완료만 요구하므로 잘못된 제안·조기 종료 구분을 전부 대체하지 못한다. Retail `0`에는 검사 문장이 없다.
- `tau2 review`·`--auto-review`: Agent·User Simulator의 대화를 추가 LLM으로 검토하며 공식 reward와 별도 결과다. 기존 trajectory에 적용할 수 있지만 이번 비교에 도입하기로 확정한 것은 아니다.
- `ALL_IGNORE_BASIS` 계열: basis 밖의 검사까지 reward에 곱하여 원래 채점 정의를 바꾼다. 이번 비교에는 제안하지 않는다.
- 공식 `docs/evaluation.md`는 CLI 기본값을 `ALL_WITH_NL_ASSERTIONS`로 설명하지만 현재 코드 경로는 `ALL`이다. 저장된 airline 결과의 `nl_assertions=null`도 이 경로와 부합한다. 문서의 설명만으로 추가 검사가 수행됐다고 간주하지 않는다.

확정한 판정 방식은 공식 reward와 기존 검사 결과를 보존하고, 아래 행동 관찰을 별도로 수행하는 것이다. 추가 평가 모델·호출·옵션을 자동으로 도입하지 않는다.

## 기존 결과와 비교 가능성 조사

### 원본과 확인한 행동

| 기호 | 원본 디렉터리 | 용도 |
| --- | --- | --- |
| A42 | `artifacts/evaluations/2026-09-11_14-51-32_KST_02d035bd/` | airline `42`의 기존 3회 결과 |
| R0 | `artifacts/evaluations/2026-09-11_11-41-16_KST_577e4916/` | retail `0`의 최종 3회 결과 |
| RP | `artifacts/evaluations/2026-09-11_11-30-03_KST_6f003c56/` | 별도 retail partial 실행. 최종 3회에 혼합하지 않음 |

각 디렉터리의 `results.json`, `metadata.toml`을 근거로 사용한다. 3단계에서 위치를 확인한 증거 참조는 `simulations`의 **simulation ID**와 **0부터 시작하는 `messages[index]`**다. 자연어 메시지에 고유 ID가 없으므로 ID를 만들지 않는다. 아래의 `turn_idx`는 해당 message index와 일치하지만 일반적으로 항상 같다고 가정하지 않는다.

| 원본·trial | Simulation ID | Reward·조회/변경 action match | 주요 근거 |
| --- | --- | --- | --- |
| A42·0 | `a8d24291-72b9-4a34-af15-300bd6387f3f` | 1; 7/8, 2/2 | `messages[22]` 두 취소·타인 제외 제안, `[24]`·`[26]` 취소 호출, `[25]`·`[27]` 결과. `5BGGWZ` 조회 누락으로 DB 성공을 완전한 조사 성공으로 보지 않음 |
| A42·1 | `5633c82f-9d15-4bbd-b0bd-ca7d9ef5e780` | 0; 8/8, 0/2 | `[16]`·`[18]`에 `SE9KEL`까지 취소 제안. `[19]` 사용자 확인과 STOP. 실제 쓰기 없음 |
| A42·2 | `ebe04350-a179-46b1-b5a6-a6e6519bb4d1` | 0; 6/8, 0/2 | `[18]` 기존 항공편을 찾지 못했다는 안내, `[24]` 신규 예약 제안, `[28]` 신규 예약 포함 확인 요청, `[29]` 확인과 STOP. `HTR26G`·`5BGGWZ` 조회 누락, 실제 쓰기 없음 |
| R0·0 | `d98c0458-3cb9-41f6-aed1-e5bcf1213742` | 1; 4/4, 1/1 | `[22]` 확인 요청, `[24]` 두 품목 교환 호출, `[25]` 결과 |
| R0·1 | `6e8d6614-66ca-4d36-b156-1b0fd40cc5d8` | 1; 4/4, 1/1 | `[16]` 확인 요청, `[18]` 두 품목 교환 호출, `[19]` 결과 |
| R0·2 | `5e10ece0-ba78-447e-b13e-febbe33d124f` | 1; 4/4, 1/1 | `[15]` 확인 요청, `[17]` 두 품목 교환 호출, `[18]` 결과 |

여섯 최종 trial은 모두 `user_stop`이며 저장된 도구 오류 표시는 없다. 이는 중단 과정까지 오류가 없었다는 뜻이 아니다. 위 표는 기존 사실의 색인이며, 확정한 행동 기준을 모든 항목에 적용한 전체 채점표는 아직 작성하지 않았다. Retail의 공식 성공도 모든 설명·제안이 정확했다는 뜻으로 사용하지 않는다.

위 성공 실행의 쓰기 호출 ID는 A42·0 `HSR97W` 취소 `0jxY8dGGGqXA8n0P9W0GFEJc8iqtpRvm`, `FDZ0T5` 취소 `w9dlvjnDHXcph8nJZeAP9r2Uy7SaUCvZ`; R0·0 교환 `bDGzVkMOrGqIMXW94O1BhOe2ZozlAyvj`, R0·1 교환 `F206NfJuKa3qAcbBMifnlAbpsdnPthTi`, R0·2 교환 `ElG9qgJhJSnwLpRbZvnbEr0X0HkrfKXp`다. 각 대응 tool result의 `id`와 일치한다.

원본 식별용 SHA-256(`results.json`): A42 `d88c841e401bc9432425c8e0ec7ce253a68d59355aa0caf2b2b24ab1149da7bc`, R0 `fbc7fd2424420e26deaf9cdaa3bba86db499772a20daeb182416f0f8eb2a85b1`, RP `ffc6471a3c9f234ebec46e8e957fca2b7b28eec976f12153bafb8b591cef66e5`.

### 일치·차이·확인 불가

| 조건 | 확인 결과와 한계 |
| --- | --- |
| 프롬프트·역할 옵션 | 두 metadata의 Agent 문구·역할별 모델·주소·빈 generation이 현재 설정과 일치 |
| 평가 조건 | task별 3회·seed 42·동시 실행 1·max_steps 200·max_errors 10 일치. 실제 trial seed는 순서대로 `670487`, `116739`, `26225` |
| Task·정책·시뮬레이터 지침 | 저장된 시나리오·평가 기준, 환경·trial별 정책, 공통 사용자 지침이 현재 관련 내용과 일치. Task 직렬화의 추가 기본 필드·null annotation 생략은 별도 구분 |
| 조회 DB | A42 쓰기 전 조회 응답 21건, R0 10건의 현재 DB 필드가 일치. 전체 DB와 당시 조회되지 않은 레코드의 동일성은 확인 불가 |
| 모델 응답 | 두 실행의 Agent·User raw response 모델명과 `system_fingerprint=b10883-91f6a6cf3` 일치. 모델 파일·샘플링·서버 시작 옵션 전체를 식별한다는 증거는 아님 |
| A42 프로젝트 코드 | metadata 커밋 `19702fc32bf08676d37cc0c3f4abd69b3f6e7587`. 조사 시 HEAD `141706e`와 Agent·평가 코드·프로젝트 lockfile가 같으며 차이는 `42` 설정 추가. 당시 미커밋 변경 전체는 저장되지 않음 |
| R0 프로젝트 코드 | metadata 커밋 `815f0d825d2b394745193f95eaee3f4f3c5af156`에는 domain 지원이 없어 그 커밋만으로 retail 실행 재현 불가. 미커밋 코드 사용 가능성이 높지만 정확한 당시 소스는 확인 불가. 커밋된 Agent·metadata 코드·프로젝트 lockfile는 현재와 일치 |
| 공식 코드 | 현재 tau2 HEAD `fc0055dc4e0a316c3f83133267fbd6faaa770992`, 설치본 1.0.1. 설치된 233개 추적 Python 파일이 현재 형제 저장소와 일치. 과거 소스 해시는 없음. `results.info.git_commit`은 실행 디렉터리의 프로젝트 커밋이며 tau2 커밋이 아님 |
| 의존성과 데이터 경로 | 현재 Python 3.12.10, LiteLLM 1.82.6, Pydantic 2.13.5, httpx 0.28.1, OpenAI SDK 3.8.0. `.env`의 `TAU2_DATA_DIR=../tau2-bench/data`. 당시 실제 설치 패키지·전체 데이터 경로/해시는 저장되지 않음 |
| 서버 조건 | 당시 모델 파일 해시, 서버 실행 명령·설정, 컨텍스트·샘플러 기본값 등을 확인할 기록 없음. 같은 모델명·주소·fingerprint만으로 동일성 확정 불가 |

조사 전부터 형제 저장소의 `uv.lock`에는 tau2 버전 표기 `1.0.0`→`1.0.1` 변경이 있었다. 공식 코드·데이터·정책·evaluator의 현재 추적 변경은 없었다. 이 문서 작성으로 공식 저장소를 수정하지 않았다. 현재 상태 확인은 과거 상태의 증명이 아니다.

### Retail 재개·partial 기록

R0 trial 0은 11:41:16~11:47:27, trial 1은 11:47:27~11:51:17, trial 2는 12:22:12~12:26:43(KST)에 실행됐다. 약 31분 공백은 #13의 서버 재시작 후 공식 `auto_resume`으로 남은 한 건을 완료했다는 기록과 부합한다. 중단된 시도의 상세 trajectory·서버 시작 명령은 현재 원본 디렉터리에 없다.

공식 재개는 `(trial, task_id, seed)`로 완료 실행을 건너뛰지만, `auto_resume`은 실행 정보 차이가 있어도 경고 후 계속할 수 있다. 정책은 실행 정보 비교에서 제외된다. Infrastructure error 실행은 재시도를 위해 결과에서 제거될 수 있다. 따라서 재개 성공 또는 최종 오류 0을 환경 동일성·과거 무오류의 증거로 사용하지 않는다. 실제로 오류가 제거됐다고 추정하지도 않는다.

RP는 #13에서 `.env` 없이 시작한 별도 partial로 분류했다. 저장된 trial 0 한 건은 reward 1이고 seed 670487이다. R0 trial 0과 대화 내용·도구 인자는 같지만 ID·시간이 다르다. 성공했기 때문에 추가하거나 실패했기 때문에 제외하는 식으로 선택하지 않고 별도 실행으로 보존한다.

### 확정한 재사용 방침과 실행 규모

사용자는 A42·R0를 문제 분석 자료로 보존하고 정량 비교의 기준으로 재사용하지 않으며, **네 task의 변경 전 기준 평가를 모두 새로 12회 확보**하는 방침에 동의했다. 과거 서버 조건과 R0 실제 코드의 확인 공백을 줄이려는 결정이며 기존 결과가 틀렸다는 판정이 아니다. 새 기준 평가도 실행 조건을 기록·유지해야 비교 가능성이 개선된다.

| 확정 대상 | 신규 기준 실행 수 | 변경 후 실행 수 |
| --- | --- | --- |
| airline `42` | 3회 | 3회 |
| airline `41` | 3회 | 3회 |
| airline `22` | 3회 | 3회 |
| retail `0` | 3회 | 3회 |
| 합계 | 12회 | 12회 |

검토했던 신규 기준 6회·9회 안은 선택하지 않았다. Task별 기준 결과는 새로 확보하는 하나의 사전 지정 3회 묶음으로 고정하고, 기존 유리한 trial을 새 묶음과 혼합하지 않는다. RP도 별도 partial 분석 자료로 보존한다.

확인하지 못한 과거 조건은 '확인 불가'로 남기며 동일하다고 추정하지 않는다. 새 기준 실행 전 현재 코드·데이터·모델·서버 조건을 기록하고 변경 후까지 유지한다. 새 실행에서도 비교에 영향을 주는 조건 차이 또는 미확인 조건이 발견되면 실행 전에 사용자와 처리 방침을 결정한다. 이번 확정은 평가 계획에 대한 것이며 이슈 #15에서 실제 평가를 시작하지 않는다.

## 유지할 비교 조건

| 항목 | 유지할 값 또는 원칙 |
| --- | --- |
| Task | airline `42`, `41`, `22`, retail `0` |
| 반복·seed | task별 변경 전후 각 3회, 설정 seed `42`. 실제 파생 seed도 기록 |
| 실행 제한 | `max_concurrency=1`, `max_steps=200`, `max_errors=10`. 별도 프로세스로 여러 평가를 동시에 시작하지 않음 |
| Agent / User | `task_agent` / 공식 `user_simulator`, half-duplex |
| 역할별 모델 | 모두 `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`, 현재 설정 주소 `http://100.80.184.89:8080/v1` |
| 생성 옵션 | 역할별 temperature·top_p·max_tokens 생략 유지. 생략을 0이나 임의의 기본값으로 바꾸지 않음 |
| Task 로드·평가 | 공식 전체 domain에서 지정 ID 사용, `task_set_name=None`, `task_split_name=None`; 기존 기본 `ALL` 경로와 task의 reward_basis 유지 |
| 실험 변경 | 확정한 Agent 추가 문구 하나. 사용자 모델·프롬프트, 정책·DB·도구·evaluator·실행 제한은 유지 |
| 설정 파일 | 기존 `configs/airline_task_42.toml`, `configs/retail.toml` 재사용. `configs/airline_task_41.toml`, `configs/airline_task_22.toml` 추가·검증 완료 |

프로젝트·공식 benchmark 커밋과 미커밋 diff, 실제 설치본, 데이터·프롬프트 식별값, 역할별 요청 옵션, 확인 가능한 모델 파일·서버 시작 설정을 후속 실행 전에 기록한다. 비밀 키는 저장하지 않는다. 비교에 영향을 주는 차이가 발견되면 실행 전에 근거·처리 방침을 사용자와 결정한다. 같은 seed는 같은 응답을 보장하지 않는다.

## 설정 검증 결과

2026-09-11, 승인받은 5단계에서 기존 airline `42` 형식으로 `41`·`22` 설정을 추가했다. 기존 `42`·retail 설정은 수정하지 않았다.

| 설정 | Domain / task | 설정 로드 | 공식 ID 검증 | 고정 조건·역할 옵션 |
| --- | --- | --- | --- | --- |
| `configs/airline_task_42.toml` | airline / `42` | 통과 | 통과 | 일치 |
| `configs/airline_task_41.toml` | airline / `41` | 통과 | 통과 | 일치 |
| `configs/airline_task_22.toml` | airline / `22` | 통과 | 통과 | 일치 |
| `configs/retail.toml` | retail / `0` | 통과 | 통과 | 일치 |

프로젝트의 기존 `.venv/Scripts/python.exe -B -`로 일회성 검증 코드를 실행했다. `load_config()`로 네 TOML을 읽고 domain·task ID·seed 42·3 trials·동시 실행 1·max_steps 200·max_errors 10을 확인했다. 역할별 모델·주소·출력 설정을 기존 `42`와 비교했고, 양쪽 `generation={}`가 유지됨을 확인했다. 공식 registry의 domain 등록과 `validate_task_ids()`의 전체 task 집합 검증을 통과했다.

실제로 로드된 데이터 경로는 `C:/Users/chahoseong/projects/tau2-bench/data`다. 네 task × 3회이므로 변경 전과 후 각각 12회라는 설정상 규모도 확인했다. 이 검증은 설정과 ID의 유효성에 대한 것이며 모델의 성공 여부나 현재 서버 준비 상태를 검증한 것은 아니다.

공식 import 과정에서 LiteLLM의 원격 모델 가격표 조회가 네트워크 제한으로 실패하여 로컬 가격표로 대체됐다는 경고가 있었다. 검증 프로세스는 exit code 0으로 완료됐고, `run_evaluation()`·`run_domain()`·모델 추론을 호출하지 않았다. 의존성·서버 설정을 변경하거나 가격표 조회를 재시도하지 않았다. 별도 평가 결과 디렉터리는 생성하지 않았다.

## 확정한 Trial별 기록 형식과 판정 원칙

| 구분 | 기록할 항목 |
| --- | --- |
| 식별·원본 | 변경 전/후, domain, task ID, trial, 설정 seed, 실제 seed, simulation ID, 원본 디렉터리·파일 및 해시 |
| 공식 결과 | reward, reward_basis·breakdown, DB check, read/write action checks, communicate/NL 검사의 실제 실행 여부, 종료 사유 |
| 조회 근거 | 판단에 필요한 레코드·필드와 실제 조회 여부, 조회 도구 호출 ID·반환 message index. 데이터에 사실이 존재하는 것과 Agent가 관찰한 것을 구분 |
| 제안·대상 | 모든 구체적 변경 제안 시점의 대상·제외 대상·근거, 잘못된 제안, 정정 시점, 최종 제안. 판단에 필요한 사용자 조건이 언제 주어졌는지도 기록 |
| 사용자 확인 | 어떤 변경 내용에 대한 동의인지, 확인 메시지 위치, 동의와 STOP의 동시 발생 여부 |
| 실제 실행 | 도구 이름·인자·호출 ID·결과 ID, 반환 오류, 관찰 가능한 상태 변화, 필요한 변경별 완료·미완료 |
| 오류·종료 영향 | 모델/도구 오류, infrastructure error, 제한 도달, 사용자 조기 종료, 실행 기회 유무, 관찰 불가능한 항목과 이유 |
| 부작용·안내 | 잘못되거나 불필요한 변경·청구, 정책 위반, 누락된 요구, 도구 결과를 넘어선 완료 안내 |

표기는 `충족`, `미충족`, `관찰 불가`, `해당 없음`으로 확정했다. 빈 검사와 관찰 불가는 성공으로 채우지 않으며, 미실행 검사를 실패로 채우지도 않는다. 관찰 불가에는 반드시 이유를 적는다.

판정 단위는 다음처럼 분리한다.

1. **구체적 제안:** 특정 대상을 변경하겠다는 권고·확인 요청·실행 계획을 관찰한다. 단순 목록 소개나 정보 확인 질문을 바로 잘못된 변경 제안으로 간주하지 않는다. 모호하면 원문을 남기고 판정을 보류한다. 잘못된 제안을 나중에 정정해도 발생 사실은 유지하고 최종 판단은 별도 기록한다.
2. **대상 판단:** 각 필요한 대상의 식별과 제외 조건 대조를 따로 확인한다. 최종 처리 목록을 제시했는데 필요한 항목을 빠뜨렸다면 관찰된 누락이다. 판단 전에 종료됐다면 추정하지 않는다. 조회 없이 맞힌 경우 대상 결과와 근거 부족을 분리한다.
3. **확인과 실행:** 사용자 동의는 Agent 판단의 정당성이나 실행 완료를 증명하지 않는다. 도구 호출만으로 완료를 선언하지 않고 반환·오류·DB 결과를 함께 확인한다. DB check가 없을 때에는 관찰된 개별 결과 이상으로 전체 DB 보존을 주장하지 않는다.
4. **조기 종료:** 확인과 STOP이 함께 나오면 확인은 관찰됐지만 그 뒤 실행 기회는 없었던 것으로 기록한다. 잘못된 제안은 오류로 남기되, 실행하지 않은 잘못된 변경을 가정하지 않는다. 필요한 변경이 실제 완료되지 않았다는 결과는 공식 점수와 함께 그대로 남긴다.
5. **Task별 충족:** `42`의 두 취소·타인 제외·신규 예약 여부, `41`의 조사·판단·설명과 무변경, `22`의 세 변경, retail의 두 품목 교환 접수를 각각 기록한다. 하나의 총점으로 합쳐 원인을 숨기지 않는다.

## 확정한 변경 전후 판정 기준

분석은 선택한 기준 묶음과 변경 후 묶음 전체를 사용한다. Task별 3회 분모를 유지해 `충족/미충족/관찰 불가` 수를 함께 제시한다. 관찰 가능한 실행만의 수치를 덧붙일 때에는 분모를 명시하며 전체 공식 결과를 대체하지 않는다. 각 seed에 대응하는 전후 trial 표도 제공하되, 동일 seed를 동일 대화가 보장된 통제 실험으로 해석하지 않는다.

주 관찰 오류는 아래 표의 세 유형 중 하나 이상이 발생한 trial을 한 건으로 센다. 같은 trial에서 여러 유형이나 같은 제안이 반복돼도 총 발생 trial 수를 중복 집계하지 않고, 유형별 표에는 각각 남긴다. 오류를 아직 제안하지 않은 채 판단 전에 끝났다면 오류 없음으로 세지 않는다. 개별 충족 항목의 개선은 충족 trial 수 증가, 악화는 감소로 비교하며 오류 항목은 반대로 비교한다. `22` 등은 개별 변경 완료 수와 모든 요구를 완료한 trial 수를 모두 기록한다.

### 비교할 축

| 축 | 비교할 내용 |
| --- | --- |
| 주 관찰: `42` 판단 오류 | 타인 예약·기타 제외 대상의 잘못된 변경 제안, 조회하지 않은 기록의 부재 단정, 그에 따른 불필요한 신규 예약 제안. 유형별 발생 trial 수와 발생 근거 |
| `42` 올바른 식별·완료 | 두 취소 대상의 식별과 타인 제외, 조회 근거의 충족, 각 취소 완료와 전체 DB 검사. 판단 개선과 완료 개선을 구분 |
| `41` 과잉 변경 방지 | 일곱 예약의 조사·조건 판단·안내, 부당한 취소 제안·실행, DB 유지. 단순 무행동 통과를 수행 성공으로 세지 않음 |
| `22` 완료 능력 | 승객·등급·수하물 각 변경과 세 변경 전체 완료, 잘못된 불가 안내·청구·다른 예약 변경 |
| Retail 회귀 | 두 품목의 요구 조건·재고·결제 확인과 한 번의 교환 접수, 요청 외 변경 여부. 공식 성공을 무오류 대화로 간주하지 않음 |
| 전체 부작용·종료 | 잘못된 DB 변경, 정책 위반, 모델/환경 오류와 조기 종료, 관찰 기회의 차이 |

### 확정한 결론 분류

이 분류는 세 번의 관찰에 대한 제한적 판단이며 통계적 유의성이나 다른 task로의 일반화를 주장하지 않는다. 기준을 확정한 뒤 결과에 맞춰 변경하지 않는다.

- **효과 있음(이번 비교에서 지지):** 비교 가능한 관찰에서 `42`의 주 관찰 오류 발생 trial 수가 감소하고, 개별 오류 유형의 증가나 필요한 대상 식별의 악화가 없으며, 조회·대조 근거의 개선이 확인된다. 필요한 완료 능력과 `41`·`22`·retail의 관찰 결과가 악화되지 않고 변경 후 잘못되거나 불필요한 DB 변경이 발생하지 않아야 한다. 완료 증가 여부는 별도로 결론 낸다. 오류 감소가 단지 제안 전에 종료된 trial 증가 때문이라면 이 분류를 사용하지 않는다.
- **효과 없음(이번 비교에서 개선 근거 없음):** 충분히 관찰 가능한 비교에서 대상 판단 오류 감소가 확인되지 않거나, 필요한 완료·제외 대상 유지에 명확한 악화가 관찰된다. 일부 개선과 부작용이 공존하면 각각 명시하고 전체 개선으로 채택하지 않는다. 이는 프롬프트가 언제나 무효라는 뜻이 아니다.
- **판단 유보:** 비교 조건 차이, 환경 오류, 조기 종료 또는 근거 부족 때문에 개선·악화의 관계를 구분할 수 없다. 일부 항목은 확인됐으면 그 항목의 결론은 남기고 나머지만 유보한다. 잘못된 제안·변경이 이미 관찰됐다면 불확실성을 이유로 그 사실을 지우지 않는다.

관찰 불가가 있는 경우 해당 이진 항목의 발생 가능한 trial 수를 `확인된 발생 수`부터 `확인된 발생 수 + 관찰 불가 수`까지로 표시한다. 오류 감소를 확정하려면 변경 후 상한이 변경 전 하한보다 작아야 하고, 비악화를 확정하려면 변경 후 오류 상한이 변경 전 오류 하한보다 크지 않아야 한다. 충족 수는 반대 방향으로 비교한다. 이는 미확인 행동을 성공·실패로 채우는 규칙이 아니라 결론이 불확실성에 따라 바뀌는지 확인하는 보수적 범위다.

효과 있음의 필수 항목에 이 비교를 적용할 수 없거나 조건이 불분명하면 전체 결론을 유보한다. 예를 들어 잘못된 제안 2회가 변경 후 0회가 되어도 세 trial 모두 판단 전에 종료됐다면 변경 후 오류 가능 범위는 0~3회이므로 개선 근거가 아니다. 충분히 관찰된 명확한 악화는 부작용으로 남기며, 나머지 항목의 유보가 그 사실을 지우지 않는다. 점수 변화나 위 분류만으로 원인 가설이 입증됐다고 주장하지 않는다.

## 후속 실행 절차 — 이슈 #15에서 실행하지 않음

### 실행 전 기록과 순서

다음 명령은 **후속 평가 실행이 승인된 뒤** 프로젝트 루트에서 사용한다. 이슈 #15에서는 명령 작성·정적 검토만 수행한다. 기존 설치 환경을 유지하기 위해 `.venv/Scripts/python.exe`로 기존 `scripts/evaluate.py` 진입점을 실행한다. 평가 도중 의존성을 동기화하거나 설치하지 않는다. 기존 모델·서버·생성 옵션·공식 평가 방식은 앞 절의 확정 조건을 유지한다.

순서는 변경 전 `42` → `41` → `22` → retail `0`, 확정 문구 적용 후에도 같은 순서다. 각 명령이 해당 task 3회를 순차 실행한다. Task마다 끝난 결과를 확인한 뒤 다음 명령을 실행한다. 여러 터미널·백그라운드 프로세스에서 동시에 실행하지 않는다.

변경 전 네 task의 기준 12회를 확보하고 원본·관찰 기록을 정리하기 전에는 P1을 적용하지 않는다. 환경 오류나 중단 때문에 기준 묶음이 미완성이면 아래 절차로 처리한다. Reward 0이나 User Simulator의 조기 종료는 결과로 보존하고 높은 점수를 얻기 위해 다시 실행하지 않는다. 비교를 마친 뒤 성능이 낮다는 이유로 추가 튜닝·평가를 반복하지 않는다.

실행 담당자는 아래 정보를 각 task 시작 전 `실행 매핑`과 실제 run 디렉터리의 `inputs/`에 기록한다. 서버 설정에 인증 정보가 있다면 키 값은 제외한다. 최초 시작 직후 중단되더라도 당시 조건을 복원할 수 있도록 시작 전 기록도 보존한다.

| 보존 항목 | 기록 방법·내용 |
| --- | --- |
| 코드 | 프로젝트·tau2 HEAD, `git status --short`와 관련 diff, 실제 사용한 Agent·평가 코드 사본/해시. HEAD만 기록하고 미커밋 코드를 생략하지 않음 |
| 프롬프트·설정 | 적용 전/후 구분, 정확한 `AGENT_PROMPT`, 사용한 TOML 사본·해시, 해석된 역할별 옵션과 생략 여부 |
| 공식 입력 | 실제 `TAU2_DATA_DIR` 절대 경로, airline·retail tasks/policy/DB와 User Simulator 지침의 파일 해시. 원본 파일은 변경하지 않음 |
| 런타임 | Python·설치된 tau2·LiteLLM·OpenAI SDK·Pydantic 등의 실제 버전, 프로젝트 lockfile 해시, 실제 설치본과 공식 소스의 대응 |
| 모델·서버 | 역할별 모델 ID·주소, 확인 가능한 모델 파일 해시·서버 버전·시작 옵션·샘플러 기본값·컨텍스트 설정. 수집 불가 항목은 명시하고 비교상 영향은 실행 전에 결정 |
| 실행·재개 | 시작/종료 시각(KST), 정확한 명령·작업 디렉터리, 종료 코드, 콘솔 로그, 중단·서버 재시작 시점과 전후 설정 비교 |
| 결과 | `results.json`, `metadata.toml` 원본 및 해시, task/trial/seed/simulation ID 매핑, 중간 결과 사본과 각 시도의 관계 |

서버의 현재 모델 목록이나 응답 fingerprint만으로 전체 조건 동일성을 대체하지 않는다. 프로젝트 문서·실험 상태 기록이 추가되는 것은 구분하되, Agent·공식 환경·모델 옵션 등 비교에 영향을 주는 변경이나 미확인 조건은 실행 전에 사용자와 처리 방침을 결정한다. P1 적용은 후속 작업에서 수행하고 문서의 정확한 세 문장 추가 외 동작 변경이 없는지 확인한다.

### 신규 실행 명령

먼저 데이터 경로를 명시한다. 현재 설정에는 인증 키 환경변수 참조가 없으며, 역할별 generation은 생략된 상태다. 아래 명령은 `.env`의 다른 값을 출력하지 않는다.

```powershell
$env:TAU2_DATA_DIR = (Resolve-Path -LiteralPath "../tau2-bench/data").Path
```

아래 네 명령을 순서대로 사용한다. **변경 전 1회씩 실행하면 기준 12회**, 기준 확보 후 P1을 적용하고 **같은 네 명령을 다시 1회씩 실행하면 변경 후 12회**다. 같은 명령이므로 각 원본 경로를 반드시 전/후에 대응시킨다. 명령 실패 시 다음 task로 자동 진행하지 않는다.

```powershell
& ".venv/Scripts/python.exe" -B scripts/evaluate.py run configs/airline_task_42.toml
if ($LASTEXITCODE -ne 0) { throw "airline 42 stopped; preserve and inspect results." }

& ".venv/Scripts/python.exe" -B scripts/evaluate.py run configs/airline_task_41.toml
if ($LASTEXITCODE -ne 0) { throw "airline 41 stopped; preserve and inspect results." }

& ".venv/Scripts/python.exe" -B scripts/evaluate.py run configs/airline_task_22.toml
if ($LASTEXITCODE -ne 0) { throw "airline 22 stopped; preserve and inspect results." }

& ".venv/Scripts/python.exe" -B scripts/evaluate.py run configs/retail.toml
if ($LASTEXITCODE -ne 0) { throw "retail 0 stopped; preserve and inspect results." }
```

콘솔 로그를 남길 때에는 각 task 직전에 고유한 로그 경로로 `Start-Transcript`를 시작하고 해당 task 종료·중단 후 `Stop-Transcript`로 닫는다. 기존 로그를 덮어쓰지 않는다. 명령의 종료 코드 0은 높은 reward를 뜻하지 않는다. 완료된 결과에서 task별 trial 0·1·2, 실제 seed `670487`·`116739`·`26225`, simulation ID의 중복·누락을 확인하고 공식 점수·오류·종료 이유를 별도 기록한다.

### 실행 매핑 — 후속 실행 시 채움

아래 칸은 아직 실행하지 않아 비어 있다. 경로를 기존 A42·R0로 채우지 않는다. Task별 최초 시작 시 식별 정보를 기록하고 종료·중단 때 상태를 갱신한다.

| 순서 | 구분 | Domain / task | 예정 trial | 실제 run 경로·입력 기록·로그 | 상태 |
| --- | --- | --- | --- | --- | --- |
| 1 | 변경 전 | airline / `42` | 0, 1, 2 | 미생성 | 미실행 |
| 2 | 변경 전 | airline / `41` | 0, 1, 2 | 미생성 | 미실행 |
| 3 | 변경 전 | airline / `22` | 0, 1, 2 | 미생성 | 미실행 |
| 4 | 변경 전 | retail / `0` | 0, 1, 2 | 미생성 | 미실행 |
| 5 | 변경 후 | airline / `42` | 0, 1, 2 | 미생성 | 미실행 |
| 6 | 변경 후 | airline / `41` | 0, 1, 2 | 미생성 | 미실행 |
| 7 | 변경 후 | airline / `22` | 0, 1, 2 | 미생성 | 미실행 |
| 8 | 변경 후 | retail / `0` | 0, 1, 2 | 미생성 | 미실행 |

### 중단과 원본 보존

| 상태 | 처리 원칙 |
| --- | --- |
| 준비 단계 실패, 결과 파일 없음 | 오류·시각·명령·입력 조건을 기록. 실행된 trial로 세거나 결과를 만들어 넣지 않음. 원인을 해결하고 같은 계획을 시작 |
| Reward 0, `user_stop`, `agent_stop`, step/error 제한 도달 | 해당 공식 결과를 그대로 유지. 실패나 조기 종료를 재시도 대상으로 바꾸지 않음 |
| 강제 중단·서버 정체로 일부 trial만 저장, 저장된 infrastructure error 없음 | 원본을 보존하고 이전 프로세스 종료·서버 조건 동일성을 확인. 아래의 제한된 재개로 미저장 trial만 이어갈 수 있음 |
| 저장된 `infrastructure_error` 있음 | 자동 재개하지 않음. 공식 재개가 오류를 제거·재실행할 수 있으므로 원본 보존 후 사용자와 처리 방침 결정. 재시도 결과로 원래 오류를 숨기거나 점수를 유리하게 대체하지 않음 |
| 코드·프롬프트·모델·정책·DB·옵션 차이 또는 동일성 미확인 | 같은 묶음으로 합치지 않고 중단. 근거·제안을 제시하고 실행 전에 처리 방침 결정 |
| 결과 손상·원본이나 조건 기록 부족 | 관찰 불가·자료 부족으로 기록하고 임의 복원·성공 추정·무조건 새 3회 실행을 하지 않음 |

중단 직후 기존 평가 프로세스가 더 이상 결과를 쓰지 않는지 먼저 확인한다. 실제 run 경로와 새 보존 폴더명을 지정하고 **아래는 해당 경로의 실제 파일이 있을 때만** 사용한다. `metadata.toml`을 다시 생성하거나 기존 `results.json`을 편집하지 않는다.

```powershell
$evaluationRun = (Resolve-Path -LiteralPath "artifacts/evaluations/REPLACE_WITH_ACTUAL_RUN").Path
$preservedRun = Join-Path $evaluationRun ("preserved/" + (Get-Date -Format "yyyyMMdd_HHmmss_fff"))
New-Item -ItemType Directory -Path $preservedRun -ErrorAction Stop | Out-Null
Copy-Item -LiteralPath (Join-Path $evaluationRun "results.json") -Destination $preservedRun -ErrorAction Stop
Copy-Item -LiteralPath (Join-Path $evaluationRun "metadata.toml") -Destination $preservedRun -ErrorAction Stop
Get-FileHash -LiteralPath (Join-Path $preservedRun "results.json"), (Join-Path $preservedRun "metadata.toml") -Algorithm SHA256
```

입력 기록·콘솔/서버 로그와 중단된 미저장 시도의 자료도 보존하고 이 사본 경로에 연결한다. 예정 24회는 논리적 trial 수다. 내부 자동 재시도나 중단 후 재실행으로 실제 시도 수가 늘었다면 시도 횟수·이유와 저장 여부를 별도 보고한다. Infrastructure error에 대한 예외 재실행을 나중에 승인받더라도 최초 오류와 후속 결과를 함께 제시하며, 관찰 불가를 성공으로 바꾸지 않는다.

### 제한된 재개 명령

현재 프로젝트 CLI에는 resume 플래그가 없다. `scripts/evaluate.py run ...`을 다시 실행하면 새 디렉터리가 생긴다. 아래는 **기존 등록·설정 변환 함수와 공식 `run_domain()`을 재사용하는 일회성 명령**이며 새 평가 기능이나 스크립트 파일을 추가하는 것이 아니다.

적용 전제: 이전 프로세스가 종료됐고, 원본 사본을 확보했으며, 입력 기록으로 당시 코드·공식 환경·서버 조건이 동일함을 확인했고, 저장된 infrastructure error가 없어야 한다. 아래 코드의 설정·프롬프트 검사는 추가 방어일 뿐 서버·전체 환경 대조를 대체하지 않는다. 변경 전 checkpoint를 P1 적용 후 재개하면 안 된다.

데이터 경로를 위와 같이 설정하고 아래 세 인자를 실제 **run 경로, 해당 TOML, 방금 보존한 사본 폴더**로 바꾼다. 명령은 모델 평가를 시작하므로 후속 실행 승인 범위에서만 사용한다.

```powershell
@'
import json
import sys
import tomllib
from pathlib import Path

from agents.task_agent import AGENT_PROMPT
from evals.config import load_config
from evals.runner import _build_run_config, _preflight_models, _register_task_agent
from tau2.runner import run_domain

run_dir = Path(sys.argv[1]).resolve(strict=True)
config = load_config(Path(sys.argv[2]))
backup_dir = Path(sys.argv[3]).resolve(strict=True)
if run_dir == backup_dir:
    raise SystemExit("Backup must be a separate directory.")
for name in ("results.json", "metadata.toml"):
    if (run_dir / name).read_bytes() != (backup_dir / name).read_bytes():
        raise SystemExit("Preserved original does not match; stop and inspect.")

metadata = tomllib.loads((run_dir / "metadata.toml").read_text(encoding="utf-8"))
current = config.model_dump(mode="json", exclude_none=True)
for section in ("evaluation", "agent", "user", "output"):
    if metadata[section] != current[section]:
        raise SystemExit(f"Configuration changed: {section}")
if metadata["prompts"]["agent"] != AGENT_PROMPT:
    raise SystemExit("Agent prompt changed; do not resume this checkpoint.")
saved = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
if any(s["termination_reason"] == "infrastructure_error" for s in saved["simulations"]):
    raise SystemExit("Infrastructure errors must be preserved; decide handling first.")

_register_task_agent()
_preflight_models(config)
run_config = _build_run_config(config, run_dir)
run_config.auto_resume = True
results = run_domain(run_config)
if any(s.termination_reason.value == "infrastructure_error" for s in results.simulations):
    raise SystemExit("New infrastructure error; preserve results before further action.")
print(run_dir / "results.json")
'@ | & ".venv/Scripts/python.exe" -B - "artifacts/evaluations/REPLACE_WITH_ACTUAL_RUN" "configs/airline_task_42.toml" "artifacts/evaluations/REPLACE_WITH_ACTUAL_RUN/preserved/REPLACE_WITH_BACKUP"
if ($LASTEXITCODE -ne 0) { throw "Resume stopped; preserve and inspect results." }
```

공식 `auto_resume`은 완료된 `(trial, task_id, seed)`를 건너뛴다. 재개 후 원래 simulation ID와 저장된 결과가 유지되고 누락된 trial만 추가됐는지 보존 사본과 비교한다. 재개 시각·명령·서버 확인 내용을 별도로 기록하고 최초 `metadata.toml`을 갱신하지 않는다. 이 명령으로 조건 차이나 손상된 결과를 자동 복구하지 않는다.

## 준비 완료 점검

6단계 검증: 문서의 네 신규 실행 명령을 기존 CLI parser에 인자로 전달해 구문과 설정 경로를 확인했다. PowerShell 코드 블록 네 개의 parser 검사와 재개 명령 안 Python 코드의 compile 검사를 통과했고, 참조하는 기존 runner 함수가 존재함을 확인했다. 이는 정적 검증이며 실제 서버 preflight·평가·checkpoint 재개는 실행하지 않았다. 설정의 실제 로드와 공식 ID 검증은 앞 절의 5단계 결과를 사용한다.

현재 환경에서 `uv` 실행 링크의 도움말 조회는 접근 거부로 실행되지 않아, 이미 정상 동작을 확인한 프로젝트 가상환경 Python을 후속 명령에 사용했다. 의존성 재설치나 권한 변경은 하지 않았다. 원래의 평가 진입점과 공식 runner를 그대로 사용한다.

| 단계 | 작업 | 현재 상태 |
| --- | --- | --- |
| 4 | 문구·기대 행동·판정 기준·재사용 방침 결정 | 완료. 기존 결과는 분석용 보존, 신규 기준 12회·변경 후 12회 확정 |
| 5 | `41`·`22` 설정 추가, 네 설정의 `load_config()` 및 공식 `validate_task_ids()` 검증 | 완료. 네 설정 통과, 모델 호출 없음 |
| 6 | 신규 기준 12회·변경 후 12회의 명령·순서·중단/재개·원본 보존 절차 작성·점검 | 완료. 실제 평가 미실행 |

후속 실행 순서는 문구 적용 전 기준 결과 확보 → 확정 문구 하나 적용 → 변경 후 12회 → 결과·결론 기록이다. 이 문서 작성이나 이슈 #15의 완료가 실제 평가 실행 허가는 아니다.

이슈 #15 완료 조건 대조:

- [x] 문제·가설·정확한 변경 문구·기대 행동·비교 조건·판정 기준과 후속 결과·결론 기록 위치를 작성했다.
- [x] 네 task의 사용자 목표·조회·변경·제외 대상·정책·실제 채점 범위를 확인했고 reference actions를 필수 순서로 해석하지 않는다.
- [x] `42`의 대상 판단, `41`의 근거 있는 무변경, `22`의 세 변경, retail의 두 품목 교환 접수를 관찰 항목으로 명시했다.
- [x] Trial별 원본·seed·공식 검사·종료·근거 참조와 제안·확인·실행·결과·관찰 불가 기록 방식을 정했다.
- [x] 과거 비교 조건과 확인 불가 항목을 기록하고 기존 결과 미재사용·신규 기준 12회·변경 후 12회를 사용자와 확정했다.
- [x] 네 설정의 고정 옵션·역할별 생략 옵션을 유지하고 설정 로드·공식 task ID 검증을 모델 호출 없이 완료했다.
- [x] 후속 실행 명령·입력 조건 기록·중단/재개·원본과 오류 보존 원칙을 작성했다.
- [x] Agent 문구를 실제 적용하거나 공식 benchmark를 수정하지 않았으며 실제 LLM 평가를 시작하지 않았다.

## 확정 기록

2026-09-11, 사용자가 P1 문구와 적용 위치를 그대로 확정했다. 위의 영어 세 문장을 기존 Agent 프롬프트 뒤, `## Domain Policy` 앞에 추가하는 것으로 정했다. 이 승인은 문구·위치의 확정이며 현재 Agent 적용이나 LLM 평가 실행 승인이 아니다.

2026-09-11, 사용자가 네 task의 기대 행동과 문서의 판정 기준을 그대로 확정했다. 공식 점수와 별도 행동 관찰, 제안·확인·실행·결과의 분리, 정정 전 오류의 보존, trial별 중복 집계 방지, 관찰 불가의 보수적 처리, 효과 있음·효과 없음·판단 유보 기준을 유지한다. 이후 결과에 맞춰 기준을 변경하지 않는다.

2026-09-11, 사용자가 A42·R0를 정량 기준으로 재사용하지 않고 분석 자료로 보존하며 신규 기준 12회·변경 후 12회로 준비하는 방침에 동의했다. 과거의 확인 불가능한 조건은 그대로 명시하고, 새 실행의 비교 조건을 기록·유지하며 차이가 있으면 실행 전에 처리 방침을 결정한다. 기존 trial은 새 기준 묶음에 혼합하지 않는다. 이 결정으로 4단계를 완료했으며 실제 평가 실행은 승인하지 않았다.

2026-09-11, 사용자가 5단계와 6단계 진행을 각각 승인했다. 두 설정 추가·네 설정 검증, 후속 명령·실행 매핑·조건 기록·중단/재개·원본 보존 절차 작성과 완료 조건 대조를 마쳤다. 문구·판정 기준·재사용 방침의 기존 확정 내용을 변경하지 않았다. 실제 Agent 적용·LLM 평가·재개는 수행하지 않았다.

## 변경 전 기준 결과

신규 12회로 확보하기로 확정했으며 아직 실행하지 않았다. 위 기존 결과 표와 이 절을 구분한다. 후속 작업에서 새 기준 원본 묶음과 trial별 관찰표를 기록한다.

## 변경 후 결과

아직 실행하지 않음. 후속 작업에서 원본 경로·metadata·trial별 관찰표를 기록한다.

## 결론

아직 판단하지 않음. 후속 작업에서 공식 점수, 판단·완료·부작용·종료 영향과 근거를 종합해 효과 있음·효과 없음·판단 유보를 기록한다. 결과가 불리하거나 유보여도 근거와 한계를 설명했다면 학습 목표를 달성할 수 있으며, 자동으로 추가 튜닝·평가를 반복하지 않는다.
