---
description: 내가 쓴 자소서 한 문항을 채용 담당자 관점으로 평가하고, 대화하며 빠르게 첨삭한다
argument-hint: <지원 폴더 이름 | 회사명> [문항 번호] [초안 파일 경로 | 붙여넣은 초안]
---

# /review

인자: $ARGUMENTS

## 0. 준비
1. `uv run career-ai config`로 데이터 폴더(`DATA`)를 확인한다. 오류면 메시지를 보여 주고 멈춘다.
2. 지원 폴더(`APP`): 첫 인자가 `DATA/applications/` 아래 폴더 이름이면 그 폴더를 쓴다. 회사명이면 이름에 그 회사명이 들어간 폴더를 찾는다. 여러 개면 고르게 하고, 없으면 "먼저 `/apply`로 공고를 등록해 주세요"라고 안내하고 멈춘다.
3. `APP`에 `posting.md`, `analysis.md`, `questions.json`이 없으면 `/apply {폴더} `로 그 단계까지 만들라고 안내하고 멈춘다. `/review`는 분석을 다시 돌리지 않는다.
4. 문항(`id`): 인자에 번호가 있으면 쓰고, 없으면 초안 내용으로 추정해 확인받는다. 문항이 하나뿐이면 그 문항이다.
5. 초안. 아래 순서로 찾고, 어느 것을 썼는지 알린다.
   1. 붙여넣은 텍스트
   2. 인자로 준 파일
   3. `drafts/q{id}_final.md`
   4. 최신 `drafts/q{id}_v{k}.md`
6. 작업 파일:
   - 시작본을 제목 줄까지 그대로 `drafts/q{id}_v{k+1}.md`로 저장한다(`k`는 지금 있는 가장 큰 버전 번호). 기록용이라 이후 고치지 않는다. 시작본이 최신 `v{k}`와 같으면 새로 저장하지 않는다.
   - 같은 내용을 작업본 `drafts/q{id}_review.md`로 복사한다.

## 1. 첫 피드백
`essay-review` 스킬의 첫 피드백 형식으로 평가한다.

## 2. 첨삭 대화
`essay-review` 스킬의 첨삭 대화 규칙을 따른다. 사용자가 "확정", "끝"처럼 마무리를 말할 때까지 이어 간다.

## 3. 마무리
1. 작업본이 시작본과 다르면 새 버전 `drafts/q{id}_v{k+2}.md`로 저장한다.
2. 최종본 만들기:
   - 사용자가 교정을 요청했으면 `/apply`의 6단계(humanize) 절차로 작업본을 교정해 `drafts/q{id}_final.md`를 만든다. 강도는 사용자가 말한 대로 한다.
   - 요청하지 않았으면 `uv run career-ai clean APP/drafts/q{id}_review.md --out APP/drafts/q{id}_final.md`.
   - 버전 파일을 먼저 쓰고 최종본을 나중에 써야 한다. 최종본이 더 새 파일이어야 `/apply`를 다시 돌렸을 때 이 문항을 교정부터 다시 하지 않는다.
3. `uv run career-ai count APP`. 이 문항이 `no_title`이면 본문에 맞는 `[제목]`을 첫 줄에 붙여 사용자 확인을 받고 다시 센다. `under`(제한보다 30자 넘게 빔)이면 `essay-draft`의 "채우는 법"으로 보강안을 보여 주고 승인받는다. `over`, `missing`, `comment_left`, `no_title`가 없으면 `uv run career-ai count APP --write-final`로 `final.md`를 갱신한다. 다른 문항이 아직 없으면(`missing`) 그 사실만 알린다.
4. 작업본 `drafts/q{id}_review.md`를 지운다.
5. 사용자에게 차례로 묻는다.
   - 대화 중에 나온 새 사실을 경험 뱅크에 추가할지. 승인한 것만 추가한다.
   - Notion에 반영할지. 승인하면 `uv run career-ai notion push APP`를 실행한다.
   - 데이터 저장소에 커밋할지. 승인하면 `DATA`에서 `git add applications/{폴더} experience && git commit -m "update: {회사} q{id} 첨삭"`을 실행한다.
