"""
The prompts, and the one rule that governs them.

A prompt here is a pure function of (task, text) and nothing else
--------------------------------------------------------------------
No user id, no session, no engagement state, no reason string. This is not
tidiness, it is what makes the cache possible and what keeps it safe.

Simplifying paragraph 5 of a document is the same work for every learner who
reads it, so the result can be computed once and reused. That only holds if the
prompt does not depend on who asked. The moment "the learner seems to be
struggling" goes into a prompt, three things happen at once: the cache key
becomes per-learner and stops hitting, engagement state ends up stored in
generated text, and the same paragraph starts reading differently for different
people for reasons nobody can inspect.

So `build_prompt` takes two arguments and cannot see anything else. There is a
test that asserts two different learners produce the same cache key for the
same chunk.

PROMPT_VERSION is part of the cache key. Change the wording below and every
previously cached result stops being used, with no migration and no stale text
surviving a rewrite.
"""

# v2 adds the analogy to `simplify_content`. This MUST change whenever the
# wording below changes: it is part of the cache key, so bumping it is what
# stops a learner being served a v1 rewrite that has no analogy in it. There is
# no migration and nothing to clean up - old entries simply stop being hit.
PROMPT_VERSION = "v2"

TASK_SIMPLIFY = "simplify_content"
TASK_BULLETS = "bullet_summary"

TASKS = (TASK_SIMPLIFY, TASK_BULLETS)

# Shared constraints. The important one is the third: this is corporate
# training material, so the technical terms are usually the thing being
# taught. A "simplification" that removes the word `amortisation` from a
# paragraph about amortisation has removed the lesson.
_RULES = """Rules:
- Keep all of the information. Do not add facts, figures, or claims that are
  not in the text.
- Do not remove or replace technical terms that the text is teaching. Explain
  them in plainer words instead.
- Write in the same language as the text.
- Return only the result, with no preamble, heading or commentary."""

# Scope section 6.4 asks for a rewrite "in simpler language with an analogy".
#
# That sits awkwardly against the first rule, and the wording below is where
# the two are reconciled: an analogy is the one thing the model may add, it is
# a comparison rather than a new fact about the subject, and it comes last so a
# learner can stop reading at the end of the rewrite and have lost nothing.
#
# "One short analogy" is deliberate. Left open, the model writes three, and the
# result stops being the paragraph the learner was reading. The length guard in
# simplify.py is the backstop, not this sentence.
_SIMPLIFY = """Rewrite the following passage so it is easier to understand.

Use shorter sentences and everyday words. Keep the same meaning and the same
level of detail - this is a rewrite, not a summary.

Then add one short analogy, as a final sentence or two, comparing the idea to
something familiar from everyday life. The analogy is a comparison only: it
must not state any new fact about the subject itself. If the passage is too
abstract or too short for an honest analogy, leave it out rather than forcing
one.

{rules}

Passage:
{text}"""

_BULLETS = """Turn the following passage into 3 to 5 short bullet points that
capture its main points.

Each bullet is one line, starting with "- ".

{rules}

Passage:
{text}"""

_TEMPLATES = {
    TASK_SIMPLIFY: _SIMPLIFY,
    TASK_BULLETS: _BULLETS,
}


def build_prompt(task: str, text: str) -> str:
    """
    The prompt for one task on one passage.

    Two arguments, deliberately. See the module docstring.
    """
    if task not in _TEMPLATES:
        raise ValueError(f"no prompt for task: {task}")
    if not text or not text.strip():
        raise ValueError("cannot build a prompt for empty text")
    return _TEMPLATES[task].format(rules=_RULES, text=text.strip())
