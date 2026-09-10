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
