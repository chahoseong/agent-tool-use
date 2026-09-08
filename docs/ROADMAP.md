# 프로젝트 로드맵

## 프로젝트 목표

tau2-bench의 mock domain에서 도구를 사용해 작업을 수행하는 Agent를 구현하고, Agent Loop의 실행 흐름을 이해한다.

공식 benchmark의 trajectory와 평가 결과를 바탕으로 실패를 분석하고, 개선 하나를 적용·재평가하여 효과와 한계를 설명할 수 있는 역량을 확보한다.

## 범위

### 포함

- Tool 선택과 Tool Calling
- Tool arguments 구성
- Tool 실행과 Tool Result 전달 구조
- 요청 → 판단 → 도구 호출 → 관찰 → 완료의 기본 Agent Loop
- Conversation / Agent state 유지
- τ-bench 공식 task를 이용한 평가
- trajectory 기반 실패 분석

### 제외

- Reflection pattern
- Explicit Planning
- Multi-Agent
- RAG
- MCP
- 장기 메모리
- 별도 DB·서비스·Frontend·배포
- 자체 benchmark/evaluator 구축
- 복잡한 Agent framework 또는 workflow orchestration

## 진행 단계

| 단계 | 핵심 작업 | 단계 완료 기준 |
| --- | --- | --- |
| **1. 공식 실행 이해 — 완료** | 공식 MinimalAgent로 `mock/create_task_1`을 실행하고 trajectory와 평가 결과를 확인한다. | LLM·Agent·Orchestrator·Environment·Evaluator의 역할을 실제 실행과 연결해 설명한다. |
| **2. 최소 Agent 구현** | tau2의 Agent contract에 맞는 최소 Agent를 현재 프로젝트에 구현하고 기존 평가 환경에 연결한다. | 작성한 코드가 LLM 호출, 도구 호출 요청, 도구 결과 처리, conversation state에 어떻게 관여하는지 설명하고, tau2가 담당하는 도구 실행·흐름 진행과 구분한다. |
| **3. 기준 평가·실패 탐색** | 선정한 mock task를 평가하고 trajectory를 분석한다. 필요하면 mock 전체와 제한된 challenge case로 범위를 넓힌다. | 분석할 실패 또는 개선할 행동을 특정하고, 관찰 사실·실패 또는 개선 지점·원인 가설을 근거와 함께 구분한다. |
| **4. 개선·재평가** | 가장 근거 있는 변경 하나를 적용하고 비교 조건을 유지해 재평가한다. | 변경 이유, 전후 결과, 가설을 지지하거나 반박하는 근거, 효과와 한계를 설명한다. |
| **5. 최종 정리** | 구현·기준 평가·분석·변경·재평가 결과를 재현 가능하게 정리한다. | 다른 사람이 기준 실행부터 결과 해석까지의 근거를 따라갈 수 있다. |

## 완료 기준

> 내 Agent가 어떻게 도구를 사용하는지, 무엇이 어디서 실패하거나 개선이 필요하다고 판단했는지, 무엇을 바꿨고 결과가 어떻게 달라졌는지를 코드와 실행 기록으로 설명할 수 있다.

- 자신의 Agent 코드에서 입력, state 갱신, LLM 호출, 도구 호출 요청 반환의 흐름을 실제 trajectory와 연결한다.
- 평가 조건과 원본 결과를 남기고, 성공 점수가 확인하는 내용과 확인하지 않는 내용을 설명한다.
- 관찰된 사실과 원인 가설을 구분하여 실패 또는 개선할 행동을 분석한다.
- 분석에 근거한 변경 하나를 적용하고, 재평가 결과로 가설을 판단한다.
- Agent 코드, 재현 명령과 설정, trajectory, 평가 결과, 실패 분석, 개선 전후 비교 기록을 남긴다. 인증 키 등 비밀정보는 저장하지 않는다.