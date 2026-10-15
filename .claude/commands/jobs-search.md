---
description: 사람인·고용24에서 공고를 찾아 내 필수 조건으로 거르고, 선호 조건으로 점수를 매겨 표로 보여 준다
argument-hint: <키워드...> [--since 7d]  (비우면 preferences.yaml의 roles로 검색)
---

# /jobs-search

인자: $ARGUMENTS

## 1. 검색
1. `uv run career-ai config`로 데이터 폴더(`DATA`)를 확인한다. 오류면 메시지를 보여 주고 멈춘다.
2. 키워드가 없으면 `DATA/preferences.yaml`의 `roles`를 하나씩 검색한다. `--since`가 없으면 `7d`.
3. `uv run career-ai search <키워드...> --since <기간>`
   - `skipped`가 있으면 어떤 수집원이 왜 빠졌는지 알린다(키 없음이면 README의 'API 키' 절 안내).
   - 결과는 `inbox` 파일에 저장된다. 같은 날 다시 검색하면 합쳐진다.

## 2. 필수 조건 거르기
`uv run career-ai filter <inbox 파일 이름>`
- 다른 조건을 통과한 공고마다 기업 규모를 조회하므로 시간이 걸릴 수 있다. 조회 결과는 `DATA/companies/`에 90일 동안 저장된다.
- `company_info`에 `candidates`가 있으면 회사가 하나로 정해지지 않은 것이다. 표에는 "확인 필요"로 두고, 사용자가 원하면 후보를 보여 주고 `uv run career-ai company <회사> --corp-code <고유번호>`(또는 `--nps-seq`)로 확정한 뒤 다시 거른다.

## 3. 선호 조건 점수
통과한 공고마다 `preferences.yaml`의 `soft`와 `keywords_include`, `experience_years`로 점수를 매긴다. 공고 제목, `keywords`, `industry`, `company_info`만 근거로 쓰고, 모르는 항목은 0점으로 두고 "정보 없음"이라고 적는다.
- 항목: `ai_investment`(공고·업종에서 보이는 AI 투자 의지), `tech_match`(키워드·제목과 `keywords_include`, 경험 뱅크 기술 스택의 겹침), `industry`(`industries_prefer`면 높게, `industries_avoid`면 0), `salary`(연봉 하한 대비 여유)
- 항목마다 0~5점, `weights`로 가중 평균해 100점 만점으로 바꾼다.
- 기술 스택은 `DATA/experience/profile.md`에서 본다.

## 4. 결과
점수 높은 순으로 표를 보여 준다.

| 순위 | 공고ID | 회사 | 제목 | 규모 | 지역 | 연봉 | 마감 | 점수 | 근거 | 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|

- 근거는 한 줄로 쓴다(예: "LLM·RAG 키워드 일치, 금융업").
- 확인 필요 칸에는 `unknown` 목록을 쓴다.
- 표 아래에 제외된 공고 수와 이유별 개수를 요약한다(예: "제외 23건 — 지역 12, 고용 형태 6, 기업 규모 5").
- 마지막에 "지원할 공고는 `/apply <공고ID>`로 시작하세요"라고 안내한다.
