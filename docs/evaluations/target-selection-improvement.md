# 조회 근거에 기반한 변경 대상 판단 개선 실험

## 상태와 범위

- 관련 이슈: [#15](https://github.com/chahoseong/agent-tool-use/issues/15), 상위 에픽 [#14](https://github.com/chahoseong/agent-tool-use/issues/14), 선행 분석 [#13](https://github.com/chahoseong/agent-tool-use/issues/13), [#8](https://github.com/chahoseong/agent-tool-use/issues/8).
- 작성일: 2026-09-11, 최종 감사일: 2026-09-14. **이슈 #15 준비와 이슈 #16의 승인된 1–6단계 작업을 완료했다. 신규 변경 전 기준 4 task × 3 trial의 원본·분석을 확보하고 최종 대조했다. 사용자는 서버 context·슬롯 차이와 기록 한계를 명시한 현재 12개 결과를 비교 기준으로 수용하고 이슈 #16 마무리를 승인했다. 이 차이가 관찰된 오류를 일으켰다는 증거는 없으며 이를 이유로 추가 기준 평가를 요구하지 않는다. 이슈 #17에서 P1 적용과 코드 검증을 완료했다. 변경 후 평가·효과 판정은 아직 수행하지 않았다. 기준 결과는 이슈 #16 6단계 절, 현재 코드와 검증은 이슈 #17 적용 기록 절을 기준으로 한다.**
- 사용자는 전체 계획을 승인했고, 각 단계 시작 전 별도 승인과 완료 후 상세 설명을 요청했다. 1단계 task·채점 분석과 2단계 기존 결과 비교 조사를 마쳤으며, 승인받은 3단계에서 이 초안을 작성했다.
- 이슈 #15의 4단계에서 사용자가 P1의 정확한 문구·적용 위치, 기대 행동·판정 기준, 기존 두 결과를 정량 기준으로 재사용하지 않는 방침을 각각 확정했다. 신규 기준 12회·변경 후 12회로 준비한다. 5·6단계도 별도 승인 후 완료했다. 이슈 #16에서는 각 task의 실행 단계마다 별도 승인을 받는다.
- 승인받은 5단계에서 설정 추가·검증을 완료하고, 6단계에서 실행·중단·재개 및 원본 보존 절차를 작성·점검했다. 이슈 #15 완료 당시에는 Agent 프롬프트에 확정 문구를 적용하지 않았다.
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

## 가설과 확정한 변경 문구 — 이슈 #17에서 적용 완료

가설: 필요한 조회와 대조 기준을 명시하면 조회 누락·조건 오해로 발생하는 잘못된 변경 제안이 줄고, 필요한 변경을 정확히 완료하는 데 도움이 될 것이다.

변경 전 `AGENT_PROMPT`:

```text
You are a helpful customer service agent.

Follow the policy strictly. Use the provided tools to help the user.
```

사용자와 확정한 추가 문구 P1:

```text
Before proposing changes, use the available tools to retrieve the records needed to identify the correct targets. Check those records against the user's requirements, exclusions, and the policy. Do not conclude that a relevant record is absent, or expand the scope of work, based on information you have not checked.
```

문구의 의미는 변경 제안 전에 대상 식별에 필요한 기록을 조회하고, 사용자 요구·제외 조건·정책과 대조하며, 확인하지 않은 정보를 근거로 기록의 부재를 단정하거나 작업 범위를 넓히지 말라는 것이다. 특정 task·도메인·예약 ID나 정답 호출 순서는 포함하지 않는다.

적용 위치는 기존 두 문장 뒤, `## Domain Policy` 앞이다. 이슈 #17에서 기존 프롬프트에 빈 줄과 위 P1을 그대로 추가했다. 기존 policy 결합 방식은 유지했다. 아래 적용 기록에서 코드 식별 정보와 검증 결과를 확인할 수 있다.

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

경로를 기존 A42·R0로 채우지 않는다. Task별 최초 시작 시 식별 정보를 기록하고 종료·중단 때 상태를 갱신한다. 사용자의 준비 폴더 삭제 요청 이후 신규 실행 조건과 분석은 문서 및 실제 결과 디렉터리의 `analysis.md`에 기록한다. 앞의 사본 보존 표를 근거로 삭제한 준비 폴더나 중복 코드 사본을 재생성하지 않는다.

| 순서 | 구분 | Domain / task | 예정 trial | 실제 run 경로·입력 기록·로그 | 상태 |
| --- | --- | --- | --- | --- | --- |
| 1 | 변경 전 | airline / `42` | 0, 1, 2 | `artifacts/evaluations/2026-09-11_18-44-51_KST_07b17b0e/`, 동일 디렉터리 `analysis.md`; 로그 `artifacts/evaluations/airline42-baseline_20260911_184445_928.log`(Python 출력 미포함) | 3회 실행·분석 완료 |
| 2 | 변경 전 | airline / `41` | 0, 1, 2 | `artifacts/evaluations/2026-09-14_09-19-22_KST_6a9c3f3f/`, 같은 디렉터리 `analysis.md`; 로그 `artifacts/evaluations/airline41-fresh_20260914_091917_678.log` | 신규 3 trial·분석 완료, 두 차례 중단·재개 및 슬롯 차이 기록 |
| 3 | 변경 전 | airline / `22` | 0, 1, 2 | `artifacts/evaluations/2026-09-14_10-29-21_KST_7ea1bbde/`, 같은 디렉터리 `analysis.md`; 로그 `airline22-baseline_20260914_102915_617.log` | 신규 3 trial·분석 완료, 두 차례 중단·재개와 context 승인 기록 |
| 4 | 변경 전 | retail / `0` | 0, 1, 2 | `artifacts/evaluations/2026-09-14_11-34-46_KST_c0605556/`, 같은 디렉터리 `analysis.md`; 로그 `retail0-baseline_20260914_113441_461.log` | 신규3회·분석 완료, 실행 후 서버503 기록 |
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

신규 12회를 확보했다. 위 기존 결과 표의 과거 결과는 이번 정량 기준에 섞지 않는다. 아래 이슈 #16의 승인 대기·중단·미완료 및 P1 미적용 표현은 해당 시점의 이력이며, 현재 완료 상태와 선택된 원본은 6단계 최종 감사 절에 정리한다.

### 이슈 #16 2단계: airline `42` 신규 기준 실행

사용자가 서버 확인 불가 항목을 명시하는 실행 방침과 2단계를 승인했다. 기존 CLI로 `configs/airline_task_42.toml`의 3 trial을 실행한다. 분석은 `gpt-6-astra` / `high` 서브에이전트가 trial별로 수행하고 주 에이전트가 원본 대조·통합하며, 결과 디렉터리의 `analysis.md`에 작성한다. 공식 evaluator는 변경하지 않는다.

실행 직전 기존 프롬프트 일치와 Agent·User preflight 통과를 확인했다. 프로젝트 HEAD는 `80168d861bee680ec2d15620fc28fcbe78ce2241`, 공식 checkout은 `fc0055dc4e0a316c3f83133267fbd6faaa770992`이며 프로젝트의 미커밋 변경은 이 문서뿐이다. 서버 빌드 `b10883-91f6a6cf3`, 템플릿 SHA-256 `6a1015c47ccfcfa67c3b772385bccee357a4d37c3cda37bd202e9047f391ab82`, context 139776, 슬롯 4, temperature 1.0 / top_k 64 / top_p 약 0.95 / min_p 약 0.05 / max_tokens -1이 1단계 관찰과 일치했다. 실제 로드된 모델 파일 체크섬·전체 시작 옵션·다른 클라이언트 사용은 여전히 확인 불가다. 삭제한 준비 폴더는 재생성하지 않는다.

실행 결과: 2026-09-11 18:44:51–19:03:15 KST, 기존 CLI 신규 실행 1회로 3 trial 완료, 종료 코드 0. 주 에이전트의 중단·재개·재실행 0회. 세 trial 모두 `user_stop`, 공식 reward 0 / DB match false다. 실제 seed는 순서대로 670487·116739·26225이며 기존 결과를 혼합하지 않았다.

| Trial / simulation ID | 공식 read/write match | 관찰 요약 |
| --- | --- | --- |
| 0 / `dbb5637b-b5e8-4f4c-8a57-4a523167b400` | 8/8, 0/2 | 타인 SE9KEL 취소 제안 후 정정. 동의 후 재확인, 마지막 확인과 STOP. 실제 취소 없음 |
| 1 / `206d5785-e17d-45d8-b094-185056a7f9eb` | 8/8, 2/2 | 필요한 두 예약 외 MFRB94 취소. HTR26G도 처음 제안했으나 정책상 거절. 단일 도구 호출 정책 위반 |
| 2 / `26fe0f18-f706-43ce-af0b-424ccc842917` | 7/8, 2/2 | 5BGGWZ 미조회 상태에서 도착편 부재 안내. 필요한 두 예약 외 SE9KEL·MFRB94 취소. 사용자 시뮬레이터가 타인 제외 조건을 말하지 않고 추가 취소에 동의한 한계 |

주 관찰 오류는 3/3, 근거 없는 부재 단정은 1/3, 그에 따른 신규 예약 제안은 0/3, 필요한 두 취소 완료는 2/3, 추가 잘못된 실제 변경은 2/3이다. 두 취소 대상 식별과 정확히 두 개만 변경하는 능력을 구분한다. Trial 2를 명시적 제외 요청 무시·무동의 취소로 표현하지 않는다. 아직 전후 비교·프롬프트 효과 결론은 없다.

상세 근거·모델/추론 강도·원본 해시는 `artifacts/evaluations/2026-09-11_18-44-51_KST_07b17b0e/analysis.md`에 기록한다. PowerShell transcript는 시작·종료 정보만 남고 Python 출력은 누락되어 완전한 콘솔 로그가 아니다. 대화·도구 반환·공식 검사는 results.json에 보존됐으며 로그 보완을 위한 재평가는 하지 않는다. 실행 후 관찰 가능한 서버 조건은 실행 전과 같았다. 다음 task `41` 실행은 별도 승인 전까지 수행하지 않는다.

### 이슈 #16 1단계: 실행 환경 점검

사용자 요청에 따라 준비 자료 폴더 `artifacts/evaluations/baseline-preparation_20260911_182956/`를 삭제했다. 아래 내용은 삭제 전 점검 이력이며, 언급된 사본·JSON·해시 manifest는 현재 보존되어 있지 않다. 기존 평가 결과는 삭제하지 않았다.

2026-09-11 18:29–18:31 KST, 사용자의 1단계 시작 승인에 따라 입력을 보존하고 읽기 전용 서버 점검을 수행했다. LLM 추론, 평가, 재개는 수행하지 않았다.

- 기록 묶음: `artifacts/evaluations/baseline-preparation_20260911_182956/`. 평가 결과 디렉터리가 아닌 준비 기록이며 `results.json`은 없다. 이 경로는 Git 제외 대상이므로 로컬 원본을 별도로 보존해야 한다.
- 프로젝트 HEAD: `80168d861bee680ec2d15620fc28fcbe78ce2241`. 점검 시작 시 작업 트리는 깨끗했다. 직전 `141706e` 대비 실제 변경은 이 문서와 `41`·`22` 설정 추가뿐이며 Agent 및 평가 실행 코드는 바뀌지 않았다. 이 점검 기록을 작성하면서 문서만 추가 변경했다.
- 기존 Agent 프롬프트를 `agent-prompt.txt`에 보존했다. 확정한 P1은 아직 적용하지 않았다. 코드·설정·lockfile·준비 문서 사본, SHA-256, HEAD와 diff를 함께 저장했다.
- 공식 checkout: `fc0055dc4e0a316c3f83133267fbd6faaa770992`. 기존 `uv.lock` 변경이 있으며 그 diff를 보존했다. 설치된 tau2의 Python 소스 233개가 checkout과 텍스트 기준으로 모두 일치했다.
- 실제 데이터 경로: `C:\Users\chahoseong\projects\tau2-bench\data`. airline·retail의 tasks/policy/db 및 사용자 시뮬레이터 지침 사본을 보존했다. `environment.json`과 `manifest.json`에 해시를 기록했다.
- 기존 `.venv`의 Python 3.12.10, tau2 1.0.1, LiteLLM 1.82.6, Pydantic 2.13.5, httpx 0.28.1, OpenAI SDK 3.8.0을 확인했다. 재설치하지 않았다. 설치 출처는 `tau2-install-source.json`에 보존했다.
- 네 설정을 기존 `load_config()`로 로드하고 공식 `validate_task_ids()`를 모두 통과했다. 유효 설정은 `validated-configs.json`에 기록했다. 이 과정에서 LiteLLM 가격표 원격 조회가 제한되어 내장 사본으로 fallback했다. 이는 모델 추론 실패가 아니며 의존성을 변경하지 않았다.
- 기존 `_preflight_models()`의 Agent·User 조회가 모두 통과했다. `/health`, `/v1/models`, `/props`는 HTTP 200이었다. 모든 요청은 GET이며 응답은 `server.json`에 보존했다.
- 서버 모델 ID는 설정과 일치한다. 서버 빌드는 `b10883-91f6a6cf3`, 양자화 표기는 `Q4_0`, 보고된 context는 139776, 슬롯 수는 4다. 평가 동시 실행 수는 기존 설정의 1을 유지한다.
- 서버 기본값은 temperature 1.0, top_k 64, top_p 약 0.95, min_p 약 0.05, max_tokens/n_predict -1이다. 이는 조회된 서버 기본값이며 실제 요청의 최종 유효 옵션 전체를 증명하지 않는다. 설정에 생략된 생성 옵션을 이번 점검에서 추가하지 않았다. Trial seed는 기존 Agent·공식 simulator 전달 방식대로 유지한다.
- 서버가 보고한 모델 경로의 snapshot ID는 `29d097773436b69ff9feafd636ab4cf873786537`이다. 채팅 템플릿 원문을 보존했으며 SHA-256은 `6a1015c47ccfcfa67c3b772385bccee357a4d37c3cda37bd202e9047f391ab82`이다.

남은 확인 불가 항목은 실제 로드된 GGUF 파일 체크섬, 전체 서버 시작 명령과 GPU/backend 옵션, 다른 클라이언트의 동시 사용 및 후속 실행 중 서버 변경 여부다. 모델 이름·경로·빌드가 같다는 사실만으로 이를 같다고 단정하지 않는다. 제안하는 처리 방침은 이 한계를 명시하고 각 실행 직전 모델·빌드·기본값·채팅 템플릿을 재확인하며 차이가 발견되면 평가를 시작하지 않는 것이다. 이 방침과 2단계 airline `42` 3회 실행은 사용자 승인 대기 중이다.

### 이슈 #16 3단계: airline `41` 신규 기준 실행

2026-09-14 두 차례 서버 셧다운으로 중단됐던 task 41 평가를 사용자의 명시적 요청·범위 확인에 따라 삭제했다. 삭제 대상은 `artifacts/evaluations/2026-09-14_08-31-08_KST_d5e13cd0/` 전체(결과·분석·보존 사본 포함)와 최초·재개 로그 두 개다. 해당 결과는 신규 기준에 재사용하지 않는다. 완료된 task 42는 유지했다.

사용자는 현재 서버 조건으로 task 41을 신규 3회 실행하도록 승인했다. 09:19:22 KST, 기존 `configs/airline_task_41.toml`과 CLI로 신규 실행을 시작했다. 결과 디렉터리는 `artifacts/evaluations/2026-09-14_09-19-22_KST_6a9c3f3f/`, 로그는 `artifacts/evaluations/airline41-fresh_20260914_091917_678.log`이며 상세 분석은 결과와 같은 디렉터리의 `analysis.md`에 작성한다.

실행 전 Agent·User preflight 통과. 서버가 보고한 `n_ctx`는 현재 262144이며 이전 관찰값 139776과 다르다. 차이의 원인이나 사용자 설정 변경 여부는 확인되지 않았다. 모델 ID·빌드·템플릿 해시·슬롯 수·주요 샘플러 기본값은 앞선 관찰과 같다. 이 차이를 기록하고 사용자 승인에 따라 새로 실행하며 서버 설정을 직접 변경하지 않았다. Task 42는 이전 관찰 조건으로 유지하므로 두 task의 전체 서버 조건이 동일했다고 주장하지 않는다. 후속 변경 후 task 41 비교에서는 이번 신규 실행 조건과 대조해야 한다.

신규 trial 0(`69749b69-e051-4890-9b65-9f6db8b1ee57`, seed 670487)과 trial 1(`bca95ee9-04bf-4003-aad4-41288a2613f2`, seed 116739)은 각각 09:33:08·09:41:54에 완료됐다. 둘 다 reward 1·DB match true·read 8/8·write 해당 없음이며 실제 쓰기 없이 인계 종료했다. Trial 0은 UDMOP1의 부당 취소 제안, trial 1은 상태 확인과 사용자 거절 사유 안내 누락이 있다. 둘 다 초기 후보에 과거 4XGCCM을 포함했다. 상세 분석은 결과 디렉터리 analysis.md에 기록했다.

Trial 2 실행 중 서버가 다시 셧다운됐고 사용자가 복구했다고 확인했다. 09:54경 health 200은 복구 후 응답으로 정정 기록했다. 남아 있던 평가를 Ctrl+C로 중단해 종료 코드 1과 해당 Python 프로세스 부재를 확인했다. 완료 결과는 2개이며 미완료 trial 2를 reward 0으로 기록하지 않는다. 결과·metadata·로그 사본을 같은 결과 디렉터리의 `preserved/20260914_095519_755331/`에 보존하고 해시를 대조했다. 완료된 task 42 원본 해시도 유지됐다.

복구 후 모델·빌드·템플릿·n_ctx 262144·슬롯·주요 기본값은 이번 신규 실행 전 관찰값과 같았다. 확인 불가 조건은 여전히 남는다. 완료된 두 trial을 유지하고 공식 auto_resume으로 누락 trial 2만 처음부터 실행하는 방안은 사용자 승인 대기 중이다. 끊긴 대화 중간에서 재개하는 의미가 아니다.

사용자 승인 후 09:58:30에 공식 auto_resume으로 누락 trial 2만 재실행했다. 로그는 `artifacts/evaluations/airline41-resume_20260914_095830_198.log`다. 실행 중 사용자가 또 서버 셧다운을 알려 즉시 중단했고, 종료 코드 1과 관련 Python 프로세스 부재를 확인했다. 완료 결과는 여전히 2개이며 기존 simulation 전체와 metadata가 재개 전과 같다. 결과·metadata·재개 로그를 `preserved/20260914_100502_689034/`에 추가 보존하고 해시를 확인했다. 서버 복구 및 별도 재개 승인 전까지 중단한다. 셧다운 원인은 미확인이며 3단계는 미완료다.

두 번째 복구 후 서버 슬롯 수가 4→1로 달라졌고 사용자는 단일 클라이언트 사용을 근거로 이를 승인했다. 10:12:43 두 번째 auto_resume을 시작해 trial 2(`9fd2bd41-355e-4289-9c61-e07830e63dcb`, seed 26225)를 10:19:39에 완료했다. 재개 로그는 `artifacts/evaluations/airline41-resume_20260914_101243_897.log`, 종료 코드 0이다. 기존 trial 0·1의 전체 simulation과 최초 metadata 보존을 확인했다. 실제 최종 실행 묶음은 최초 신규 실행 1회와 승인된 재개 2회이며 중단 이력을 숨기지 않는다.

세 trial 모두 공식 reward 1·DB match true·실제 쓰기 없음·인계에 의한 user_stop이다. Reference read는 8/8·8/8·3/8, reference write는 모두 해당 없음이다. Trial 2는 예약 두 개만 조회한 뒤 UDMOP1 취소 진행을 조건부로 제안했다가 거절했다. 실제 무환불 취소 요청에 정책을 유지하고 인계했지만 나머지 다섯 예약의 조사를 마치지 않았다. 상세 판정과 근거를 analysis.md에 통합했다. 근거 있는 전체 무변경 수행은 0/3이며 구체 제안은 trial 0의 명확한 가능 오안내와 trial 2의 조건부 성급 제안을 구분한다. Trial 1의 사유 질문은 제안 판정을 보류했다. 공식 점수 1을 근거 있는 전체 무변경 수행 성공으로 해석하지 않는다.

Trial 0·1은 서버 슬롯 4, trial 2는 사용자 승인된 슬롯 1이다. Context는 이번 세 완료 trial에서 관찰값 262144이며 task 42의 이전 관찰값과 구분한다. 결과가 슬롯 차이와 무관하다거나 원인이 해결됐다는 결론은 내리지 않는다. 변경 후 비교에서 이 실행 조건 차이를 명시해야 한다. 프롬프트 P1은 여전히 미적용이다.

Task 41의 3단계를 완료한 뒤 사용자가 다음 task 22의 4단계를 승인했다.

### 이슈 #16 4단계: airline `22` 신규 기준 실행

사용자 승인에 따라 2026-09-14 10:29:21 KST에 기존 CLI·configs/airline_task_22.toml로 신규 3회 평가를 시작했다. 결과는 `artifacts/evaluations/2026-09-14_10-29-21_KST_7ea1bbde/`, 상세 분석은 같은 디렉터리 analysis.md, 콘솔 로그는 `airline22-baseline_20260914_102915_617.log`다. Agent·User preflight와 기본 프롬프트 유지를 확인했다.

서버는 직전 승인 조건과 같은 n_ctx 262144·슬롯 1이며 모델·빌드·템플릿·주요 샘플러 값이 일치했다. 승객·등급·수하물 세 변경과 차액 결제·무료 수하물 적용을 각각 분석한다. Trial별 gpt-6-astra/high 서브에이전트 분석 후 주 에이전트가 검증·통합한다. Retail 0은 아직 승인하지 않았으며 P1도 미적용이다.

2026-09-14 10:34 KST, 사용자가 서버 셧다운을 알려 즉시 task 22 평가를 Ctrl+C로 중단했다. 종료 코드 1과 해당 Python 프로세스 부재를 확인했다. 완료 simulation은 0개이며 미완료 trial을 실패 점수로 집계하지 않는다. 결과·metadata·로그를 `artifacts/evaluations/2026-09-14_10-29-21_KST_7ea1bbde/preserved/20260914_103417_746790/`에 보존하고 원본 해시를 대조했다. 셧다운 원인은 미확인이며 복구 확인·재개 승인 전까지 중단한다. 4단계 미완료, retail 실행 안 함.

복구 후 n_ctx 관찰값이 262144→193280으로 달라져 사용자에게 확인했고 현재 조건 승인을 받았다. 10:49:51 KST, 슬롯 1·context 193280에서 공식 auto_resume으로 세 trial을 시작했다. 이전 완료 결과가 0개여서 완료 simulation 간 과거 context 혼합은 없다. 재개 로그는 `airline22-resume_20260914_104951_980.log`이며 최초 metadata는 그대로 보존한다. 실제 trial 시각과 승인된 서버 조건은 analysis.md와 results.json에서 구분한다.

Context 193280 재개에서 trial 0(`2b1114b6-45d9-440d-8b59-d85bed47bf18`, seed 670487)이 10:59:38 KST에 완료됐다. 공식 reward 0·DB match false·write 1/3이며 승객만 변경했다. 동일편 승급 요청을 다른 항공편 선택으로 확대한 뒤 사용자가 대안을 선택했고, 최종적으로 basic economy의 항공편 교체를 거절했다. 마지막 거절 자체의 정책 적합성과 원래 허용된 승급·수하물 미완료를 구분해 analysis.md에 기록했다.

Trial 1 실행 중 사용자가 다시 서버 셧다운을 알려 11:05 KST에 즉시 중단했다. 완료는 1/3, 나머지는 점수 미산출이다. 결과·metadata·로그를 `preserved/20260914_110532_629262/`에 보존하고 관련 Python 프로세스 종료·해시를 확인했다. Context 193280에서도 발생한 셧다운의 원인은 미확인이다. 복구·재개 승인 전까지 중단하며 4단계는 아직 미완료다.

사용자 복구·재시작 승인 후 11:11:20 KST에 나머지 두 trial만 공식 재개했다. 서버 context 193280·슬롯 1과 주요 값은 이전 승인 조건과 같았다. 로그는 `airline22-resume_20260914_111120_286.log`이며 완료 trial 0과 metadata를 유지한다.

11:24:15 KST에 마지막 trial을 마쳐 종료 코드 0으로 3회 완료했다. Trial 1은 `ab71f8c7-a013-44dc-a8ab-6756fae3db42`(seed 116739), trial 2는 `a592f292-f935-488b-9d7b-9b2f472d814b`(seed 26225)다. 완료된 세 trial은 모두 context 193280·슬롯 1 관찰 조건이며 최초 262144 시도는 완료 결과가 없다. 기존 trial 0 전체와 최초 metadata는 보존 사본과 일치한다.

공식 reward는 0·0·1, reference write match는 1/3·0/3·2/3이다. 실제 승객/등급/수하물 완료는 trial별 1/3·0/3·3/3, 전체 요구 완료는 1/3이다. Trial 2는 도구 인자의 추가 필드 때문에 flights action match가 불일치했지만 공식 도구가 DB 가격으로 적용해 실제 세 변경·209달러 청구와 DB match를 달성했다. 다만 사전 가격·좌석 조회와 차액·결제수단 확인이 빠졌다. Trial 0·1의 대안 항공편 거절 자체는 정책에 맞으며, 원래 범위 확대·늦은 정책 대조·미완료와 구분한다.

세 trial을 각각 gpt-6-astra/high 서브에이전트로 분석하고 원본 대조·통합을 완료했다. 상세 증거·원본 해시·중단 이력은 결과 디렉터리 analysis.md에 있다. 4단계 완료이며 retail 0은 별도 승인 전까지 실행하지 않는다. P1 미적용·효과 판단 유보를 유지한다.

### 이슈 #16 5단계: retail `0` 신규 기준 실행

사용자가 5단계를 승인해 2026-09-14 11:34:46 KST에 기존 configs/retail.toml·CLI로 3회 신규 평가를 시작했다. 결과는 `artifacts/evaluations/2026-09-14_11-34-46_KST_c0605556/`, 상세 분석은 같은 디렉터리 analysis.md, 로그는 `retail0-baseline_20260914_113441_461.log`다. Context193280·슬롯1·빌드·템플릿·주요 기본값은 직전 승인 조건과 같다. Agent·User preflight와 기존 프롬프트 유지를 확인했다.

두 품목의 조건·재고·사용자 동의를 확인한 한 번의 교환 요청과 차액을 분석한다. 각 trial의 gpt-6-astra/high 분석 후 주 에이전트가 원본 대조·통합한다. P1과 추가 평가는 실행하지 않는다.

11:46:30 KST에 retail 신규3회가 중단·재개 없이 완료됐고 종료 코드0이다. Trial ID는 순서대로 `3083d48e-8cd9-40d8-ab1f-09501a24b095`, `ea00ac59-3472-493f-8eb9-34a3bb1322d7`, `38e3283d-1ee9-454b-aa5a-71374e189e0b`, 실제 seed670487·116739·26225다. 세 결과는 reward0·DBfalse·read4/4·write0/1이며 최종 대상·차액·카드는 정확하지만 마지막 동의+STOP으로 미접수다. Trial2는 앞선 진행 요청 후 재확인 기회가 있었고 trial0·1은 내역 질문에 응답한 뒤 최초 최종 동의에서 끝났음을 구분한다.

Trial1의 white후보 설명 오류, trial0·2의 설명/도구 혼합 및 사용자 전달 경계, 전체 품목 reminder 누락과 추가 안내 근거를 analysis.md에 기록했다. 세 trial 각각 gpt-6-astra/high 분석과 원본 대조·통합을 완료했다. 실행 후 GET /props는503으로 종료 후 서버 조건 동일성은 미확인이다. 완료된 simulation에 인프라 실패가 있었다고 추정하지 않으며 결과는 유지했다.

5단계 완료. 신규 기준12회 확보 후 최종 감사·통합 기록은6단계 별도 승인 대상이고 P1·변경 후 평가는 아직 실행하지 않았다.

### 이슈 #16 6단계: 변경 전 기준 최종 감사

2026-09-14, 사용자 승인으로 주 에이전트가 네 결과 묶음과 trial별 분석을 대조했다. **완료된 신규 simulation 12개와 분석 네 개를 기준 자료로 확정한다.** 기존 결과 재사용은 0개다. 원본 결과·metadata를 수정하지 않았고 추가 평가·공식 reviewer·P1 적용은 수행하지 않았다. 이 단계의 완료는 서버 조건 차이가 해소됐거나 프롬프트 효과를 판정할 수 있다는 뜻이 아니다.

#### 선택한 원본과 trial 명세

아래 A42/A41/A22/R0는 이 절에서만 사용하는 새 기준 묶음의 약칭이다. 위 과거 결과의 약칭과 혼합하지 않는다. 각 디렉터리에 `results.json`, `metadata.toml`, `analysis.md`가 있다. 분석의 `[n]`은 각 simulation의 0부터 시작하는 `messages[n]`이며 호출 ID로 원본과 연결한다.

| 묶음 | 원본 디렉터리 | 설정 | 전체 대화 분석 |
| --- | --- | --- | --- |
| A42 | `artifacts/evaluations/2026-09-11_18-44-51_KST_07b17b0e/` | `configs/airline_task_42.toml` | [analysis.md](../../artifacts/evaluations/2026-09-11_18-44-51_KST_07b17b0e/analysis.md) |
| A41 | `artifacts/evaluations/2026-09-14_09-19-22_KST_6a9c3f3f/` | `configs/airline_task_41.toml` | [analysis.md](../../artifacts/evaluations/2026-09-14_09-19-22_KST_6a9c3f3f/analysis.md) |
| A22 | `artifacts/evaluations/2026-09-14_10-29-21_KST_7ea1bbde/` | `configs/airline_task_22.toml` | [analysis.md](../../artifacts/evaluations/2026-09-14_10-29-21_KST_7ea1bbde/analysis.md) |
| R0 | `artifacts/evaluations/2026-09-14_11-34-46_KST_c0605556/` | `configs/retail.toml` | [analysis.md](../../artifacts/evaluations/2026-09-14_11-34-46_KST_c0605556/analysis.md) |

| 묶음 / trial | Simulation ID | Seed | 메시지 수 | Reward / DB match | Reference read / write match |
| --- | --- | ---: | ---: | --- | --- |
| A42 / 0 | `dbb5637b-b5e8-4f4c-8a57-4a523167b400` | 670487 | 28 | 0 / false | 8/8 / 0/2 |
| A42 / 1 | `206d5785-e17d-45d8-b094-185056a7f9eb` | 116739 | 28 | 0 / false | 8/8 / 2/2 |
| A42 / 2 | `26fe0f18-f706-43ce-af0b-424ccc842917` | 26225 | 34 | 0 / false | 7/8 / 2/2 |
| A41 / 0 | `69749b69-e051-4890-9b65-9f6db8b1ee57` | 670487 | 34 | 1 / true | 8/8 / 해당 없음 |
| A41 / 1 | `bca95ee9-04bf-4003-aad4-41288a2613f2` | 116739 | 26 | 1 / true | 8/8 / 해당 없음 |
| A41 / 2 | `9fd2bd41-355e-4289-9c61-e07830e63dcb` | 26225 | 20 | 1 / true | 3/8 / 해당 없음 |
| A22 / 0 | `2b1114b6-45d9-440d-8b59-d85bed47bf18` | 670487 | 36 | 0 / false | 해당 없음 / 1/3 |
| A22 / 1 | `ab71f8c7-a013-44dc-a8ab-6756fae3db42` | 116739 | 27 | 0 / false | 해당 없음 / 0/3 |
| A22 / 2 | `a592f292-f935-488b-9d7b-9b2f472d814b` | 26225 | 28 | 1 / true | 해당 없음 / 2/3 |
| R0 / 0 | `3083d48e-8cd9-40d8-ab1f-09501a24b095` | 670487 | 18 | 0 / false | 4/4 / 0/1 |
| R0 / 1 | `ea00ac59-3472-493f-8eb9-34a3bb1322d7` | 116739 | 18 | 0 / false | 4/4 / 0/1 |
| R0 / 2 | `38e3283d-1ee9-454b-aa5a-71374e189e0b` | 26225 | 22 | 0 / false | 4/4 / 0/1 |

12개 종료 사유는 모두 `user_stop`, `review=null`, `hallucination_retries_used=0`이다. 저장된 완료 대화의 도구 호출 95개는 각각 대응 반환이 있고 모두 `error=false`다. 이 사실은 아래 중단 시도가 없었다거나 서버·HTTP 내부 재시도가 없었다는 뜻이 아니다. Reference가 없는 항목은 해당 없음이며 0점으로 바꾸지 않는다.

#### 원본·입력·재개 보존 검증

| 묶음 | results.json SHA-256 | metadata.toml SHA-256 |
| --- | --- | --- |
| A42 | `02597d744c4e6a8c030195f6cd02c6fdafbace41bd9b880a1d367fc9c6dcebee` | `5375e8fd57f5b0290a353841afab49c2e3363297bc48135d9d250cbd3b63f761` |
| A41 | `a1c7831ccc0f8bb73dab580b7f5c65444a1e77445abf7391972ecacdf3b78417` | `7ec897cffabd643c6ce62e1424baa27792da067f82f47ff38cd267bb1e2c2010` |
| A22 | `6f6f61fe181bf911a18c026748f59328516c3c408f31db36e37f2f52c8477443` | `6047c958f019901a16c058a950d69ec91a6058116599864048d417e92e7ac8e9` |
| R0 | `622622bb6bb508ad5160898265d0a209a19d67e4487edae97ddebb4a2432a8f5` | `2b9620a2bf477daa73b2f675dd76aaf74f586d21b28ad569efeac50110715894` |

최종 감사에서 다음을 확인했다.

- 위 해시가 각 분석의 최종 원본 기록과 일치한다. 네 설정의 evaluation·Agent·User 내용과 metadata, 감사 당시 변경 전 `AGENT_PROMPT`와 네 저장 프롬프트가 일치했다. 공통 seed 42·trial 3·concurrency 1·max_steps 200·max_errors 10, 역할별 `generation={}`를 유지한다.
- 저장 task 네 개를 공식 `Task` 모델로 정규화해 현재 공식 task와 비교했고 일치했다. 저장 policy·User Simulator 지침도 현재 파일과 텍스트 기준으로 일치했다. 네 설정과 공식 airline/retail tasks·policy·db의 SHA-256은 각 분석의 입력 해시와 일치한다.
- 프로젝트 HEAD `80168d861bee680ec2d15620fc28fcbe78ce2241`, 공식 HEAD `fc0055dc4e0a316c3f83133267fbd6faaa770992`가 유지됐다. 설치된 tau2 Python 소스 233개가 공식 checkout과 텍스트 기준으로 일치한다. 공식 checkout의 기존 `uv.lock` 내 tau2 버전 1.0.0→1.0.1 차이 외 소스·데이터 diff는 없다.
- 기존 Python 3.12.10 / tau2 1.0.1 / LiteLLM 1.82.6 / Pydantic 2.13.5 / httpx 0.28.1 / OpenAI SDK 3.8.0을 재확인했다. Task 모델 로드 중 가격표 원격 조회 실패 후 내장 사본을 사용했으며 모델 평가 호출은 하지 않았다.
- Simulation ID 12개가 서로 다르고 task·trial·seed가 명세와 일치한다. 호출과 반환 ID의 대응·선후관계, 분석 내 전체 호출 ID와 simulation ID의 존재를 확인했다. 최종 표 12행의 점수·메시지 수·action match와 95개 호출의 분석 내 메시지 참조도 원본과 대조했다. 네 분석 링크가 존재하고 `git diff --check`를 통과했다. 이는 연결·수치 검증이며 자연어 판정의 자동 정답 검증은 아니다. 의미 판정은 앞 단계의 전체 대화 분석과 아래 핵심 근거 대조를 사용한다.
- A41 보존 사본 두 개의 완료 simulation 각 2개, A22 보존 사본 두 개의 완료 simulation 각 0개·1개가 최종 결과에 그대로 보존됐다. Metadata는 네 보존 사본 모두 최종 파일과 바이트 단위로 같다. 분석에 기록된 실행 로그 해시도 현재 파일과 대조했다.

위 검증은 현재 파일 및 남아 있는 실행 기록에 대한 대조다. 삭제된 준비 사본을 소급 복원하거나 실행 당시 서버 전체 환경을 증명하지 않는다. 원본은 Git 제외 디렉터리에 있어 문서 커밋만으로 다른 작업 환경에 전달되지 않는다. 후속 작업에는 위 네 디렉터리의 원본·분석·preserved 사본과 아래 로그를 함께 전달해야 한다.

#### 실행 횟수와 중단 이력

| 묶음 | 신규 진입 / 공식 재개 | 중단 시점 | 최종 완료 수 | 보존 위치: 각 원본 디렉터리 아래 |
| --- | --- | --- | ---: | --- |
| A42 | 1 / 0 | 없음 | 3 | 별도 중단 사본 없음 |
| A41 | 1 / 2 | 최초 trial 2, 첫 재개 trial 2 | 3 | `preserved/20260914_095519_755331/`, `preserved/20260914_100502_689034/` |
| A22 | 1 / 2 | 최초 trial 0, 첫 재개 trial 1 | 3 | `preserved/20260914_103417_746790/`, `preserved/20260914_110532_629262/` |
| R0 | 1 / 0 | 없음 | 3 | 별도 중단 사본 없음 |

선택한 최종 묶음은 신규 진입 4회 + 재개 4회 = 총 8회이며 중단된 실행 시도는 4회다. 미완료 시도는 성공·실패 분모에 넣지 않았다. 재개는 기존 등록·preflight·RunConfig 생성 경로에서 `run_config.auto_resume = True`로 설정한 뒤 공식 `run_domain(run_config)`를 사용했고 누락 trial을 처음부터 실행했다. 중간 대화 이어 쓰기나 성공이 나올 때까지 완료 trial 재평가를 수행한 것이 아니다. 위 실행·재개 절의 명령과 각 분석의 시각·조건·보존 해시를 함께 읽는다.

콘솔 로그는 `artifacts/evaluations/` 아래 다음 파일이다.

- A42: `airline42-baseline_20260911_184445_928.log`.
- A41: `airline41-fresh_20260914_091917_678.log`, `airline41-resume_20260914_095830_198.log`, `airline41-resume_20260914_101243_897.log`.
- A22: `airline22-baseline_20260914_102915_617.log`, `airline22-resume_20260914_104951_980.log`, `airline22-resume_20260914_111120_286.log`.
- R0: `retail0-baseline_20260914_113441_461.log`.

A42 로그에는 transcript 시작·종료만 있고 Python 출력이 누락됐다. 나머지는 Tee-Object로 기록했지만 중단 trial의 완전한 대화가 results에 없으면 분석을 추정해서 채우지 않는다. 비용 계산의 가격표 미등록 메시지와 인프라 중단은 구분하며 저장 비용 0을 무료 사용의 증거로 삼지 않는다.

사용자가 삭제한 이전 A41 `2026-09-14_08-31-08_KST_d5e13cd0/`와 최초·재개 로그 두 개는 위 8회·12개에 포함하지 않는다. 이 폐기 묶음의 신규/재개 2회와 두 중단은 대화·문서의 이력으로 남지만 원본 재검증은 불가능하다. 준비 디렉터리 `baseline-preparation_20260911_182956/`도 사용자 요청으로 삭제됐다. 따라서 전체 작업에서 실행 시도가 오직 8회였다고 표현하거나 삭제된 입력 사본·서버 응답이 보존돼 있다고 표현하지 않는다.

#### 서버 조건과 비교 가능 범위

| 완료 결과 | 실행 직전 관찰 n_ctx | 슬롯 | 해석 |
| --- | ---: | ---: | --- |
| A42 trial 0–2 | 139776 | 4 | 2026-09-11 관찰 조건 |
| A41 trial 0–1 | 262144 | 4 | 새 기준 실행 조건 |
| A41 trial 2 | 262144 | 1 | 복구 후 차이를 사용자 승인 |
| A22 trial 0–2 | 193280 | 1 | 최초 262144 시도는 완료 0개라 이 표에서 제외 |
| R0 trial 0–2 | 193280 | 1 | 실행 후 /props 503으로 종료 후 조건 미확인 |

Agent·User 모델명은 모두 `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`, endpoint는 `http://100.80.184.89:8080/v1`이다. 관찰된 빌드 `b10883-91f6a6cf3`, 템플릿 해시 `6a1015c47ccfcfa67c3b772385bccee357a4d37c3cda37bd202e9047f391ab82`, 주요 기본값 temperature 1 / top_k 64 / top_p 약 0.95 / min_p 약 0.05 / max_tokens -1은 실행 기록상 같다. 서버가 보고한 context 값 차이를 사용자 설정 변경이나 셧다운 원인으로 단정하지 않는다. 사용자의 단일 클라이언트 사용 설명과 평가 concurrency 1도 슬롯 차이의 영향이 없음을 입증하지 않는다.

실제 GGUF 체크섬·전체 서버 시작 옵션·GPU/backend 조건·요청별 최종 유효 옵션·실행 중 연속 상태는 확인 불가다. 현재 서버를 다시 조회해도 과거 조건을 복원할 수 없으므로 이번 감사에서는 새 서버 조회를 하지 않았다. Retail 종료 후 503은 완료 대화의 인프라 실패를 의미하지 않으며, 복구 후 health 200은 이전 셧다운을 부정하지 않는다.

후속 P1 평가는 동일 task·trial·seed별 조건을 이 표와 대조해야 한다. 특히 A41은 단일 공통 서버 조건으로 기존 세 trial을 모두 맞출 수 없다. 현재 차이는 사용자가 수용한 기준 조건으로 기록하며 #16 완료의 장애물로 취급하지 않는다. 후속 평가의 실행 조건과 범위는 해당 단계 승인 시 명시한다. 현재 기준을 임의 폐기·교체하거나 추가 기준 평가를 자동 수행하지 않는다. Seed가 같아도 프롬프트·응답 변화에 따라 사용자 대화가 달라질 수 있으므로 동일 대화나 인과 효과를 보장하지 않는다.

#### 공식 검사와 실제 행동의 통합 판정

| Task | 공식 reward 1 | 실제 요구 완료 관찰 | 해석에 필요한 차이 |
| --- | --- | --- | --- |
| Airline 42 | 0/3 | 필요한 두 취소 2/3, 정확히 두 개만 취소 0/3 | 추가 취소 2/3. 정정 전 제안까지 포함한 기존 주 관찰 오류 3/3 |
| Airline 41 | 3/3 | 쓰기 없는 DB 결과 3/3, 근거 있는 전체 무변경 수행 0/3 | 안 바꾼 결과와 전체 조회·정책 판단·안내의 완전성은 다름 |
| Airline 22 | 1/3 | 승객 2/3, 동일편 승급 1/3, 수하물 1/3, 세 변경 전체 1/3 | Trial 2의 실제 세 변경과 209달러 청구는 완료됐으나 사전 차액·결제 확인 미충족 |
| Retail 0 | 0/3 | 최종 대상·차액·카드 정확 3/3, 교환 접수 0/3 | 마지막 동의와 STOP이 함께 발생. Trial 2의 앞선 진행 요청은 별도 관찰 |

이 표의 분모는 각 task의 완료된 3개 trial이다. 서로 다른 목표를 가진 task를 합쳐 하나의 행동 성공률로 만들지 않는다. 특히 task 42의 사전 확정 주 관찰 오류를 다른 task의 모든 절차 오류와 합산해 새 지표로 바꾸지 않는다.

핵심 근거와 해석 경계:

1. **기대 호출 일치·최종 DB·정책 준수는 각각 다른 정보다.** 공식 `evaluator/evaluator.py`는 action 검사를 저장하지만 task의 `reward_basis`에 포함된 항목으로 reward를 결합한다. 이번 airline은 DB·COMMUNICATE이며 communicate 기준은 비어 있다. Retail은 DB·NL_ASSERTION이며 NL assertion 목록이 비어 있어 해당 성분이 1이다. Airline의 NL 미실행과 retail의 빈 기준을 모두 실제 자연어 무오류 판정으로 해석하지 않는다. 공식 reviewer도 12개 모두 미실행이다.
2. **Action 일치는 추가 오류를 배제하지 않는다.** A42 trial 1의 `[22]`와 trial 2의 `[24,26,28,30]`은 기대 취소 둘을 포함해 write 2/2지만 추가 취소 때문에 DB가 다르다. 반대로 A22 trial 2 `[22]→[23]`은 flights 인자의 추가 필드로 action match가 false여도 공식 도구가 DB 가격을 적용해 올바른 최종 DB를 만들었다. `[18–19]`에 구체 차액·결제수단 동의가 없었던 절차 문제는 이 성공과 별개로 남는다.
3. **사용자 동의와 올바른 대상 판단을 분리한다.** A42 trial 2는 숨은 task의 타인 제외 조건과 다른 사용자 발화·동의가 있었다. 결과 이탈은 보존하되 명시적 제외 요청 무시·무동의 취소로 기록하지 않는다. A22 trial 0·1은 Agent가 먼저 항공편 교체로 범위를 넓혔고 사용자가 대안을 선택했다. 이후 basic economy의 항공편 교체를 거절한 것 자체는 정책에 맞으며 원래 동일편 승급 미완료와 구분한다.
4. **구체 제안의 불확실성을 유지한다.** A41 trial 0 `[28]`은 취소 가능 오안내, trial 2 `[10]`은 자격 확인 전 조건부 진행 제안이다. Trial 1 `[20]`의 사유 질문은 구체 변경 제안인지 판정 보류다. 이를 세 건의 확정 오제안이나 모호성 없는 단일 비율로 바꾸지 않는다. Trial 2에서 실제 무환불 요청을 거절한 사실을 발화가 없었던 trial 0·1에도 가정해 적용하지 않는다.
5. **STOP 직후 행동은 관찰 불가지만 이전 기회는 남는다.** R0 trial 0·1은 내역·가격 질문에 응답한 뒤 첫 최종 확인에서 STOP으로 끝났다. Trial 2는 `[19]`에 STOP 없는 진행 요청을 받고 `[20]`에서 재확인한 뒤 `[21]` STOP을 받았다. A42 trial 0도 `[25]` 동의 뒤 `[26]` 응답 기회가 있었다. 실제 미완료는 유지하되 모두 기회가 없었다고 설명하거나 재확인이 STOP을 유발했다고 단정하지 않는다.
6. **생성한 설명과 사용자에게 전달한 설명을 구분한다.** 공식 half-duplex `orchestrator/orchestrator.py`의 도구 호출 메시지는 ENV로 전달되며 User history에서도 제외된다. A22 trial 0 `[14]`, R0 trial 0 `[10]`·trial 2 `[14]`의 자연어와 도구 혼합에 동일 원칙을 적용했다. 특히 R0 trial 2의 정확한 품절 설명은 생성됐지만 그 메시지로 사용자에게 안내되지 않았다. 전체 품목 reminder 누락·부정확한 후보/환불 안내도 실제 쓰기 부재와 분리해 분석에 보존했다.

판정은 사전 확정한 충족·미충족·관찰 불가·해당 없음과 제안→동의→실행→결과 구분을 유지했다. 정정된 초기 오류를 삭제하지 않으며 DB false만으로 개별 미변경 레코드 전체의 상태를 증명하지 않는다. 도구 호출·반환 및 실제 도달한 대화 범위를 근거로 삼는다.

#### 이슈 #16 완료 조건 대조와 후속 인계

| 완료 조건 | 감사 결과 |
| --- | --- |
| 네 task 각각 비교 기준 3개 | 충족. 원본 12개를 확보했고 사용자가 환경 차이와 기록 한계를 명시한 비교 기준으로 수용했다. 동일 조건·인과 효과 보장을 뜻하지 않음 |
| 공식 검사와 실제 행동 차이를 원본으로 설명 | 완료. 네 analysis의 메시지·호출 ID와 위 통합 판정으로 연결 |
| 기존/신규·조건·중단/재개 추적 | 선택된 신규 결과와 보존 사본 대조 완료. 삭제된 과거 묶음·준비 자료 및 A42 콘솔 누락은 검증 한계로 명시 |
| 후속 담당자가 변경 전 Agent와 비교 결과를 식별 | 완료. HEAD·프롬프트·설정·원본 목록 확정, P1 미적용 |

6단계의 원본 감사·통합 문서 작업을 완료했다. 이후 사용자가 현재 기준 자료의 한계를 설명받고 이슈 #16 정리·마무리를 승인했다. 현재 12개 결과를 기준으로 수용하며 context·슬롯 차이만을 이유로 추가 평가를 수행하지 않는다. 이 차이가 결과에 영향을 주었다는 증거는 확보하지 못했고, 동일 서버 조건에서의 인과 효과도 입증하지 않았다. GitHub 이슈에는 완료 항목·결과 경로·검증·한계를 반영하고 완료 사유로 종료한다. 다음 작업은 P1 적용·변경 후 평가이며 해당 단계의 범위와 실행 조건은 별도로 승인받는다. 효과 있음·없음 판단은 그 결과를 확보한 후 기존 기준으로 수행하며, 조건 차이나 관찰 불가가 결론을 바꿀 수 있으면 판단 유보로 남긴다.

## 이슈 #17 적용 기록

사용자 승인으로 1단계 문구 적용, 2단계 검증, 3단계 기록·최종 검토를 완료했다. **P1은 적용됐으며 실제 행동 개선은 아직 평가하지 않았다.** 위 변경 전 문구와 확정 P1을 빈 줄로 연결한 것이 현재 프롬프트 전체다. 과거 기준 원본·metadata는 변경 전 상태를 그대로 유지한다.

### 무엇을 왜 변경했는가

`agents/task_agent.py`의 `AGENT_PROMPT`에 P1 세 문장만 추가했다. 기존의 일반적인 정책 준수 지침에 대상 판단 전 조회·요구/제외 조건/정책 대조를 명시하기 위한 변경이다. 특정 task·예약·정답이나 도구 호출 순서를 포함하지 않는다. 사용자 확인과 한 번에 한 도구 호출 등 공식 정책을 유지한다.

`get_init_state()`의 기존 결합 경로는 변경 전 지침 → P1 → Domain Policy 순서의 system instructions를 만든다. `generate_next_message()`는 기존처럼 이를 대화 이력과 함께 LLM에 전달하고, `write_metadata()`는 호출 시점의 `task_agent.AGENT_PROMPT`를 저장한다. Agent Loop·state·실행 제어·모델·User Simulator·evaluator·의존성 변경은 없다.

### 코드 버전 식별

적용 작업의 기준 HEAD는 `1a5434e0775a0c0dc62ff25fad544647f2ed207b`다. P1은 이 HEAD 위의 미커밋 변경이며 HEAD만으로 적용 여부를 식별하면 안 된다. 이전 기준 평가의 HEAD `80168d861bee680ec2d15620fc28fcbe78ce2241`와도 구분한다. diff는 `git diff 1a5434e0775a0c0dc62ff25fad544647f2ed207b -- agents/task_agent.py`로 확인한다.

| 식별 대상 | 변경 전 SHA-256 | P1 적용 후 SHA-256 |
| --- | --- | --- |
| 프롬프트 문자열 UTF-8 | `04e85eae6600569754de79bf267fcb971c72620ed631483df6906479a679b42b` | `dde31a582b9495743e5fb29257e34e9d1cb4f544a98f2354495cb21e0ddb2bd3` |
| task_agent.py 소스, CRLF를 LF로 정규화 | `0b249dc1e884c64147bd132c4aadad206b2fc573b80bddfc45a51bb623d21e68` | `c23365f87ce0f5965d73db46cf927f526db707ef37993d91c775c3c6e94fa62e` |

후속 평가 전에 실제 프롬프트와 이 해시를 대조하고 당시 HEAD·미커밋 diff를 기록한다. Metadata의 commit 필드는 HEAD를 기록하므로 미커밋 P1 적용 자체를 증명하지 않는다. 함께 저장된 `prompts.agent`가 실제 문구 식별 근거다. 이후 커밋할 경우 새 commit을 추가 기록한다.

### 검증 결과와 한계

2단계에서 기존 가상환경의 `.venv/Scripts/python.exe -B -m` 뒤에 아래 명령을 붙여 실행했다. uv 실행 링크가 작동하지 않아 이 경로를 사용했고 패키지 재설치는 하지 않았다.

| 검사 | 결과 |
| --- | --- |
| `pytest tests/test_task_agent.py tests/test_eval_metadata.py` 최초 실행 | Agent 16개 통과. Metadata 13개는 기본 임시 폴더 권한 문제로 setup 오류 |
| `pytest -p no:cacheprovider --basetemp <작업 디렉터리 안의 새 임시 경로> --tb=short` | 관련 29개를 포함한 전체 195개 통과 |
| `ruff check .` | 통과, 변경 파일 포함 |
| `ruff format --check .` | 수정 파일의 줄바꿈을 formatter로 정리한 후 40개 파일 통과 |
| `mypy` | 변경 파일을 포함한 18개 소스 통과 |
| `git diff --check` | 통과 |

테스트 실행에만 `LITELLM_LOCAL_MODEL_COST_MAP=True`를 사용해 원격 가격표 조회를 피했다. Pytest 임시 경로와 캐시 설정만 조정했고 제품 코드·테스트를 권한 문제에 맞춰 변경하지 않았다. 새 임시 폴더는 종료 후 정리했다. 공식 의존성의 audioop 폐기 예정 경고 1건이 남았다.

기존 테스트는 프롬프트/정책 결합, system instructions의 모델 입력 전달, 현재 프롬프트 문자열의 metadata 왕복 보존을 각각 검사한다. 1단계의 확정 문구 일치 검토와 함께 사용하며 같은 문구를 반복 검사하는 테스트는 추가하지 않았다. Mock 응답을 사용하는 테스트는 실제 모델의 판단 개선이나 정책 준수를 입증하지 않는다.

### 최종 검토와 완료 조건

정확성·가독성·구조·보안·성능 관점에서 검토했고 수정이 필요한 항목은 발견하지 못했다. 확정 문자열과 일치하며 추가 추상화·입출력·권한·dependency는 없다. 프롬프트가 길어진 만큼 입력은 늘고 모델의 조회 행동도 달라질 수 있지만, 토큰 비용·지연·정확도 변화는 측정하지 않았다. 지침은 행동을 유도하며 도구 실행을 코드로 차단하지 않는다.

- [x] 확정 지침의 system instructions 구성·LLM 입력 전달 경로 확인.
- [x] 프롬프트 보강만 변경하고 평가 정답·task 전용 분기 미포함.
- [x] 현재 프롬프트 metadata 보존 경로와 기존 테스트·필수 검사 확인.
- [x] 문구·이유·diff 기준·해시·검증 기록으로 적용 버전 식별 가능.

이슈 #17의 로컬 작업을 완료했다. GitHub 이슈 업데이트·종료 및 commit/push는 수행하지 않았다. 실제 benchmark와 변경 후 행동 비교는 별도 승인된 후속 작업에서 수행한다.

## 변경 후 결과

아직 실행하지 않음. 후속 작업에서 원본 경로·metadata·trial별 관찰표를 기록한다.

## 결론

아직 판단하지 않음. 후속 작업에서 공식 점수, 판단·완료·부작용·종료 영향과 근거를 종합해 효과 있음·효과 없음·판단 유보를 기록한다. 결과가 불리하거나 유보여도 근거와 한계를 설명했다면 학습 목표를 달성할 수 있으며, 자동으로 추가 튜닝·평가를 반복하지 않는다.
