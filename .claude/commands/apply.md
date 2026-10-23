---
description: 공고를 분석해 강조 전략, 맞춤 경력기술서, 자소서 초안, 교정, 글자수 검증, Notion까지 진행한다
argument-hint: [지원 폴더 이름 | 공고ID | 공고 URL | 공고 원문] [--from <단계>]
---

# /apply

인자: $ARGUMENTS

## 0. 준비
1. `uv run career-ai config`로 데이터 폴더(`DATA`)를 확인한다. 오류면 메시지를 보여 주고 멈춘다.
2. 인자 해석:
   - 첫 인자가 `DATA/applications/` 아래 폴더 이름이면 그 폴더(`APP`)에서 이어서 한다.
   - `--from <단계>`가 있으면 그 단계부터 결과 파일이 있어도 다시 만든다.
   - 인자가 없으면 공고 수집 확장 스킬이 있으면 그 스킬의 목록 추천을 따르고, 없으면 "공고 원문을 붙여넣어 주세요"라고 요청한다.
   - 첫 인자가 `/jobs-search`의 공고ID(`saramin-...`, `work24-...`)면 `DATA/applications/_inbox/*.json`에서 그 공고를 찾아 회사, 제목, URL, 마감일, 플랫폼을 가져오고, 본문은 아래 URL 방식으로 읽는다.
   - **공고 수집 확장 스킬**(`.claude/skills/*-source/SKILL.md`, 개인 환경에만 있음)이 있고 인자가 그 스킬이 다루는 형태(특정 채용 플랫폼 URL, 회사명, 인자 없음)면 그 스킬의 절차로 공고 원문·공고 이미지·문항을 받은 뒤 아래 단계로 이어 간다.
   - 첫 인자가 그 밖의 URL이면 `uv run career-ai fetch <URL>`로 본문을 읽는다. `posting_text`를 공고 원문으로 쓴다. `error: login_wall`이거나 본문이 공고로 보이지 않으면 공고 원문을 붙여넣어 달라고 요청한다.

**공고 이미지 읽기 규칙:** 공고 상세가 이미지 파일(`posting-images/` 또는 수집 결과의 `image_files`)로만 있으면 Read 도구로 조각 이미지를 순서대로 모두 열어 읽는다. 여러 직무를 함께 뽑는 공고면 고른 직무 부분만 골라낸다. 정리 형식: `주요 업무`, `자격 요건`, `우대 사항`, `근무지·근무 형태`, `전형 절차`, `제출 서류`. 이미지에 없는 항목은 "공고에 없음"이라고 쓰고 지어내지 않는다.

3. 단계 이름과 결과 파일. 결과 파일이 이미 있으면 그 단계는 건너뛴다(`--from` 이후 단계 제외).

| 단계 | 결과 파일 |
|---|---|
| `posting` | `posting.md` |
| `analysis` | `analysis.md` |
| `questions` | `questions.json` |
| `career` | `career.md` |
| `draft` | `drafts/q{id}_v{k}.md` (문항마다 하나 이상) |
| `humanize` | `drafts/q{id}_final.md` (문항마다) |
| `count` | `final.md` |

예외: 어떤 문항의 최신 `drafts/q{id}_v{k}.md`가 `drafts/q{id}_final.md`보다 새 파일이면, 그 문항은 `humanize`부터 다시 한다(초안을 고친 뒤 예전 교정본으로 글자수를 재지 않도록).

## 1. posting
공고 원문(붙여넣기, `fetch` 결과, `_inbox` 정보)에서 회사, 직무(공고 제목), 마감일, 공고 URL, 플랫폼을 뽑는다. 없는 값은 사용자에게 묻되, 마감일과 URL은 "모름"을 허용한다.
- 공고ID: `_inbox`에서 왔으면 그 공고ID, 공고에 번호가 있으면 그것, 없으면 `manual-YYYYMMDD-HHMM`.
- `APP` = `DATA/applications/{회사}_{공고ID}` (회사명의 공백과 `/\:*?"<>|`는 제거).
- `posting.md`:
  ```markdown
  ---
  company: 
  title: 
  role:        # AI 엔지니어 | AX | 데이터 분석 | 데이터 사이언티스트 | 기타
  platform:    # 자소설닷컴 | 잡코리아 | 사람인 | 고용24 | 리멤버 | 캐치 | 기업 채용 사이트
  url: 
  deadline:    # YYYY-MM-DD 또는 빈 값
  posting_id: 
  ---

  (공고 원문 그대로)
  ```

## 2. analysis
`company-analysis` 스킬을 따른다.

**[확인 지점 ①]** 요약과 적합도를 보여 주고 "이대로 진행 / 수정 / 중단"을 묻는다. 수정 요청은 반영해 다시 저장한다.

## 3. questions
`question-extract` 스킬을 따른다.

## 4. career
`career-tailor` 스킬을 따른다.

## 5. draft
`questions.json`의 문항이 비어 있으면 건너뛴다. 아니면 `essay-draft` 스킬을 따른다.

**[확인 지점 ②]** 강조 전략, 맞춤 경력기술서, 문항별 초안(소재 배분 표 포함)을 보여 주고 "진행 / 수정 / 중단"을 묻는다. 초안 수정은 새 버전(`v{k+1}`)으로 저장한다.

## 6. humanize
`humanize-korean` 플러그인(im-not-ai)이 설치돼 있지 않으면 README의 설치 명령을 안내하고 멈춘다.

