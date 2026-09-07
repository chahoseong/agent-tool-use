# Tool Use

## 정의

`Tool Use`는 **에이전트(Agent)**가 작업을 수행하는데 필요한 **도구(Tool)**를 판단하고 사용하는 능력입니다. 

## 작동 방식

```mermaid
sequenceDiagram
    autonumber
    participant U as 사용자
    participant A as 에이전트
    participant L as LLM
    participant T as 도구

    U->>A: 작업 요청
    A->>L: 사용자 요청 + 사용 가능한 도구 명세

    loop 도구 사용이 필요한 동안
        L-->>A: 도구 호출 요청
        A->>T: 도구 실행
        T-->>A: 실행 결과
        Note over A: 도구 호출 요청과 실행 결과를<br/>대화에 추가
        A->>L: 갱신된 대화를 바탕으로 다음 판단 요청
    end

    L-->>A: 사용자에게 전달할 응답
    A-->>U: 응답 전달
```

- LLM은 어떤 도구를 호출할지 판단하여 도구 호출 요청을 생성합니다. 에이전트는 LLM에게 받은 요청을 분석하여 해당 도구를 실행하고, 실행 결과를 다시 LLM에게 전달하여 최종 응답을 생성하도록 합니다.