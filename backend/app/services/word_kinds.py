"""Part-of-speech families, for the weekly report's radar chart.

Imported wordbooks carry a free-form `part_of_speech` string: "n.", "noun",
"名词", "adj." all mean the same thing. A radar chart needs a fixed set of
axes or the shape changes every week, so every raw value is folded into one
of six families, and the axis order is fixed here.
"""

from __future__ import annotations

# The axes, in the order they are drawn. Six is enough to read a shape and
# few enough to label.
POS_AXES: tuple[tuple[str, str], ...] = (
    ("noun", "名词"),
    ("verb", "动词"),
    ("adjective", "形容词"),
    ("adverb", "副词"),
    ("connector", "介词·连词"),
    ("other", "其他"),
)

# Words that name a part of speech, longest first so "preposition" is tested
# before "position" could ever match.
_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "connector",
        (
            "preposition",
            "conjunction",
            "pronoun",
            "preposition/conjunction",
            "介词",
            "连词",
            "代词",
            "冠词",
            "介词连词",
            "介词/连词",
            "prep",
            "conj",
            "pron",
            "art",
            "article",
            "num",
            "numeral",
            "int",
            "interjection",
            "aux",
            "modal",
        ),
    ),
    ("adverb", ("adverb", "副词", "adv")),
    ("adjective", ("adjective", "形容词", "adj")),
    ("noun", ("noun", "名词", "n")),
    ("verb", ("verb", "动词", "v", "vt", "vi")),
)

# A bare "n" or "v" is a noun/verb only when it stands alone; inside a longer
# word it is part of something else ("adv" has a "v" in it).
_BARE = {"n", "v", "vt", "vi", "a", "adv", "adj", "prep", "conj", "pron"}


def normalize_part_of_speech(raw: str | None) -> str:
    """Fold a raw part-of-speech string into one of the POS_AXES families."""
    if not raw:
        return "other"
    value = raw.strip().lower()
    if not value:
        return "other"

    # A value like "n. / pl." or "adj; adv" may name more than one family;
    # the first axis it matches wins, in axis order.
    for family, markers in _MARKERS:
        for marker in markers:
            if len(marker) == 1:
                # Single letters must match the whole token.
                tokens = {token.strip(".;,()[]") for token in value.replace("/", " ").split()}
                if marker in tokens:
                    return family
                continue
            if marker in value:
                return family
    return "other"


def pos_axis_labels() -> list[dict[str, str]]:
    """Axis metadata for the client: the key it counts by and the label to draw."""
    return [{"key": key, "label": label} for key, label in POS_AXES]
