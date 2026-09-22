"""
Where generated text comes from, behind an interface narrow enough to swap.

Why this is not Module 5's client
---------------------------------
Module 5 has a Gemini client and the sensible thing is to use it. It cannot be
imported: `app/ai_assistant/` and `app/core/config.py` arrive with PR #43,
which is open, conflicting and has changes requested. Waiting for it would
leave Module 4 unable to produce any of the four responses scope 6.4 asks for.

Duplicating Module 5's client would be worse than waiting, so this does
neither. Module 4 needs one thing from a language model - text in, text out,
no conversation and no memory - which is a much smaller surface than the
assistant needs. `TextGenerator` is that surface. `GeminiGenerator` implements
it today by reading the *same environment variables* Module 5 reads, so there
is one API key on the server and not two. When #43 merges, the body of
`GeminiGenerator.generate` becomes a call to `ai_assistant.service`'s client
factory and nothing else in Module 4 changes.

Two things this deliberately will not do
----------------------------------------
**It will not pretend.** With no model available there is no honest way to
simplify a passage, so `simplify_content` fails instead of returning the
original text labelled as simplified. That failure is visible - the client
reports `failed`, which releases the cooldown - whereas a silent passthrough
would be a lie the learner cannot detect and which Module 8 would record as a
delivered intervention that may have helped.

**It will not hide which one ran.** Every result carries the generator that
produced it, and the API passes that through, because "was this actually
written by a model or assembled by a fallback" is not a question anyone should
have to guess at.
"""

import logging
import os
import re
import time

log = logging.getLogger(__name__)

# Same names Module 5 uses, so the server has one key and one model setting.
ENV_API_KEY = "GEMINI_API_KEY"
ENV_MODEL = "GEMINI_MODEL"
ENV_TIMEOUT_MS = "GEMINI_TIMEOUT_MS"

# Module 4's own switch. `auto` uses Gemini when a key is present and falls back
# when it is not; `mock` never calls out, for demos and for anyone who wants to
# be certain no request leaves the machine. There is no third mode because
# tests inject a generator directly rather than setting an environment
# variable.
ENV_MODE = "INTERVENTION_CONTENT_MODE"

DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_TIMEOUT_MS = 60_000

# Gemini returns 503 "currently experiencing high load" often enough to matter:
# two of about fifteen calls while measuring prompt output. Without a retry a
# learner loses the intervention entirely over a few seconds of load.
#
# 5xx and 429 are retried. 429 is a 4xx but it is a rate limit, not a mistake -
# the free tier limits calls per minute, and a burst of interventions across a
# few learners reaches that easily. Every other 4xx is a bad key or a bad model
# name; retrying those only makes a misconfiguration slower to diagnose.
RATE_LIMITED = 429
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 3.0)

# A 429 is not always transient, and the retry cannot tell the difference.
# Measured on the free tier: the quota is
# GenerateRequestsPerDayPerProjectPerModel-FreeTier, 20 requests PER DAY PER
# MODEL. Once that is gone, all three attempts fail and the learner gets
# nothing until tomorrow.
#
# That is survivable only because of cache.py. A passage is generated once and
# then served to everyone, so a ten-chunk document costs at most twenty calls
# ever, not twenty per learner. Anything beyond a demo needs a paid tier.

GENERATOR_GEMINI = "gemini"
GENERATOR_EXTRACTIVE = "extractive"


class GenerationUnavailable(RuntimeError):
    """No generator can do this task right now. The caller must not improvise."""


class GenerationFailed(RuntimeError):
    """A generator ran and did not produce usable output."""


class TextGenerator:
    """
    Text in, text out.

    Implemented by GeminiGenerator now, and by a thin delegation to Module 5's
    client factory once #43 merges. `name` travels with every result so the
    origin of a piece of text is never in doubt.
    """

    name = "abstract"
    can_simplify = False

    def generate(self, prompt: str, *, task: str, text: str) -> str:
        raise NotImplementedError


