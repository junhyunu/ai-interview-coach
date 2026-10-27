"""질문 고르기 · 점수 합계 · 비교 · 리포트. AI 없이 코드가 계산한다."""

import re
from datetime import date

from prompts import CONTEXT, PANEL

TOTAL_QUESTIONS = 5
MAX_FOLLOW_UPS = 1   # 질문당 꼬리 질문 최대 개수 — AI가 더 묻자고 해도 코드가 막는다
MAX_CLARIFY = 1      # 질문당 "무슨 뜻이에요?" 되묻기 허용 횟수
PASS_SCORE = 14      # 답변 점수(0~20)가 이보다 낮으면 고친 답 · 재도전 대상
MIN_EXPERIENCE = 30  # 경험이 이 글자 수보다 짧으면 시작하지 않는다
SOURCE_LIMIT = 4000  # 공고 · 경험 원문을 프롬프트에 넣을 때 자르는 길이

CRITERIA = [
    ("specific", "구체성"),
    ("relevance", "직무 연관"),
    ("structure", "구조"),
    ("evidence", "근거 · 검증"),
]


# ── 질문 (AI가 만든 순서 그대로, 5개만) ──
def build_questions(generated: list[dict]) -> list[dict] | None:
    """빈 질문은 빼고 앞에서 5개. 5개가 안 되면 None."""
    valid = [g for g in generated if (g.get("question") or "").strip()][:TOTAL_QUESTIONS]
    if len(valid) < TOTAL_QUESTIONS:
        return None
    return [{"no": i, "type": (g.get("type") or "").strip() or "질문", "question": g["question"].strip(),
             "point": (g.get("point") or "").strip()}
            for i, g in enumerate(valid, 1)]


# ── 상황 블록 ────────────────────────────────
def clip(text: str, limit: int = SOURCE_LIMIT) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + " …(이하 생략)"


def build_context(company: str, job: str, posting: list[str] | str, experience: list[str] | str) -> str:
    def as_text(v):
        if isinstance(v, list):
            return " / ".join(s.strip() for s in v if s.strip()) or "없음"
        return clip(v) or "없음"

    return CONTEXT.format(company=company, job=job, posting=as_text(posting), experience=as_text(experience))


def transcript(records: list[dict]) -> str:
    """평가 위원회에 넘길 면접 기록."""
    lines = []
    for r in records:
        lines.append(f"[Q{r['no']}] {r['question']}")
        lines.append(f"  보는 점: {r['point']}")
        lines.append(f"  답: {r.get('answer') or '(답 없음)'}")
        if r.get("follow_q"):
            lines.append(f"  꼬리 질문: {r['follow_q']}")
            lines.append(f"  꼬리 답: {r.get('follow_a') or '(답 없음)'}")
    return "\n".join(lines)


# ── 점수 계산 ────────────────────────────────
def clamp(value, lo: int, hi: int) -> int:
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


def criteria_scores(raw: dict) -> dict:
    """기준 4개를 0~5로 자르고, 합계(0~20)는 코드가 다시 계산한다."""
    scores = {k: clamp(raw.get(k), 0, 5) for k, _ in CRITERIA}
    scores["total"] = sum(scores[k] for k, _ in CRITERIA)
    return scores


def normalize_eval(raw: dict, records: list[dict]) -> dict:
    panel_by_role = {p.get("role"): p for p in raw.get("panel", [])}
    panel = []
    for role in PANEL:
        p = panel_by_role.get(role)
        if p:
            panel.append({"role": role, "against": p.get("against", ""), "good": p.get("good", ""),
                          "score": clamp(p.get("score"), 0, 10)})

    answers_by_no = {a.get("no"): a for a in raw.get("answers", [])}
    answers = []
    for r in records:
        a = answers_by_no.get(r["no"], {})
        answers.append({
            "no": r["no"],
            "question": r["question"],
            **criteria_scores(a),
            "weak": a.get("weak", ""),
            "rewrite": a.get("rewrite", ""),
            "check": [c for c in a.get("check", []) if c.strip()][:2],
        })

    return {
        "panel": panel,
        "panel_avg": panel_average(panel),
        "answers": answers,
        "answer_avg": answer_average(answers),
        "conflict": raw.get("conflict", ""),
        "agree": raw.get("agree", ""),
        "next": [n for n in raw.get("next", []) if n.strip()][:3],
    }


