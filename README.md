# agent-tool-use

TaskAgent를 공식 tau2-bench mock task로 평가합니다. 현재는 llama.cpp 서버를 지원합니다.

## 빠른 시작

프로젝트 루트에서 실행합니다. `.env.example`을 참고해 `.env`에 데이터 경로를 지정하고, 사용할 llama.cpp 서버를 실행하세요.

```dotenv
TAU2_DATA_DIR=../tau2-bench/data
```

상대 경로는 현재 작업 디렉토리 기준입니다.

```powershell
uv run python scripts/evaluate.py init
```

생성된 `evaluation.toml`에서 평가할 `task_ids`와 Agent·User의 모델 ID, 서버 주소를 수정합니다. 자세한 설정은 템플릿 주석을 참고하세요.

```powershell
uv run --env-file .env python scripts/evaluate.py run evaluation.toml
```

`results.json`과 `metadata.toml`이 실행별 디렉토리에 저장되며, 결과 파일 경로가 출력됩니다.

출력 전 검토와 피드백 반영을 활성화하려면 설정 파일에 다음 섹션을 추가합니다.

```toml
[reflection]
enabled = true
max_revisions = 2
```

생략하면 비활성화됩니다. `max_revisions`는 0 이상의 정수이며, 0이면 최초 검토만 수행합니다.
작성·수정·검토는 Agent의 동일 모델 설정을 사용하고 적용값은 `metadata.toml`에 기록됩니다.
활성화된 평가의 내부 검토 과정은 실행 디렉토리의 `reflection/<출력 ID>.jsonl`에 저장됩니다.
`reflection/index.json`은 로그와 공식 simulation·trial·메시지 위치의 대응표입니다.
공식 출력이 남지 않은 실패 시도의 로그는 미연결 상태로 보존합니다.

## LLM 추가 평가

Codex에서 `$judge-evaluation`과 결과 디렉터리를 지정하면 trial별 서브에이전트가
기존 행동 기준으로 추가 채점합니다. 기본 모델은 `gpt-6-astra`, 추론 강도는 `high`입니다.
공식 평가가 끝나도 자동 실행하지 않으며, 스킬 실행 요청은 실험 이름 확인,
채점·검증·재검토·JSON 저장·Langfuse 등록과 링크 제공까지 포함합니다.
이미 이름을 지정했다면 다시 묻지 않습니다. 로컬 저장만 요청하면 Cloud 등록을 생략합니다.

결과는 원본 아래 `llm-judge/<UTC시각>_<고유ID>/`에 저장됩니다.
`manifest.json`은 준비 정보, `trial_<번호>.json`은 판정·실제 증거·시도 이력,
`completion.json`은 최종 상태입니다. 재평가는 새 폴더를 사용합니다.
`analysis.md`는 필수 산출물이 아닙니다. 현재 기준은 airline 42·41·22와 retail 0을 지원합니다.

`uv run python -m evals.judge --help`로 입력 준비·저장·완료 검증 명령을 확인할 수 있습니다.
이 명령 자체는 LLM을 호출하지 않으며, 서브에이전트 실행과 의미 검토는 Codex 스킬이 담당합니다.

## Langfuse Cloud에서 보기

`.env`에 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, 프로젝트 리전의
`LANGFUSE_BASE_URL`을 설정합니다. 키는 저장소에 커밋하지 않습니다.

```powershell
uv run --env-file .env python -m evals.langfuse_export "<결과 디렉터리>" --trial 0
```

`--trial`을 생략하면 해당 결과의 모든 trial을 전송합니다. 추가 판정까지 보려면
`--judge "<llm-judge 실행 디렉터리>"`를 지정합니다. 반환되는 trace URL을 엽니다.
trial마다 `evaluate-task` 아래 모델 응답과 도구 요청·결과가 표시되며,
공식 점수는 `tau2.reward`, 검증 완료된 추가 판정은 `judge.<기준 ID>`로 표시됩니다.
추가 판정의 comment에는 이유와 실제 증거를 함께 넣습니다. 미해결 판정은 점수로
등록하지 않고 evaluator 출력에 상태와 함께 남깁니다.

