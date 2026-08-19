from __future__ import annotations

import html
import math
import re
from collections.abc import Iterable
from itertools import cycle
from typing import Any

from .schemas import Episode, Story


COMPLIANCE_GATES: tuple[str, ...] = (
    "opinion",
    "take_connects_stories",
    "format_varied",
    "advice_safe",
    "neutral_anchor",
    "figures_sourced",
    "no_verify_tags",
    "sources_linked",
    "synthetic_disclosure",
    "broll_cadence",
    "one_upload_today",
)

REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "daily": ("hook", "story_1", "story_2", "story_3", "take", "sign_off"),
    "deep_dive": (
        "hook",
        "what_happened",
        "background",
        "mechanism",
        "who_wins_who_loses",
        "take",
        "sign_off",
    ),
}

HYPE_WORDS = {"game-changing", "revolutionary", "insane", "wild"}
ADVICE_PATTERNS = (
    r"\byou should\b",
    r"\byou must\b",
    r"\byou need to\b",
    r"\byou ought to\b",
    r"\bi (?:recommend|advise)\b",
    r"\bmy advice\b",
    r"\bbuy (?:this|the|these)\b",
    r"\bsell (?:this|the|these)\b",
    r"(?:^|[.!?]\s+)(?:buy|sell|invest in|vote for|take|use|avoid|choose)\b",
    r"\b(?:buy|sell|invest in)\s+(?:shares?|stocks?|tokens?|[a-z][\w.-]+)\b",
    r"\bmedical advice\b",
    r"\blegal advice\b",
    r"\bfinancial advice\b",
    r"\bpolitical advice\b",
)
CREDENTIAL_PATTERNS = (
    r"\b(?:i am|i'm|your|our)\s+(?:an?\s+)?"
    r"(?:doctor|dr\.?|expert|analyst|professor|advisor)\b",
    r"\b(?:doctor|dr\.?|expert|analyst|professor|advisor)\s+mira\b",
)
UNSPOKEN_ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}\b")

