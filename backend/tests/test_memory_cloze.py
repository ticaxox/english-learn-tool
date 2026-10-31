"""Cloze generation for the spelling trainer."""

from app.services.memory import CLOZE_MODES, _cloze


def test_full_blanks_every_letter() -> None:
    assert _cloze("harbor", "full") == "______"


def test_first_letter_keeps_only_the_first() -> None:
    assert _cloze("harbor", "first_letter") == "h_____"


def test_partial_keeps_the_first_third() -> None:
    assert _cloze("harbor", "partial") == "ha____"


def test_middle_keeps_first_and_last_and_varies_the_rest() -> None:
    samples = {_cloze("opportunity", "middle") for _ in range(40)}

    assert len(samples) > 1, "the middle blanks must not be fixed"
    for sample in samples:
        assert len(sample) == len("opportunity")
        assert sample[0] == "o"
        assert sample[-1] == "y"
        assert 1 <= sample[1:-1].count("_") <= len(sample) - 2


def test_middle_on_two_letter_words_is_a_no_op() -> None:
    assert _cloze("go", "middle") == "go"


def test_modes_are_the_on_the_wire_values() -> None:
    assert CLOZE_MODES == ("full", "partial", "first_letter", "middle")
