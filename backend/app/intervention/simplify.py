"""
Producing the text an intervention actually shows.

This is the part of Module 4 that finally does something to the content rather
than deciding to. Two of the four responses need generated text:

    simplify_content   the passage, rewritten more plainly
    bullet_summary     the passage, as a few bullets

The other two do not. A break suggestion and an assistant prompt are a
sentence, and that sentence is already on the decision as `reason`.

Why generation is not in the analyze path
-----------------------------------------
A model call takes seconds. `/engagement/analyze` runs once every ten seconds
and is serialised per session, so blocking it on a generation would stall
engagement detection - a working feature - behind a new one, and the stall
would grow with the model's latency.

So the decision and the text are separate requests. Analyze offers the
intervention in milliseconds; the browser then fetches the text from
`GET /intervention/{id}/content` before rendering it and reporting `displayed`.
On a cache hit that is immediate. On a miss it is one model call, on a request
of its own, where waiting is ordinary.

This also means the failure path already exists. If generation fails the client
reports `failed`, which P2 releases the cooldown for, so a model outage costs
the learner a delay rather than two minutes of silence.

What it refuses to do
---------------------
Output that is empty, that has run away from the passage, or that comes back
unchanged is rejected rather than shown. An unchanged passage means the model
did nothing, and showing it would spend a real intervention on an interruption
that helps nobody while Module 8 recorded it as delivered.

The length guard is deliberately loose, and the comment on MAX_LENGTH_RATIO
says why: measuring real output showed that simplifying lengthens text, because
explaining a term inline is longer than the term. A tight guard rejects good
work.
"""

import logging
import re

from app.intervention import cache, content, prompts, provider
from app.intervention.decider import BULLET_SUMMARY, SIMPLIFY_CONTENT

log = logging.getLogger(__name__)

# Which intervention types need generated text at all.
GENERATED_TYPES = {
    SIMPLIFY_CONTENT: prompts.TASK_SIMPLIFY,
    BULLET_SUMMARY: prompts.TASK_BULLETS,
}

# A guard against runaway output, NOT against length.
#
# This started at 1.5, on the reasoning that "a rewrite half as long again is
# not a simplification". Measuring real output disproved that. Six passages
# through gemini-3.6-flash, output length over input length:
#
#     simplify_content   1.16  1.27  1.50  1.65  2.29     mean 1.57
#     bullet_summary     1.02  1.35  1.67  1.67  2.03  2.13
#
# A ratio of 1.5 would have rejected three of five perfectly good rewrites.
# Simplifying training material lengthens it, because that is what explaining
# a term inline does - "ischaemia, which means a lack of blood flow over a long
# period" is longer than "ischaemia" and is the entire point.
#
# So the guard stays, for the case it is actually useful in: a model that loops,
# pads, or hands the whole prompt back. 3.0 is above everything measured and
# still catches a doubling plus commentary. It applies to both tasks now, since
# runaway output is not specific to one.
MAX_LENGTH_RATIO = 3.0

# Below this there is nothing worth rewriting, and the model tends to pad.
MIN_PASSAGE_CHARS = 80

_FENCE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.S)
_PREAMBLE = re.compile(r"^[^\n]{0,80}:\s*\n+")


class NotGenerated(Exception):
    """This intervention type shows a fixed sentence, not generated text."""


def clean(output: str) -> str:
    """
    Strip the two things models add despite being told not to: a code fence
    around the whole answer, and a short introductory line ending in a colon.

    Both are checked narrowly. A preamble is only removed when it is a short
    first line ending in a colon and something substantial follows, so a
    passage that legitimately begins with a heading is left alone.
    """
    text = (output or "").strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    without = _PREAMBLE.sub("", text, count=1).strip()
    if without and len(without) > 40:
        text = without
    return text


def validate(task: str, original: str, generated: str) -> str:
    """Raise GenerationFailed rather than return something not worth showing."""
    if not generated:
        raise provider.GenerationFailed("empty output")

    if len(generated) > len(original) * MAX_LENGTH_RATIO:
        raise provider.GenerationFailed("the output ran away from the passage")

    if task == prompts.TASK_SIMPLIFY:
        if generated.strip() == original.strip():
            raise provider.GenerationFailed("the passage came back unchanged")

    return generated


def _superseded(hit: dict, task: str, generator=None) -> bool:
    """
    Whether a cache hit should be thrown away and the work done again.

    Only in one case: the entry came from the extractive fallback and a real
    model is available now. Somebody who has configured a model should not keep
    being served leading sentences because the first person to read this
    paragraph arrived before the key was set.

    Everything else is kept, including model output when no model is currently
    configured - the text is no worse for the key having been removed.
    """
    if hit["generator"] != provider.GENERATOR_EXTRACTIVE:
        return False
    if generator is not None:
        return generator.name != provider.GENERATOR_EXTRACTIVE
    try:
        return provider.choose(task).name != provider.GENERATOR_EXTRACTIVE
    except provider.GenerationUnavailable:
        return False


def generate(
    *,
    task: str,
    text: str,
    generator: provider.TextGenerator = None,
    use_cache: bool = True,
) -> dict:
    """
    Text for one passage and one task.

    Returns {"generated", "generator", "cached"}. `generator` is carried all the
    way to the client so a fallback result is never mistaken for model output.
    """
    if task not in prompts.TASKS:
        raise ValueError(f"unknown task: {task}")
    passage = (text or "").strip()
    if len(passage) < MIN_PASSAGE_CHARS:
        raise provider.GenerationUnavailable("the passage is too short to be worth rewriting")

    # The key first, before any generator is chosen. That ordering is the point:
    # a passage a real model already rewrote stays reachable even if the API
    # key has since been removed, because serving text that was properly
    # generated is better than a 503 over a configuration change.
    cache_key = cache.key_for(task=task, text=passage, prompt_version=prompts.PROMPT_VERSION)
    hit = cache.get(cache_key) if use_cache else None

    if hit and not _superseded(hit, task, generator):
        return {"generated": hit["generated"], "generator": hit["generator"], "cached": True}

    generator = generator or provider.choose(task)

    if task == prompts.TASK_SIMPLIFY and not generator.can_simplify:
        raise provider.GenerationUnavailable(
            f"{generator.name} cannot simplify; a language model is required"
        )
    model = getattr(generator, "model", generator.name)

    prompt = prompts.build_prompt(task, passage)
    generated = validate(task, passage, clean(generator.generate(prompt, task=task, text=passage)))

    if use_cache:
        cache.put(
            cache_key, generated=generated, generator=generator.name, task=task, model=model
        )
    return {"generated": generated, "generator": generator.name, "cached": False}


def for_intervention(uid: str, event: dict, *, generator=None) -> dict:
    """
    The text for a stored intervention event.

    Raises NotGenerated for the two types that show a fixed sentence,
    LookupError when the passage cannot be reached, and the provider's
    exceptions when generation is unavailable or fails.
    """
    task = GENERATED_TYPES.get(event["intervention_type"])
    if task is None:
        raise NotGenerated(event["intervention_type"])

    chunk = content.get_chunk(uid, event.get("content_id"), event.get("chunk_id"))
    if not chunk or not chunk["text"]:
        raise LookupError("the passage this intervention refers to could not be read")

    result = generate(task=task, text=chunk["text"], generator=generator)
    return {**result, "original": chunk["text"], "chunk_id": chunk["chunk_id"]}