def panel_average(panel: list[dict]) -> float:
    return round(sum(p["score"] for p in panel) / len(panel), 1) if panel else 0.0


def answer_average(answers: list[dict]) -> float:
    return round(sum(a["total"] for a in answers) / len(answers), 1) if answers else 0.0


def needs_rewrite(answer: dict) -> bool:
    return answer["total"] < PASS_SCORE


def retry_targets(answers: list[dict]) -> list[dict]:
    """기준 점수 미만인 답만, 점수 낮은 순으로."""
    return sorted([a for a in answers if needs_rewrite(a)], key=lambda a: (a["total"], a["no"]))


def compare(before: dict, after: dict) -> dict:
    rows = [
        {"기준": label, "전": before[k], "후": after[k], "차이": after[k] - before[k]}
        for k, label in CRITERIA
    ]
    return {"rows": rows, "before": before["total"], "after": after["total"],
            "delta": after["total"] - before["total"]}


def retry_summary(answers: list[dict], retries: dict) -> dict:
    """재도전한 질문들의 전 → 후 평균 (재도전하지 않은 질문은 빼고)."""
    done = [a for a in answers if a["no"] in retries]
    if not done:
        return {"count": 0, "before": 0.0, "after": 0.0, "delta": 0.0}
    before = sum(a["total"] for a in done) / len(done)
    after = sum(retries[a["no"]]["scores"]["total"] for a in done) / len(done)
    return {"count": len(done), "before": round(before, 1), "after": round(after, 1),
            "delta": round(after - before, 1)}


def stars(answer_avg: float) -> str:
    """답변 평균(0~20) → 별 3칸."""
    n = 3 if answer_avg >= 16 else 2 if answer_avg >= 12 else 1
    return "★" * n + "☆" * (3 - n)


# ── 질문 다듬기 검사 ─────────────────────────
POLISH_LIMIT = 60


def check_polish(questions: list[dict]) -> list[dict]:
    return [{**q, "length": len(q["question"]), "over": len(q["question"]) > POLISH_LIMIT} for q in questions]


UNVERIFIED = re.compile(r"\[확인 필요[^\]]*\]")


def count_unverified(text: str) -> int:
    return len(UNVERIFIED.findall(text or ""))


# ── 리포트 (코드가 계산한 숫자만) ────────────
def build_report(profile: dict, evaluation: dict, retries: dict, polish: dict | None) -> str:
    ev = evaluation
    summary = retry_summary(ev["answers"], retries)
    out = [
        f"# 면접 리포트 — {profile['company']} · {profile['job']} 신입",
        f"{date.today().isoformat()} · 별점 {stars(ev['answer_avg'])}",
        "",
        "## 한눈에",
        f"- 위원 평균: **{ev['panel_avg']} / 10**",
        f"- 답변 평균: **{ev['answer_avg']} / 20** (기준 {PASS_SCORE}점)",
        f"- 기준 미만 답변: {len(retry_targets(ev['answers']))}개",
    ]
    if summary["count"]:
        out.append(f"- 재도전 {summary['count']}개: 평균 {summary['before']} → {summary['after']} "
                   f"({summary['delta']:+.1f})")

    out += ["", "## 위원 4명", "| 위원 | 점수 | 뽑지 말아야 할 이유 | 좋은 점 |", "| --- | --- | --- | --- |"]
    out += [f"| {p['role']} | {p['score']} | {p['against']} | {p['good']} |" for p in ev["panel"]]
    out += ["", f"- 갈린 곳: {ev['conflict']}", f"- 같은 판단: {ev['agree']}"]

    out += ["", "## 답변별 점수", "| Q | 구체성 | 직무 연관 | 구조 | 근거 · 검증 | 합계 | 재도전 |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for a in ev["answers"]:
        r = retries.get(a["no"])
        after = f"{a['total']} → {r['scores']['total']}" if r else "-"
        out.append(f"| Q{a['no']} | {a['specific']} | {a['relevance']} | {a['structure']} | "
                   f"{a['evidence']} | {a['total']} | {after} |")

    out += ["", "## 다음 연습에서 고칠 것"] + [f"{i}. {n}" for i, n in enumerate(ev["next"], 1)]

    if polish:
        out += ["", "## 면접 끝에 할 질문", f"- 원래 질문: {polish['original']}"]
        out += [f"- ({q['angle']}) {q['question']}" for q in polish["questions"]]

    return "\n".join(out) + "\n"