_WORD_RE = re.compile(r"\b[\w]+(?:[-'][\w]+)*\b", flags=re.UNICODE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def runtime_seconds(text: str) -> int:
    words = count_words(text)
    return math.ceil(words / 2.5) if words else 0


def default_compliance() -> dict[str, bool]:
    return {gate: False for gate in COMPLIANCE_GATES}


def _small_number_words(number: int) -> str:
    ones = (
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    )
    tens = (
        "",
        "",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
    )
    if number < 20:
        return ones[number]
    if number < 100:
        return tens[number // 10] + (
            f" {ones[number % 10]}" if number % 10 else ""
        )
    if number < 1_000:
        return f"{ones[number // 100]} hundred" + (
            f" {_small_number_words(number % 100)}" if number % 100 else ""
        )
    for value, label in (
        (1_000_000_000, "billion"),
        (1_000_000, "million"),
        (1_000, "thousand"),
    ):
        if number >= value:
            lead, remainder = divmod(number, value)
            result = f"{_small_number_words(lead)} {label}"
            return (
                f"{result} {_small_number_words(remainder)}"
                if remainder
                else result
            )
    return " ".join(ones[int(digit)] for digit in str(number))


def _spell_number_match(match: re.Match[str]) -> str:
    value = match.group(0)
    if "." in value:
        whole, decimal = value.split(".", 1)
        return (
            f"{_small_number_words(int(whole))} point "
            + " ".join(_small_number_words(int(digit)) for digit in decimal)
        )
    number = int(value)
    if number <= 999_999_999_999:
        return _small_number_words(number)
    return " ".join(_small_number_words(int(digit)) for digit in value)


def voice_safe_source_text(text: str) -> str:
    value = html.unescape(_HTML_TAG_RE.sub(" ", text or ""))
    value = value.replace("—", ",").replace("–", ",").replace(";", ",")
    value = value.replace("(", " ").replace(")", " ")
    value = value.replace("[", " ").replace("]", " ")
    value = value.replace("$", "")
    value = re.sub(r"\d+(?:\.\d+)?", _spell_number_match, value)
    value = re.sub(
        r"\b[A-Z]{2,5}\b",
        lambda match: "-".join(match.group(0)),
        value,
    )
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n.,!?")
    return value


def _limit_words(text: str, limit: int) -> str:
    words = text.split()
    return " ".join(words[:limit])


def _as_sentences(phrase: str, max_words: int = 16) -> list[str]:
    safe = voice_safe_source_text(phrase)
    words = safe.split()
    sentences: list[str] = []
    for index in range(0, len(words), max_words):
        chunk = " ".join(words[index : index + max_words]).strip(" ,:")
        if chunk:
            sentences.append(f"{chunk[0].upper()}{chunk[1:]}.")
    return sentences


def _compose(phrases: Iterable[str]) -> str:
    sentences: list[str] = []
    for phrase in phrases:
        sentences.extend(_as_sentences(phrase))
    return " ".join(sentences)


def _fill_section(phrases: list[str], minimum_words: int) -> str:
    sentences: list[str] = []
    prepared: list[str] = []
    for phrase in phrases:
        prepared.extend(_as_sentences(phrase))
    if not prepared:
        return ""
    for sentence in cycle(prepared):
        sentences.append(sentence)
        if count_words(" ".join(sentences)) >= minimum_words:
            break
    return " ".join(sentences)


def _exact_section(phrases: list[str], target_words: int) -> str:
    """Build a spoken section with a deterministic word budget."""
    filled = _fill_section(phrases, target_words)
    words = filled.split()
    if len(words) <= target_words:
        return filled
    return " ".join(words[:target_words]).rstrip(" ,;:") + "."


def _story_section(
    story: Story,
    ordinal: str,
    minimum_words: int,
) -> str:
    source = _limit_words(voice_safe_source_text(story.source), 4)
    title = _limit_words(voice_safe_source_text(story.title), 7)
    summary = _limit_words(voice_safe_source_text(story.summary), 7)
    return _fill_section(
        [
            f"Story {ordinal} comes from {source}",
            f"The source headline reads {title}",
            f"The supplied source summary says {summary}",
            "No additional fact is added beyond the supplied source material",
            "A human editor confirms the framing before publication",
            "The reported event remains separate from this desk's interpretation",
            "Its practical impact depends on details inside the linked source",
        ],
        minimum_words,
    )


def _safe_title(prefix: str, source_title: str) -> str:
    clean = re.sub(r"\s+", " ", source_title).strip()
    available = max(1, 59 - len(prefix))
    if len(clean) > available:
        clean = clean[: available - 1].rstrip() + "…"
    return f"{prefix}{clean}"[:59]


def _overlay_text(value: str, limit: int = 42) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _description(angle: str, stories: list[Story]) -> str:
    lines = [
        "Human-edited AI newsroom draft.",
        f"Editorial angle: {angle}",
        "Review every original source before publication.",
        "Sources:",
    ]
    lines.extend(f"- {story.source}: {story.url}" for story in stories)
    return "\n".join(lines)


def make_cues(total_runtime: int) -> list[dict[str, Any]]:
    if total_runtime <= 0:
        return []
    return [
        {
            "timestamp_seconds": second,
            "duration_seconds": min(5, total_runtime - second),
            "broll_id": (index % 15) + 1,
            "label": "Reusable library cue",
        }
        for index, second in enumerate(range(0, total_runtime, 12))
    ]


def _daily_draft(episode: Episode, stories: list[Story]) -> dict[str, Any]:
    angle = _limit_words(voice_safe_source_text(episode.angle), 12)
    sections = {
        "hook": _compose(
            ("Three sourced items frame one question for the A-I desk",)
        ),
        "story_1": _exact_section(
            [
                f"Story one comes from {_limit_words(voice_safe_source_text(stories[0].source), 4)}",
                f"The source headline reads {_limit_words(voice_safe_source_text(stories[0].title), 7)}",
                f"The supplied source summary says {_limit_words(voice_safe_source_text(stories[0].summary), 7)}",
                "No additional fact is added beyond the supplied source material",
                "A human editor confirms the framing before publication",
                "The reported event remains separate from this desk's interpretation",
                "Its practical impact depends on details inside the linked source",
            ],
            52,
        ),
        "story_2": _exact_section(
            [
                f"Story two comes from {_limit_words(voice_safe_source_text(stories[1].source), 4)}",
                f"The source headline reads {_limit_words(voice_safe_source_text(stories[1].title), 7)}",
                f"The supplied source summary says {_limit_words(voice_safe_source_text(stories[1].summary), 7)}",
                "No additional fact is added beyond the supplied source material",
                "A human editor confirms the framing before publication",
                "The reported event remains separate from this desk's interpretation",
                "Its practical impact depends on details inside the linked source",
            ],
            47,
        ),
        "story_3": _exact_section(
            [
                f"Story three comes from {_limit_words(voice_safe_source_text(stories[2].source), 4)}",
                f"The source headline reads {_limit_words(voice_safe_source_text(stories[2].title), 7)}",
                f"The supplied source summary says {_limit_words(voice_safe_source_text(stories[2].summary), 7)}",
                "No additional fact is added beyond the supplied source material",
                "A human editor confirms the framing before publication",
                "The reported event remains separate from this desk's interpretation",
                "Its practical impact depends on details inside the linked source",
            ],
            42,
        ),
        "take": _exact_section(
            [
                f"The editorial angle is {angle}",
                "This interpretation stays grounded in all three linked sources",
                "The comparison is editorial judgment and not a new factual claim",
                "Together, the stories reward careful verification before any broader conclusion",
                "The human editor remains accountable for this connection",
            ],
            51,
        ),
        "sign_off": _compose(("That is the A-I Desk, review every source",)),
    }
    script = "\n\n".join(sections.values())
    total_words = count_words(script)
    total_runtime = runtime_seconds(script)
    return {
        "script": script,
        "sections": sections,
        "title": _safe_title("AI Desk: ", stories[0].title),
        "description": _description(episode.angle, stories),
        "hashtags": [
            "#AI",
            "#AINews",
            "#DeveloperNews",
            "#Technology",
            "#AIDesk",
        ],
        "overlays": [
            {
                "timestamp_seconds": 0,
                "text": _overlay_text("Three stories. One angle."),
            },
            {
                "timestamp_seconds": 12,
                "text": _overlay_text(stories[0].title),
            },
            {
                "timestamp_seconds": 38,
                "text": _overlay_text(stories[1].title),
            },
            {
                "timestamp_seconds": 58,
                "text": _overlay_text(stories[2].title),
            },
        ],
        "cues": make_cues(total_runtime),
        "word_count": total_words,
        "runtime_seconds": total_runtime,
    }


def _deep_draft(episode: Episode, story: Story) -> dict[str, Any]:
    title = _limit_words(voice_safe_source_text(story.title), 12)
    summary = _limit_words(voice_safe_source_text(story.summary), 18)
    source = _limit_words(voice_safe_source_text(story.source), 6)
    angle = _limit_words(voice_safe_source_text(episode.angle), 18)

    sections = {
        "hook": _compose(
            (
                f"One source frames a deeper editorial question about {title}",
            )
        ),
        "what_happened": _fill_section(
            [
                f"The selected source is {source}",
                f"Its headline reads {title}",
                f"The supplied summary says {summary}",
                "This offline draft treats the linked article as the factual authority",
                "It adds no announcement date benchmark price or result",
                "The editor separates the source claim from interpretation",
                "Every quoted phrase remains traceable to the linked article",
                "Unsupported detail stays out of the publication draft",
                "The current text records evidence boundaries before commentary",
                "The source link remains available in the episode description",
            ],
            150,
        ),
        "background": _fill_section(
            [
                "Background needs earlier events that the supplied material may not include",
                "This offline draft does not create that missing chronology",
                "The editor can add context only after checking primary sources",
                "Each added date needs a direct citation in the description",
                "Each added figure needs the same source level check",
                "A related headline alone is not enough evidence",
                "The useful question is what changed compared with the verified prior state",
                "Another question is who made the claim and in what setting",
                "Source language and editorial language should remain visibly distinct",
                "Uncertainty belongs in the script when the record is incomplete",
                "A strong background section explains context without pretending certainty",
                "The human editor owns every connection between earlier events",
                "No credential or expert framing is assigned to the A-I anchor",
                "The result should remain reporting and interpretation rather than advice",
            ],
            240,
        ),
        "mechanism": _fill_section(
            [
                "The mechanism section explains how the reported change works",
                "The supplied source must support each component in that explanation",
                "This scaffold does not infer a model architecture product feature or benchmark",
                "The editor can identify inputs outputs constraints and measured results",
                "Those details should use plain language suitable for spoken delivery",
                "A mechanism claim needs more than a promotional phrase",
                "The script should distinguish a demonstration from a deployed capability",
                "It should distinguish a company statement from independent evidence",
                "Numbers must be written as spoken and traced to the source",
                "Acronyms should be written for the voice engine",
                "Short sentences keep one technical idea audible at a time",
                "Any missing technical detail can be omitted without inventing a bridge",
                "The linked article remains the authority for the final explanation",
                "The human edit decides which mechanism details matter to developers",
            ],
            240,
        ),
        "who_wins_who_loses": _fill_section(
            [
                "Impact analysis starts with stakeholders named or supported by the source",
                "This draft does not invent winners losers customers or market effects",
                "A developer impact claim needs a clear connection to verified material",
                "A founder impact claim needs the same evidence boundary",
                "The episode can describe tradeoffs without telling viewers what to do",
                "Sensitive topic guidance remains outside the format",
                "Benefits and costs should be presented with equal sourcing discipline",
                "A company claim should not become an independent conclusion",
                "The final edit should state whose perspective supports each effect",
                "If evidence is mixed the script should say that plainly",
                "The editorial angle can connect facts without creating new facts",
                "Viewers should be able to follow every claim back to a source",
            ],
            190,
        ),
        "take": _fill_section(
            [
                f"The editorial angle is {angle}",
                "That angle is an interpretation rather than a newly reported fact",
                "It must remain grounded in the linked source",
                "The strongest version explains why this evidence changes the discussion",
                "It avoids hype certainty and instructions to the viewer",
                "I could be wrong about this, and here's what would change my mind",
                "Clear contrary evidence from a primary source would change the conclusion",
                "A corrected source record would also require a revised episode",
                "Visible uncertainty is part of the human editorial judgment",
                "The final take should sound argued rather than merely summarized",
            ],
            140,
        ),
        "sign_off": _compose(("That is the A-I Desk, review every source",)),
    }
    script = "\n\n".join(sections.values())
    total_words = count_words(script)
    total_runtime = runtime_seconds(script)
    return {
        "script": script,
        "sections": sections,
        "title": _safe_title("Deep Dive: ", story.title),
        "description": _description(episode.angle, [story]),
        "hashtags": [
            "#AI",
            "#AIDeepDive",
            "#DeveloperNews",
            "#Technology",
            "#AIDesk",
        ],
        "overlays": [
            {"timestamp_seconds": 0, "text": _overlay_text(story.title)},
            {
                "timestamp_seconds": 90,
                "text": _overlay_text("What the source establishes"),
            },
            {
                "timestamp_seconds": 240,
                "text": _overlay_text("How it works"),
            },
            {
                "timestamp_seconds": 360,
                "text": _overlay_text("The editorial take"),
            },
        ],
        "cues": make_cues(total_runtime),
        "word_count": total_words,
        "runtime_seconds": total_runtime,
    }


def build_offline_draft(
    episode: Episode, stories: list[Story]
) -> dict[str, Any]:
    if episode.kind == "daily":
        return _daily_draft(episode, stories)
    return _deep_draft(episode, stories[0])


def join_sections(kind: str, sections: dict[str, str]) -> str:
    ordered_keys = REQUIRED_SECTIONS.get(kind, tuple(sections))
    return "\n\n".join(
        sections[key].strip()
        for key in ordered_keys
        if sections.get(key, "").strip()
    )


def contains_advice(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in ADVICE_PATTERNS)


def contains_credential_framing(text: str) -> bool:
    lowered = text.lower()
    return any(
        re.search(pattern, lowered) for pattern in CREDENTIAL_PATTERNS
    )


def contains_unspoken_acronym(text: str) -> bool:
    return bool(UNSPOKEN_ACRONYM_RE.search(text))


def broll_cadence_valid(cues: list[dict[str, Any]], runtime: int) -> bool:
    if not cues or runtime <= 0:
        return False
    timestamps: list[int] = []
    for cue in cues:
        try:
            timestamp = cue["timestamp_seconds"]
            duration = cue["duration_seconds"]
            broll_id = cue["broll_id"]
            label = cue["label"]
        except (KeyError, TypeError):
            return False
        if (
            not isinstance(timestamp, int)
            or isinstance(timestamp, bool)
            or timestamp < 0
            or not isinstance(duration, int)
            or isinstance(duration, bool)
            or not 1 <= duration <= 12
            or not isinstance(broll_id, int)
            or isinstance(broll_id, bool)
            or not 1 <= broll_id <= 15
            or not isinstance(label, str)
            or not label.strip()
        ):
            return False
        timestamps.append(timestamp)
    if len(timestamps) != len(set(timestamps)):
        return False
    timestamps.sort()
    if not timestamps or timestamps[0] > 3:
        return False
    intervals = [
        right - left for left, right in zip(timestamps, timestamps[1:])
    ]
    if any(not 8 <= interval <= 12 for interval in intervals):
        return False
    final_tail = runtime - timestamps[-1]
    return 0 <= final_tail <= 12


def production_metadata_errors(episode: Episode) -> list[str]:
    errors: list[str] = []
    if (
        len(episode.hashtags) != 5
        or len(set(episode.hashtags)) != 5
        or any(
            not isinstance(tag, str)
            or not tag.startswith("#")
            or len(tag) <= 1
            for tag in episode.hashtags
        )
    ):
        errors.append("provide exactly five unique hashtags")

    overlay_timestamps: list[int] = []
    overlays_valid = len(episode.overlays) == 4
    for overlay in episode.overlays:
        timestamp = overlay.get("timestamp_seconds")
        text = overlay.get("text")
        if (
            not isinstance(timestamp, int)
            or isinstance(timestamp, bool)
            or timestamp < 0
            or timestamp > episode.runtime_seconds
            or not isinstance(text, str)
            or not text.strip()
            or len(text.strip()) > 42
        ):
            overlays_valid = False
            break
        overlay_timestamps.append(timestamp)
    if (
        not overlays_valid
        or overlay_timestamps != sorted(set(overlay_timestamps))
    ):
        errors.append(
            "provide exactly four ordered timed overlays with one to "
            "forty-two characters"
        )

    if not broll_cadence_valid(episode.cues, episode.runtime_seconds):
        errors.append(
            "provide valid B-roll cues every eight to twelve seconds"
        )
    return errors


def calculate_compliance(
    episode: Episode,
    stories: list[Story],
    previous: dict[str, bool] | None = None,
) -> dict[str, bool]:
    prior = {**default_compliance(), **(previous or {})}
    take = episode.sections.get("take", "").strip()
    description = episode.description
    automatic_checks = {
        "opinion": bool(episode.angle.strip() and take),
        "take_connects_stories": bool(
            take
            and (
                episode.kind == "deep_dive"
                or "three" in take.lower()
                or "source" in take.lower()
            )
        ),
        "advice_safe": not contains_advice(episode.script),
        "neutral_anchor": not contains_credential_framing(episode.script),
        "no_verify_tags": "[verify]" not in episode.script.lower(),
        "sources_linked": bool(stories)
        and all(story.url in description for story in stories),
        "broll_cadence": broll_cadence_valid(
            episode.cues, episode.runtime_seconds
        ),
    }
    compliance = prior.copy()
    for gate, passed in automatic_checks.items():
        if not passed:
            compliance[gate] = False
    return {
        gate: bool(compliance.get(gate, False))
        for gate in COMPLIANCE_GATES
    }


def approval_errors(episode: Episode, stories: list[Story]) -> list[str]:
    errors: list[str] = []
    expected_story_count = 3 if episode.kind == "daily" else 1
    if len(episode.story_ids) != expected_story_count:
        errors.append(
            f"{episode.kind} episodes require exactly "
            f"{expected_story_count} stor{'y' if expected_story_count == 1 else 'ies'}"
        )
    if len(stories) != expected_story_count:
        errors.append("one or more episode stories no longer exist")
    if not episode.angle.strip():
        errors.append("a human editorial angle is mandatory")
    if not episode.script.strip():
        errors.append("the episode has no script")
        return errors
    canonical_script = join_sections(episode.kind, episode.sections)
    if episode.script.strip() != canonical_script.strip():
        errors.append("the script must match the canonical episode sections")
    if "[verify]" in episode.script.lower():
        errors.append("remove every [VERIFY] marker")
    if contains_advice(episode.script):
        errors.append("remove advisory or imperative language")
    if contains_credential_framing(episode.script):
        errors.append("remove credential or expert framing from the anchor")
    if contains_unspoken_acronym(episode.script):
        errors.append("spell every acronym as spoken, for example A-P-I")

    missing_sections = [
        key
        for key in REQUIRED_SECTIONS[episode.kind]
        if not episode.sections.get(key, "").strip()
    ]
    if missing_sections:
        errors.append(
            "missing required sections: " + ", ".join(missing_sections)
        )

    minimum, maximum = (
        (210, 225) if episode.kind == "daily" else (900, 1100)
    )
    actual_words = count_words(episode.script)
    if not minimum <= actual_words <= maximum:
        errors.append(
            f"script must contain {minimum}-{maximum} words; found {actual_words}"
        )

    for sentence in re.split(r"(?<=[.!?])\s+|\n+", episode.script):
        sentence = sentence.strip()
        if sentence and count_words(sentence) > 18:
            errors.append("every spoken sentence must contain at most 18 words")
            break

    if any(character in episode.script for character in ("—", "–", ";", "(", ")")):
        errors.append(
            "script contains voice-unsafe punctuation "
            "(dash, semicolon, or parentheses)"
        )
    if re.search(r"\d", episode.script):
        errors.append("spell every number as spoken; digits are not allowed")
    lowered = episode.script.lower()
    used_hype = sorted(word for word in HYPE_WORDS if word in lowered)
    if used_hype:
        errors.append("remove hype terms: " + ", ".join(used_hype))
    if contains_advice(episode.script):
        errors.append("script contains prohibited direct advice language")
    if not episode.title.strip() or len(episode.title) >= 60:
        errors.append("title must be present and shorter than 60 characters")
    if stories and not all(
        story.url in episode.description for story in stories
    ):
        errors.append("description must link every selected source")
    errors.extend(production_metadata_errors(episode))
    return errors
