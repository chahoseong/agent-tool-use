# 실험 근거 자료

## 파일 위치

| Task       | 지침 추가 전                                       | 지침 추가 후                                   |
| ---------- | -------------------------------------------------- | ---------------------------------------------- |
| airline 42 | [Baseline](prompt-improvement/airline-42/baseline/) | [Prompt](prompt-improvement/airline-42/prompt/) |
| airline 41 | [Baseline](prompt-improvement/airline-41/baseline/) | [Prompt](prompt-improvement/airline-41/prompt/) |
| airline 22 | [Baseline](prompt-improvement/airline-22/baseline/) | [Prompt](prompt-improvement/airline-22/prompt/) |
| retail 0   | [Baseline](prompt-improvement/retail-0/baseline/)   | [Prompt](prompt-improvement/retail-0/prompt/)   |

[Reflection 결과](reflection/airline-42/)는 airline 42 trial 0이며, 비교 대상은 위 airline 42 Prompt의 trial 0이다.

## 파일 설명

- `results.json`: 공식 채점, 대화·도구 호출·결과, task와 정책 정보.
- `metadata.toml`: 실행 설정, Agent 프롬프트, 코드 버전.
- `judge/`: 추가 채점 기준과 trial별 판정·근거.
- Reflection의 `reflection/`, `prompt-snapshot.json`, `stop-record.json`: 검토·수정 과정, 사용한 프롬프트, 중단 기록.
- [manifest.json](manifest.json): 원본 위치·해시와 실행별 집계. [verification.json](verification.json): 파일·집계·링크 검증 결과.
- [chart-data.json](chart-data.json): 정정을 반영한 차트용 집계.
- [LICENSE.tau2-bench](LICENSE.tau2-bench): 포함된 공식 benchmark 자료의 라이선스.

## 판정 정정

`retail 0` Baseline의 사용자 동의는 원래 세 실행 모두 ‘해당 없음’이었다. 실제 기록에서 명시적 동의를 확인해, 문서와 차트에는 **3/3 통과**로 반영했다.

원본 judge 파일은 그대로 두고, [corrections.json](corrections.json)에 원래 판정·정정 내용·메시지 근거를 남겼다. 모델 재채점은 수행하지 않았다.