class GeminiGenerator(TextGenerator):
    """
    The real one. The SDK is imported inside the call, not at module level,
    because `google-genai` is not installed on every machine yet - it arrives
    with #43 - and Module 4 must degrade rather than fail to import.
    """

    name = GENERATOR_GEMINI
    can_simplify = True

    def __init__(self, api_key: str, model: str = None, timeout_ms: int = None):
        self.api_key = api_key
        self.model = model or os.getenv(ENV_MODEL, DEFAULT_MODEL).strip() or DEFAULT_MODEL
        try:
            self.timeout_ms = int(os.getenv(ENV_TIMEOUT_MS, DEFAULT_TIMEOUT_MS))
        except ValueError:
            self.timeout_ms = DEFAULT_TIMEOUT_MS
        if timeout_ms is not None:
            self.timeout_ms = timeout_ms

    def generate(self, prompt: str, *, task: str, text: str) -> str:
        try:
            from google import genai
            from google.genai import errors, types
        except ImportError as error:
            raise GenerationUnavailable(
                "the Gemini SDK is not installed on this server"
            ) from error

        # types.HttpOptions rather than a plain dict, matching how Module 5
        # builds its client. Same SDK, same construction, so there is one
        # shape to get right instead of two.
        client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(timeout=self.timeout_ms),
        )

        last = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = client.models.generate_content(
                    model=self.model, contents=prompt
                )
            except errors.APIError as error:
                transient = isinstance(error, errors.ServerError) or (
                    getattr(error, "code", None) == RATE_LIMITED
                )
                if not transient:
                    log.warning("Gemini call failed: %s", type(error).__name__)
                    raise GenerationFailed("the model did not answer") from error

                # Logged by type only, because the exception text can echo back
                # the learner's study material.
                last = error
                log.warning(
                    "Gemini unavailable, attempt %d of %d", attempt + 1, MAX_ATTEMPTS
                )
                if attempt + 1 < MAX_ATTEMPTS:
                    time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                continue
            except Exception as error:
                log.warning("Gemini call failed: %s", type(error).__name__)
                raise GenerationFailed("the model did not answer") from error

            output = getattr(response, "text", None)
            if not output:
                raise GenerationFailed("the model returned nothing")
            return output

        raise GenerationFailed("the model was unavailable") from last


class ExtractiveGenerator(TextGenerator):
    """
    The fallback, and only for bullets.

    Taking the leading sentences of a passage is a real summarisation method,
    not a stand-in for one, so a learner is not being shown something invented.
    It is labelled `extractive` in the response so nobody mistakes it for model
    output.

    `can_simplify` is False and stays False. Simplifying needs a language
    model; there is no arrangement of the original sentences that is simpler
    than the original.
    """

    name = GENERATOR_EXTRACTIVE
    can_simplify = False

    MAX_BULLETS = 5
    MIN_SENTENCE_WORDS = 4

    def generate(self, prompt: str, *, task: str, text: str) -> str:
        from app.intervention.prompts import TASK_BULLETS

        if task != TASK_BULLETS:
            raise GenerationUnavailable(f"{self.name} cannot do {task}")

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
        useful = [s for s in sentences if len(s.split()) >= self.MIN_SENTENCE_WORDS]
        chosen = (useful or sentences)[: self.MAX_BULLETS]
        if not chosen:
            raise GenerationFailed("nothing to summarise")
        return "\n".join(f"- {s}" for s in chosen)


def _mode() -> str:
    return (os.getenv(ENV_MODE) or "auto").strip().lower()


def choose(task: str) -> TextGenerator:
    """
    The best generator available for this task, or a clear refusal.

    Order is deliberate: a real model whenever one is configured, the
    extractive fallback only where it is honest, and an exception rather than
    anything that would present one kind of output as another.
    """
    from app.intervention.prompts import TASK_SIMPLIFY

    if _mode() != "mock":
        api_key = (os.getenv(ENV_API_KEY) or "").strip()
        if api_key:
            return GeminiGenerator(api_key)

    fallback = ExtractiveGenerator()
    if task == TASK_SIMPLIFY:
        raise GenerationUnavailable(
            "simplification needs a language model; set GEMINI_API_KEY"
        )
    return fallback
