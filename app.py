"""AI 면접 코치 — Streamlit 화면만. (프롬프트 문장 · API 직접 호출 없음)"""

import html
from pathlib import Path

import streamlit as st

import coach
import sources
from llm import LLMError, ask_json
from prompts import (
    EVAL_SCHEMA, EVALUATOR, INTERVIEWER, INTERVIEWER_SCHEMA, PERSONAS, POLISH, POLISH_SCHEMA,
    PREP, PREP_SCHEMA, RETRY, RETRY_SCHEMA, STAGE_FOLLOW, STAGE_MAIN,
)

st.set_page_config(page_title="AI 면접 코치", page_icon="🎤", layout="centered")
st.markdown(f"<style>{(Path(__file__).parent / 'ui' / 'style.css').read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True)

S = st.session_state
DEFAULTS = {
    "stage": "start",          # start → interview → interview_done → review
    "view": "평가",
    "profile": None, "context": "", "questions": [], "records": [], "messages": [],
    "qi": 0, "phase": "main", "follow_used": 0, "clarify_used": 0, "understanding": None,
    "evaluation": None, "retries": {}, "polish": None,
}
for k, v in DEFAULTS.items():
    if k not in S:
        S[k] = v.copy() if isinstance(v, (dict, list)) else v

VIEWS = ["평가", "재도전", "리포트"]
STEPS = ["시작", "면접", "평가", "재도전", "리포트"]
AVATAR = {"assistant": ":material/mic:", "user": ":material/person:"}
esc = html.escape


# ── 작은 화면 조각 ───────────────────────────
def md(s: str):
    st.markdown(s, unsafe_allow_html=True)


def head(label: str, title: str, lead: str = ""):
    md(f'<div class="eyebrow">{label}</div><div class="section-title">{title}</div>'
       + (f'<p class="lead">{lead}</p>' if lead else "") + '<div class="spacer"></div>')


def block_head(label: str, title: str):
    md(f'<div class="block-label">{label}</div><div class="block-title">{title}</div>')


def steps():
    if S.stage == "start":
        cur = 0
    elif S.stage in ("interview", "interview_done"):
        cur = 1
    else:
        cur = 2 + VIEWS.index(S.view or "평가")
    md('<div class="steps">' + "".join(
        f'<span class="{"on" if i == cur else "done" if i < cur else ""}">{i + 1:02d} {s}</span>'
        for i, s in enumerate(STEPS)) + "</div>")


def highlight(text: str) -> str:
    """[확인 필요: ○○] 를 파란 밑줄로."""
    return coach.UNVERIFIED.sub(lambda m: f'<span class="verify">{m.group(0)}</span>', esc(text)).replace("\n", "<br>")


def bars(scores: dict) -> str:
    rows = "".join(
        f'<div class="bar-row"><span class="name">{label}</span>'
        f'<div class="bar"><i style="width:{scores[k] * 20}%"></i></div><span class="num">{scores[k]}/5</span></div>'
        for k, label in coach.CRITERIA)
    return f'<div class="bars">{rows}</div>'


def call_ai(spinner: str, instructions: str, user_input: str, schema: dict, name: str, for_eval=False):
    try:
        with st.spinner(spinner):
            return ask_json(instructions, user_input, schema, name, for_eval=for_eval)
    except LLMError as e:
        st.error(str(e))
        return None


def reset():
    for k in list(S.keys()):
        del S[k]


def go(view: str):
    S.view = view


# ── 📟 상태창 ───────────────────────────────
def sidebar():
    with st.sidebar:
        md('<div class="eyebrow">📟 상태창</div>')
        if not S.profile:
            md('<p class="muted" style="font-size:14px">직군 · 회사 · 경험을 넣으면 면접이 시작돼요.</p>')
        else:
            p = S.profile
            md(f'<div class="side-company">{esc(p["company"])}</div>'
               f'<p class="muted" style="font-size:13px;margin:0 0 22px">{p["job"]} 신입 · {PERSONAS[p["job"]]["name"]}</p>')

            done = S.qi if S.stage == "interview" else coach.TOTAL_QUESTIONS
            now = min(S.qi + 1, coach.TOTAL_QUESTIONS)
            label = f"질문 {now}/{coach.TOTAL_QUESTIONS}" if S.stage == "interview" else "면접 완료"
            st.progress(done / coach.TOTAL_QUESTIONS, text=label)

            u = "–" if S.understanding is None else S.understanding
            md(f'<div class="block-label" style="margin-top:18px">면접관이 본 이해도</div>'
               f'<div class="side-big">{u}<small> / 100</small></div>')

            rows = []
            if S.stage == "interview":
                phase = "본 질문" if S.phase == "main" else f"꼬리 질문 {S.follow_used}/{coach.MAX_FOLLOW_UPS}"
                rows += [("지금", phase), ("남은 질문", f"{coach.TOTAL_QUESTIONS - S.qi - 1}개")]
            if S.evaluation:
                ev = S.evaluation
                rows += [("위원 평균", f"{ev['panel_avg']} / 10"), ("답변 평균", f"{ev['answer_avg']} / 20"),
                         ("재도전", f"{len(S.retries)} / {len(coach.retry_targets(ev['answers']))}")]
            md('<div style="margin-top:22px">' + "".join(
                f'<div class="side-row"><span class="k">{k}</span><span>{v}</span></div>' for k, v in rows) + "</div>")

        st.write("")
        st.button("처음부터 다시", on_click=reset, width="stretch")


# ── ① 시작 ─────────────────────────────────
def view_start():
    md('<div class="eyebrow">AI INTERVIEW COACH</div>'
       '<h1 class="hero-title">연습한 만큼,<br>면접이 늘어요.</h1>'
       '<p class="lead">직군 · 공고 · 내 경험을 넣으면 면접관이 다섯 문제를 묻고, 위원 네 명이 평가해요. '
       '고친 답으로 다시 답하면 점수가 얼마나 올랐는지 숫자로 보여 드려요.</p><div class="spacer"></div>')

    with st.container(key="card-job"):
        block_head("01", "어떤 직군으로 지원하나요?")
        job = st.segmented_control("직군", list(PERSONAS), key="in_job", label_visibility="collapsed")
        if job:
            p = PERSONAS[job]
            md(f'<p class="muted" style="font-size:14px;margin:12px 0 0">'
               f'<span class="tag">{p["name"]}</span>{esc(p["title"])}</p>')

    with st.container(key="card-company"):
        block_head("02", "회사와 채용공고")
        st.text_input("회사 이름", key="in_company", placeholder="예: 클래스로")
        st.text_area("채용공고 붙여넣기", key="in_posting", height=140,
                     placeholder="담당 업무 · 자격 요건 · 우대 사항을 그대로 붙여 넣으면 가장 정확해요.")
        st.file_uploader("공고 파일 (선택)", type=["pdf", "docx", "txt", "md"], key="in_posting_file")
        st.text_input("공고 · 회사 링크 (선택)", key="in_url", placeholder="https://")
        st.caption("채용 사이트는 로그인 · 동적 페이지라 링크를 못 읽을 때가 많아요. 붙여넣기를 추천해요.")

    with st.container(key="card-exp"):
        block_head("03", "내 경험")
        st.file_uploader("자기소개서 · 포트폴리오 (선택, 여러 개)", type=["pdf", "docx", "txt", "md"],
                         accept_multiple_files=True, key="in_exp_files")
        st.text_area("직접 적기", key="in_exp", height=140,
                     placeholder="프로젝트 · 맡은 일 · 결과(숫자) 위주로 적어 주세요. 실제 개인정보는 빼고요.")

    md('<div class="spacer"></div>')
    if st.button("면접 시작하기", type="primary", width="stretch"):
        start_interview()


def start_interview():
    job, company = S.get("in_job"), (S.get("in_company") or "").strip()
    problems = []
    if not job:
        problems.append("직군을 골라 주세요.")
    if not company:
        problems.append("회사 이름을 적어 주세요.")

    posting = [S.get("in_posting") or ""]
    if S.get("in_posting_file"):
        try:
            posting.append(sources.read_upload(S.in_posting_file))
        except Exception:
            st.warning("공고 파일을 읽지 못했어요. 내용을 붙여 넣어 주세요.")
    if (S.get("in_url") or "").strip():
        text, err = sources.fetch_url(S.in_url)
        if err:
            st.warning(err)
        posting.append(text)

    experience = [S.get("in_exp") or ""]
    for f in S.get("in_exp_files") or []:
        try:
            experience.append(sources.read_upload(f))
        except Exception:
            st.warning(f"{f.name} 파일을 읽지 못했어요.")
    posting_text = "\n\n".join(p.strip() for p in posting if p.strip())
    experience_text = "\n\n".join(e.strip() for e in experience if e.strip())
    if len(experience_text) < coach.MIN_EXPERIENCE:
        problems.append(f"내 경험을 {coach.MIN_EXPERIENCE}자 이상 적거나 파일을 올려 주세요.")

    if problems:
        for p in problems:
            st.warning(p)
        return

    prep_input = (f"[채용공고 원문]\n{coach.clip(posting_text) or '없음'}\n\n"
                  f"[지원자 경험 원문]\n{coach.clip(experience_text)}")
    res = call_ai("공고와 경험을 읽고 나만의 질문을 만들고 있어요…",
                  PREP.format(company=company, job=job),
                  prep_input, PREP_SCHEMA, "interview_prep")
    if res is None:
        return
    questions = coach.build_questions(res["questions"])
    if questions is None:
        st.error("질문 5개를 다 만들지 못했어요. '면접 시작하기'를 한 번 더 눌러 주세요.")
        return

    S.questions = questions
    S.profile = {"job": job, "company": company,
                 "posting_summary": res["posting_summary"], "experience_facts": res["experience_facts"]}
    S.context = coach.build_context(company, job, res["posting_summary"] or posting_text, experience_text)
    S.records = [{"no": q["no"], "question": q["question"], "point": q["point"],
                  "answer": "", "follow_q": "", "follow_a": ""} for q in S.questions]
    persona = PERSONAS[job]
    S.messages = [{"role": "assistant", "label": persona["title"],
                   "content": f"안녕하세요, {persona['name']}입니다. 오늘은 질문 {coach.TOTAL_QUESTIONS}개를 드릴게요. "
                              "질문 뜻이 헷갈리면 편하게 되물어 보셔도 돼요."}]
    S.qi, S.phase, S.follow_used, S.clarify_used, S.understanding = 0, "main", 0, 0, None
    S.stage = "interview"
    ask_current_question()
    st.rerun()


# ── ② 면접 ─────────────────────────────────
def ask_current_question():
    q = S.questions[S.qi]
    S.messages.append({"role": "assistant", "label": f"질문 {q['no']}/{coach.TOTAL_QUESTIONS} · {q['type']}",
                       "content": f"**{q['question']}**"})


def next_question():
    S.qi += 1
    S.phase, S.follow_used, S.clarify_used = "main", 0, 0
    if S.qi < coach.TOTAL_QUESTIONS:
        ask_current_question()
    else:
        S.stage = "interview_done"
        S.messages.append({"role": "assistant", "label": "면접 끝",
                           "content": "여기까지입니다. 수고하셨어요. 이제 위원 네 명이 답변을 평가할게요."})


def render_message(m: dict):
    with st.chat_message(m["role"], avatar=AVATAR[m["role"]]):
        if m.get("label"):
            md(f'<div class="msg-label">{esc(m["label"])}</div>')
        st.markdown(m["content"])


def handle_answer(text: str):
    text = text.strip()
    if not text:
        return
    q, rec = S.questions[S.qi], S.records[S.qi]
    msg = {"role": "user", "content": text}
    render_message(msg)

    if S.phase == "main":
        stage, user_input = STAGE_MAIN, f"[지원자의 답]\n{text}"
    else:
        stage, user_input = STAGE_FOLLOW, f"[꼬리 질문]\n{rec['follow_q']}\n\n[지원자의 답]\n{text}"
    instructions = INTERVIEWER.format(persona=PERSONAS[S.profile["job"]]["persona"], context=S.context,
                                      question=q["question"], point=q["point"], stage=stage)
    res = call_ai("면접관이 답을 듣고 있어요…", instructions, user_input, INTERVIEWER_SCHEMA, "interviewer")
    if res is None:
        return

    S.messages.append(msg)
    S.understanding = coach.clamp(res["understanding"], 0, 100)
    reaction = res["reaction"].strip()

    # 되묻기: 답으로 세지 않고 같은 질문을 쉬운 말로 (질문당 MAX_CLARIFY 번까지)
    if res["is_clarification"] and S.clarify_used < coach.MAX_CLARIFY:
        S.clarify_used += 1
        S.messages.append({"role": "assistant", "label": "다시 여쭤볼게요", "content": reaction})
        st.rerun()

    if S.phase == "main":
        rec["answer"] = text
        follow = res["follow_up"].strip()
        # 꼬리 질문 횟수는 코드가 정한다 — AI가 더 묻자고 해도 MAX_FOLLOW_UPS 에서 막힘
        if follow and S.follow_used < coach.MAX_FOLLOW_UPS:
            S.follow_used += 1
            rec["follow_q"] = follow
            S.phase = "follow"
            S.messages.append({"role": "assistant", "label": "꼬리 질문",
                               "content": (f"{reaction}\n\n" if reaction else "") + f"**{follow}**"})
        else:
            if reaction:
                S.messages.append({"role": "assistant", "content": reaction})
            next_question()
    else:
        rec["follow_a"] = text
        if reaction:
            S.messages.append({"role": "assistant", "content": reaction})
        next_question()
    st.rerun()


def view_interview():
    p = S.profile
    persona = PERSONAS[p["job"]]
    head("02 면접", persona["name"], f"{persona['title']} · 한 번에 질문 하나, 질문마다 꼬리 질문 하나.")

    with st.expander("면접관이 읽은 내 정보"):
        if p["posting_summary"]:
            md('<div class="block-label">공고에서 본 요구</div>')
            st.markdown("\n".join(f"- {s}" for s in p["posting_summary"]))
        md('<div class="block-label">내 경험에서 본 사실</div>')
        st.markdown("\n".join(f"- {s}" for s in p["experience_facts"]) or "-")

    for m in S.messages:
        render_message(m)

    if S.stage == "interview":
        answer = st.chat_input("답변을 입력하세요")
        if answer:
            handle_answer(answer)
    else:
        md('<div class="spacer"></div>')
        if st.button("위원 4명에게 평가받기", type="primary", width="stretch"):
            run_evaluation()


def run_evaluation():
    res = call_ai("위원 네 명이 따로 평가하고 있어요…", EVALUATOR.format(context=S.context),
                  coach.transcript(S.records), EVAL_SCHEMA, "panel_eval", for_eval=True)
    if res is None:
        return
    S.evaluation = coach.normalize_eval(res, S.records)
    S.stage, S.view = "review", "평가"
    st.rerun()


# ── ③ 평가 ─────────────────────────────────
def view_eval():
    ev = S.evaluation
    low = coach.retry_targets(ev["answers"])
    head("03 평가", "위원 네 명의 평가", "위원마다 반론을 먼저 듣고, 점수 합계와 평균은 코드가 계산했어요.")

    md('<div class="grid three">'
       f'<div class="tile"><div class="k">위원 평균</div><div class="v">{ev["panel_avg"]}<small>/10</small></div></div>'
       f'<div class="tile"><div class="k">답변 평균</div><div class="v">{ev["answer_avg"]}<small>/20</small></div></div>'
       f'<div class="tile"><div class="k">고칠 답 (기준 {coach.PASS_SCORE}점 미만)</div>'
       f'<div class="v">{len(low)}<small>개</small></div></div></div>')

    md('<div class="grid">' + "".join(
        f'<div class="tile"><div class="role"><b>{p["role"]}</b><span>{p["score"]}<small> /10</small></span></div>'
        f'<div class="lbl">뽑지 말아야 할 이유</div><p>{esc(p["against"])}</p>'
        f'<div class="lbl">좋은 점</div><p>{esc(p["good"])}</p></div>'
        for p in ev["panel"]) + "</div>")

    with st.container(key="card-panel-sum"):
        md(f'<div class="row-note"><span class="k">갈린 곳</span><span>{esc(ev["conflict"])}</span></div>'
           f'<div class="row-note"><span class="k">같은 판단</span><span>{esc(ev["agree"])}</span></div>')

    md('<div class="spacer"></div>')
    block_head("답변별", "질문마다 점수와 고친 답")
    for a in ev["answers"]:
        state = "고친 답 있음" if coach.needs_rewrite(a) else "통과"
        with st.expander(f"Q{a['no']}  ·  {a['total']}/20  ·  {state}"):
            md(f'<p style="margin:0 0 8px"><b style="font-weight:500">{esc(a["question"])}</b></p>' + bars(a)
               + f'<div class="row-note"><span class="k">약한 점</span><span>{esc(a["weak"])}</span></div>')
            if coach.needs_rewrite(a):
                md(f'<div class="block-label" style="margin-top:14px">고친 답</div>'
                   f'<div class="quote">{highlight(a["rewrite"])}</div>')
                if coach.count_unverified(a["rewrite"]):
                    st.caption("파란 밑줄 [확인 필요]는 내 자료에 없던 내용이에요. 실제 사실로 채우거나 빼세요.")
                if a["check"]:
                    md('<div class="block-label">사람이 확인할 것</div>')
                    st.markdown("\n".join(f"- {c}" for c in a["check"]))
            else:
                st.caption(f"기준 {coach.PASS_SCORE}점 이상이라 고친 답은 생략했어요.")

    if ev["next"]:
        with st.container(key="card-next"):
            block_head("다음 연습", "다음에 고칠 것 세 가지")
            st.markdown("\n".join(f"{i}. {n}" for i, n in enumerate(ev["next"], 1)))

    with st.expander("면접 기록 다시 보기"):
        st.text(coach.transcript(S.records))

    md('<div class="spacer"></div>')
    st.button("재도전하러 가기" if low else "리포트 보기", type="primary", width="stretch",
              on_click=go, args=("재도전" if low else "리포트",))


# ── ④ 재도전 ───────────────────────────────
def view_retry():
    ev = S.evaluation
    targets = coach.retry_targets(ev["answers"])
    head("04 재도전", "고친 답을 참고해, 내 말로 다시",
         f"기준 {coach.PASS_SCORE}점 미만인 답만 점수 낮은 순으로 모았어요. 같은 기준으로 다시 채점해요.")

    if not targets:
        st.success(f"모든 답이 {coach.PASS_SCORE}점 이상이에요. 재도전할 답이 없어요.")
        st.button("리포트 보기", type="primary", width="stretch", on_click=go, args=("리포트",))
        return

    for a in targets:
        r = S.retries.get(a["no"])
        with st.container(key=f"card-retry-{a['no']}"):
            md(f'<div class="block-label">Q{a["no"]} · 지난 점수 {a["total"]}/20</div>'
               f'<div class="block-title">{esc(a["question"])}</div>'
               f'<div class="row-note"><span class="k">약한 점</span><span>{esc(a["weak"])}</span></div>')
            with st.expander("고친 답 참고"):
                md(f'<div class="quote">{highlight(a["rewrite"])}</div>')
            st.text_area("다시 답하기", key=f"retry_{a['no']}", height=150,
                         placeholder="상황 → 행동 → 결과 순서로, 내가 실제로 한 일만.")
            if st.button("다시 채점", key=f"btn_retry_{a['no']}", width="stretch"):
                rescore(a)
            if r:
                c = coach.compare(a, r["scores"])
                delta_cls = "" if c["delta"] > 0 else " down"
                md(f'<div class="compare" style="margin-top:14px"><span class="from">{c["before"]}</span>'
                   f'<span class="arrow">→</span><span class="to">{c["after"]}</span>'
                   f'<span class="delta{delta_cls}">{c["delta"]:+d}점</span></div>'
                   '<table class="mini"><tr><th>기준</th><th>전</th><th>후</th><th>차이</th></tr>' + "".join(
                       f'<tr><td>{row["기준"]}</td><td>{row["전"]}</td><td>{row["후"]}</td>'
                       f'<td class="{"up" if row["차이"] > 0 else ""}">{row["차이"]:+d}</td></tr>'
                       for row in c["rows"]) + "</table>"
                   f'<div class="row-note" style="margin-top:8px"><span class="k">남은 약점</span>'
                   f'<span>{esc(r["weak"])}</span></div>')

    left = len(targets) - len([a for a in targets if a["no"] in S.retries])
    md('<div class="spacer"></div>')
    if left:
        st.caption(f"{left}개 남았어요. 모두 다시 답하면 전 → 후 비교가 나와요.")
        return

    s = coach.retry_summary(ev["answers"], S.retries)
    with st.container(key="card-retry-sum"):
        block_head("전 → 후", f"재도전 {s['count']}개, 평균 점수")
        md(f'<div class="compare"><span class="from">{s["before"]}</span><span class="arrow">→</span>'
           f'<span class="to">{s["after"]}</span><span class="delta{"" if s["delta"] > 0 else " down"}">'
           f'{s["delta"]:+.1f}점</span></div>'
           '<table class="mini" style="margin-top:14px"><tr><th>질문</th><th>전</th><th>후</th><th>차이</th></tr>'
           + "".join(f'<tr><td>Q{a["no"]}</td><td>{a["total"]}</td><td>{S.retries[a["no"]]["scores"]["total"]}</td>'
                     f'<td class="{"up" if S.retries[a["no"]]["scores"]["total"] > a["total"] else ""}">'
                     f'{S.retries[a["no"]]["scores"]["total"] - a["total"]:+d}</td></tr>' for a in targets)
           + "</table>")
    st.button("리포트 보기", type="primary", width="stretch", on_click=go, args=("리포트",))


def rescore(a: dict):
    text = (S.get(f"retry_{a['no']}") or "").strip()
    if not text:
        st.warning("다시 답할 내용을 먼저 적어 주세요.")
        return
    rec = next(r for r in S.records if r["no"] == a["no"])
    user_input = f"[질문]\n{rec['question']}\n\n[보는 점]\n{rec['point']}\n\n[지원자의 답]\n{text}"
    res = call_ai("같은 기준으로 다시 채점하고 있어요…", RETRY.format(context=S.context), user_input,
                  RETRY_SCHEMA, "retry_score", for_eval=True)
    if res is None:
        return
    S.retries[a["no"]] = {"answer": text, "scores": coach.criteria_scores(res), "weak": res["weak"]}
    st.rerun()


# ── ⑤ 리포트 ───────────────────────────────
def view_report():
    ev = S.evaluation
    head("05 리포트", "마지막 질문 다듬기와 리포트", "숫자는 모두 코드가 계산한 값이에요.")

    with st.container(key="card-polish"):
        block_head("⑨ 질문 다듬기", "“마지막으로 궁금한 점 있나요?”")
        st.text_area("면접관에게 하고 싶은 질문", key="in_polish", height=90,
                     placeholder="예: 신입은 입사하면 어떤 일을 하나요?")
        if st.button("질문 다듬기", width="stretch"):
            polish()
        if S.polish:
            rows = "".join(
                f'<tr><td><span class="tag">{q["angle"]}</span></td><td>{esc(q["question"])}</td>'
                f'<td style="text-align:right;white-space:nowrap" class="{"" if q["over"] else "muted"}">'
                f'{q["length"]}자{" · 초과" if q["over"] else ""}</td></tr>'
                for q in S.polish["questions"])
            md(f'<table class="mini" style="margin-top:14px">{rows}</table>'
               f'<div class="row-note" style="margin-top:6px"><span class="k">빠진 것</span>'
               f'<span>{esc(S.polish["why"])}</span></div>')
            if any(q["over"] for q in S.polish["questions"]):
                st.caption(f"{coach.POLISH_LIMIT}자를 넘은 질문은 소리 내어 말하기 길어요. 한 번 더 줄여 보세요.")

    report = coach.build_report(S.profile, ev, S.retries, S.polish)
    with st.container(key="card-report"):
        block_head("면접 리포트", f'{esc(S.profile["company"])} · {S.profile["job"]} 신입')
        s = coach.retry_summary(ev["answers"], S.retries)
        md(f'<div class="stars">{coach.stars(ev["answer_avg"])}</div>'
           f'<div class="row-note" style="margin-top:12px"><span class="k">위원 평균</span><span>{ev["panel_avg"]} / 10</span></div>'
           f'<div class="row-note"><span class="k">답변 평균</span><span>{ev["answer_avg"]} / 20</span></div>'
           + (f'<div class="row-note"><span class="k">재도전</span><span>{s["count"]}개 · '
              f'{s["before"]} → {s["after"]} ({s["delta"]:+.1f})</span></div>' if s["count"] else ""))
        with st.expander("리포트 미리보기"):
            st.markdown(report)
        st.download_button("면접리포트.md 내려받기", report, file_name="면접리포트.md",
                           mime="text/markdown", type="primary", width="stretch")


def polish():
    text = (S.get("in_polish") or "").strip()
    if not text:
        st.warning("다듬을 질문을 먼저 적어 주세요.")
        return
    res = call_ai("질문을 다듬고 있어요…", POLISH.format(context=S.context), f"[원래 질문]\n{text}",
                  POLISH_SCHEMA, "polish_question")
    if res is None:
        return
    S.polish = {"original": text, "questions": coach.check_polish(res["questions"][:3]), "why": res["why"]}
    st.rerun()


# ── 화면 고르기 ─────────────────────────────
sidebar()
steps()
if S.stage == "start":
    view_start()
elif S.stage in ("interview", "interview_done"):
    view_interview()
else:
    st.segmented_control("보기", VIEWS, key="view", label_visibility="collapsed")
    md('<div class="spacer"></div>')
    {"평가": view_eval, "재도전": view_retry, "리포트": view_report}.get(S.view or "평가", view_eval)()
