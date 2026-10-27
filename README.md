# 🎤 AI 면접 코치

직군 · 회사 · 내 경험을 넣으면 면접관이 5문제(질문마다 꼬리 질문 1개)를 묻고, 위원 4명이 평가하고, 고친 답을 참고해 다시 답하면 점수가 얼마나 올랐는지 보여 주는 Streamlit 서비스.

## 실행
```bash
pip install -r requirements.txt
# .env 를 직접 만들기 (.env.example 참고)
#   OPENAI_API_KEY=sk-...
#   OPENAI_MODEL=gpt-6-luna
streamlit run app.py
```

## 흐름과 기법
| 화면 | 기법 | 누가 |
| --- | --- | --- |
| ① 시작: 직군 · 회사 · 공고(붙여넣기/파일/링크) · 내 경험(파일/글) | ⑭ 컨텍스트 블록 | `PREP` · `CONTEXT` |
| ② 면접: 질문 하나씩 · 꼬리 질문 1개 · 📟 상태창 | ⑧ 게임 플레이 · ③ 페르소나 · ⑤ 숫자 규칙 | `INTERVIEWER` / 횟수는 코드 |
| ③ 평가: 위원 4명 · 반론 먼저 · 점수 | ⑮ 다중 관점 · ⑯ 심사숙고 | `EVALUATOR` / 합계는 코드 |
| ④ 고친 답 · [확인 필요] (14점 미만만) | ⑫ 리플렉션 · ⑩ 팩트 체크 | `EVALUATOR` |
| ⑤ 재도전: 전 → 후 점수 | BAB · 숫자로 증명 | `RETRY` / 비교는 코드 |
| ⑥ 마지막 질문 다듬기 · 리포트(★) | ⑨ 질문 개선 | `POLISH` / 리포트는 코드 |

## 파일
| 파일 | 하는 일 |
| --- | --- |
| `prompts.py` | 프롬프트 문장 · JSON 스키마 (✍️ 내가 쓰는 곳) |
| `llm.py` | OpenAI 호출 한 곳 `ask_json()` |
| `coach.py` | 질문 고르기 · 점수 합계 · 비교 · 리포트 (AI 없이) |
| `sources.py` | 업로드 파일(pdf/docx/txt) · 링크에서 글자 뽑기 |
| `app.py` | Streamlit 화면 |
| `ui/style.css` | 디자인 (Augen Pro 톤 · Pretendard) |
| `data/questions.csv` | 질문 은행 36개 (지금은 쓰지 않음 — 질문은 AI가 공고 · 경험으로 생성) |