문항마다 최신 버전 `drafts/q{id}_v{k}.md`에 대해:
1. `uv run career-ai clean APP/drafts/q{id}_v{k}.md --out APP/drafts/q{id}_clean.md`
2. Skill 도구로 `humanize-korean` 스킬을 호출하고, `q{id}_clean.md`의 **본문 텍스트**를 입력으로 준다(이 스킬은 파일 경로가 아니라 텍스트를 받는다).
   - **기본은 항상 강하게:** 인자에 `--strict 정밀 모드, 강도: 적극, 장르: essay (자기소개서)`를 붙인다(사용자 결정, 2026-10-19: "AI 티가 많이 남는다"). 사용자가 "가볍게"라고 말한 경우에만 약하게 돌린다.
   - 이유: 스킬은 정량 점수가 낮으면(`route_hint: light`) 가장 약한 보수 강도로만 돌아 변경률이 0.5% 수준에 그친다. 정밀 모드는 진단 → 겨냥 윤문 → 마무리 점검 3콜로 돌고, 같은 글의 변경률이 20% 정도가 된다.
   - **함께 전달하는 지시문:** "사실·수치·고유명사·본인과 팀의 역할 구분·인과는 그대로 둔다. 원문에 없던 사실·장면·감정·원인을 새로 넣지 않는다. 쉼표로 절을 이어 붙인 복문, 모든 문장이 같은 종결어미로 끝나는 리듬, 추상 명사화('~의 부재', '~가능성 탐색'), 같은 주어 반복, 문단마다 같은 틀로 닫히는 구조를 고친다. 단, 문장을 너무 잘게 쪼개지 않는다(한 문단에 40자 미만 짧은 문장은 2~3개, 나머지는 50~80자, 긴 문장도 한 개쯤 남긴다). 쉼표를 0개로 만들지 말고 자연스러운 자리는 남긴다. 합쇼체를 유지한다."
   - 스킬 안내의 `python3` 명령이 이 PC에 없으면 `python`으로 바꿔 실행한다.
   - 시간과 사용량: 문항 하나에 약 5분, 에이전트 3콜이 든다. 문항이 많으면 시작 전에 "문항 N개, 약 N×5분 걸립니다"라고 알린다.
3. 결과는 저장소 루트의 `_workspace/{run_id}/final.md`에 생긴다. 이 파일은 끝에 `<!-- HUMANIZE-SUMMARY -->` 블록이 붙는다. 파일을 그대로 `APP/drafts/q{id}_final.md`로 복사(셸의 파일 복사 명령 사용)한 뒤 `uv run career-ai clean APP/drafts/q{id}_final.md --out APP/drafts/q{id}_final.md`를 실행한다. `clean`은 `<!-- HUMANIZE-SUMMARY`부터 끝까지와 근거 주석, BOM을 지운다.
4. 스킬이 변경률 초과로 `hold_and_report`를 내면 교정본을 쓰지 않는다. `q{id}_clean.md`를 `q{id}_final.md`로 복사하고 그 사실을 보고한다.
5. **사실 대조:** `q{id}_final.md`와 `q{id}_v{k}.md`를 비교해, 교정 과정에서 새로 생긴 수치·고유명사·사실이 없는지 확인한다. 있으면 그 부분을 `v{k}`의 표현으로 되돌린다.

`career.md`의 `### 경력 요약` 문단만 교정한다:
1. 그 문단 텍스트를 `humanize-korean` 스킬에 입력으로 준다(위 2번과 같은 설정: 정밀 모드 + 적극 + 지시문).
2. 결과 `final.md`에서 `<!-- HUMANIZE-SUMMARY` 앞의 본문만 가져온다.
3. 위 5번과 같이 원래 문단과 사실을 대조한다.
4. `career.md`에서 `### 경력 요약` 제목 아래 문단을 이 본문으로 바꾼다. 다른 부분은 건드리지 않는다.

## 7. count
`questions.json`의 문항이 비어 있으면 건너뛴다.
1. `uv run career-ai count APP`
2. `over`인 문항: 의미와 사실을 유지하며 `q{id}_final.md`를 줄이고 다시 센다. 줄일 때는 문장을 빼거나 짧게 할 뿐 새 내용을 넣지 않는다. 교정은 다시 돌리지 않는다. **두 번 줄여도 넘으면 멈추고** 현재 글자수와 본문을 보여 주며 사용자에게 맡긴다.
   `comment_left`인 문항: 닫히지 않은 주석 등 `<!--`/`-->`가 남은 것이다. 해당 부분을 지우고 다시 센다.
3. `under`인 문항: 경고만 한다.
4. `over`, `missing`, `comment_left`가 없으면 `uv run career-ai count APP --write-final`

## 8. 마무리
- 결과 요약: 폴더 경로, 문항별 글자수와 상태, `final.md`·`career.md` 경로.
- `uv run career-ai notion push APP`로 Notion에 저장하고, 결과의 `url`을 알려 준다.
  `config` 오류면 README의 'Notion 연결' 절을 안내하고, `notion` 오류면 메시지를 보여 준다. 어느 경우든 로컬 결과는 그대로 남는다고 알린다.
- 데이터 저장소에 커밋할지 묻는다. 승인하면 `DATA`에서 `git add applications/{폴더} && git commit -m "add: {회사} {직무}"`.
