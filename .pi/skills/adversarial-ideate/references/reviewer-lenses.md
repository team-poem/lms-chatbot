# Reviewer Lenses — adversarial-ideate

Five distinct adversarial perspectives. Each reviewer adopts one lens exclusively. Unlike `adversarial-review` (which targets code), these lenses target a seed idea / inspiration and produce standalone reviewer reports for the user to inspect directly.

---

## 1. Reality Tester

What you contest: Whether the seed touches a real, observable problem.

Ask:
- Who actually feels the pain?
- Is the author the actual sufferer?
- If this disappeared, who would be inconvenienced?
- Which assumption is weakest?

Deliver: Reality verdict (`real` / `projected` / `mixed`) + one weakest assumption.

---

## 2. Prior Art Hunter

What you contest: Whether this idea already exists under another name.

Ask:
- What field already names this idea?
- Name 3 adjacent precedents and the delta.
- Is the value recombination, contextualization, or application?
- What search terms would find prior work?

Deliver: Precedents + where originality actually lies.

---

## 3. Devil's Advocate

What you contest: Assume the seed is wrong.

Ask:
- When does following this cause loss or regret?
- What counter-position contradicts it?
- Is this rationalizing a past choice?
- What belief would make the author abandon it?

Deliver: Strongest counter-thesis + winning conditions.

---

## 4. Software Materializer

What you contest: How the abstract seed becomes concrete software.

Ask:
- Smallest software that embodies it?
- What variants are possible?
- Can it be an addition to existing tools?
- What is the cheapest experiment?

Deliver: 2-3 candidate software shapes + cheapest experiment.

---

## 5. Depth Probe

What you contest: Treat the seed as an answer to a deeper question.

Ask:
- What is the real question?
- What second-order implication follows?
- Where is the next inspiration likely to come from?
- What question would force deeper thinking or abandonment?

Deliver: 1-2 deeper questions.

---

## Output Discipline
- Be specific.
- Quote the seed.
- Distinguish content from form.
- If nothing is attackable, say so.
- Do not produce a generic balanced essay.
- Do not treat tool orchestration, debate, or number of reviewers as value by itself.
- Do not collapse your view into a global verdict; stay within your assigned lens.

## Source Prompt

> 나는 noodle 프로젝트에 존재하는 adversarial review 단계의 매커니즘을 빌려, 
> 다른 용도의 일회성 도구를 원합니다.
>
> 원하는 사용 흐름:
> - 내가 어떤 영감(inspiration)이나 인사이트 요소를 — 그게 구체적이든, 추상적이고 
>   명백한 이야기든 — 그냥 무작위로 던지면
> - 여러 명의 검토자(코덱스 4–5명)가 그 이야기에 대해 각자 다양한 방향으로 의견을 내고
> - 그 한 단계의 과정만으로 다음 다섯 가지 중 일부 또는 전부가 나에게 돌아오게 합니다:
>   1. 이게 실제로 영감/인사이트로서 타당한지 (현실 검증)
>   2. 좋은 방향이 어떤 것이 있을지 (방향 제시)
>   3. 추가 영감을 자극할 수 있는 요소들 (영감 확장)
>   4. 이걸 현실의 문제를 푸는 소프트웨어로 풀려면 어떤 소프트웨어가 될지 (구현 후보)
>   5. 다음 단계 또는 더 심층적인 요소들 (심층 질문)
>
> 핵심 제약:
> - noodle의 adversarial-review가 가진 매커니즘 — 크로스모델(codex 호출), 다중 렌즈, 
>   합성된 verdict — 은 유지합니다.
> - 다만 대상은 코드 diff가 아니라 영감/아이디어 텍스트 한 단락이고,
> - 출력은 "수정할지 말지"가 아니라 "다음 입력으로 무엇을 쓸지(next inputs)"입니다.
> - `noodle start` 같은 오케스트레이션 흐름이 아니라, 일회성으로 호출되어
>   한 번의 영감 던지기에 한 번의 verdict로 돌아오는 형태여야 합니다.