reflection 로그가 있으면 대응표와 공식 출력을 검증한 뒤 해당 응답 아래에
`reflect-agent-response`를 연결합니다. 초안·수정·검토 호출과 종료 이유를 볼 수 있으며,
reflection 판정은 judge 점수로 등록하지 않습니다. 미연결 실패 로그는 게시하지 않습니다.
새 trace는 내부 모델 호출에서 사용량을 집계합니다. 기존 trace에 추가할 때는 최종 호출의
사용량을 기존 관찰에 유지하고 내부의 동일 호출은 참조용 span으로 표시합니다.
동일 로그의 재게시와 전송 불확실성은 프로젝트별 게시 기록으로 관리합니다.
로그에는 전체 모델 요청이 없으므로 내부 관찰의 input은 저장된 초안·피드백 범위입니다.

이 명령은 저장된 공식 mock 데이터를 Cloud로 전송합니다. 모델·벤치마크를 다시
실행하지 않고 원본 파일도 변경하지 않습니다. 원본 아래 `langfuse/`의 프로젝트별
전송 기록으로 기존 trace를 재사용하고, 같은 judge 결과의 score는 같은 ID로 갱신합니다.
전송 성공 여부가 불명확하면 재생성하지 않고 확인이 필요한 상태로 멈춥니다.
전송 기록을 삭제하지 마세요. 기존 전송분은 `--trial 0 --adopt-trace <ID>`로
원본 일치 여부를 확인하고 연결할 수 있습니다.
원본 simulation ID로 session을 묶고, 원본 해시·task·trial·seed·commit을 기록합니다.

과거 기록을 가져오는 방식이므로 trace의 latency는 업로드 작업 시간입니다.
실제 평가 시각·소요 시간은 `original_*` metadata를 사용합니다. Generation의 input은
저장된 대화 흐름이며 실제 모델 요청을 완전히 복원한 값이 아닙니다.
정책·도구 명세·저장된 agent prompt는 root metadata에 따로 보존합니다.

스킬은 승인된 실험 이름과 원본·judge 디렉터리 목록을 `publication.json`에 저장하고
`uv run --env-file .env python -m evals.publish_evaluation "<publication.json>"`을 실행합니다.
같은 비교 사례 집합을 Dataset에 묶고, 공식 SDK의 실험 실행기에 저장된 판정을
반환하여 실험 항목을 등록합니다. 이때 모델·judge를 다시 실행하지 않습니다.
실험 결과 기록에는 기존 대화 trace 링크와 판정 JSON을 담으며 대화·토큰 기록을 복제하지 않습니다.
실험 이름에는 자동 식별 접미사가 붙으며, 재채점은 별도 실험 이력으로 구분됩니다.
실험 항목의 공식 점수는 원본 trace 점수와 별도 연결되므로 집계 시 observation 범위를
구분합니다. 전송 실패 시 같은 계획으로 등록만 재시도하며 judge를 다시 실행하지 않습니다.
성공하면 `publication.published.json`에 링크가 남습니다.

구현 근거: [공식 tracing 지침](https://langfuse.com/docs/observability/best-practices),
[SDK instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation).

## 조회 명령

Task 목록과 상세 정보:

```powershell
uv run --env-file .env python scripts/evaluate.py tasks
uv run --env-file .env python scripts/evaluate.py show create_task_1
```

평가 결과 조회:

```powershell
uv run --env-file .env tau2 view --file "<출력된 results.json 경로>"
```

추가 옵션은 [tau2 view 공식 문서](https://github.com/sierra-research/tau2-bench/blob/main/docs/cli-reference.md#tau2-view--view-results)를 참고하세요.

도움말:

```powershell
uv run python scripts/evaluate.py --help
```
