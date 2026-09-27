import argparse

import pytest

from scripts.release import build_commit_message, parse_commit_summary


def test_parse_commit_summary_trims_surrounding_whitespace() -> None:
    assert parse_commit_summary("  feat: add allocation preview  ") == (
        "feat: add allocation preview"
    )


@pytest.mark.parametrize("summary", ["", "   ", "feat: first line\nfix: second line"])
def test_parse_commit_summary_rejects_empty_or_multiline_values(summary: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_commit_summary(summary)


def test_build_commit_message_includes_version_and_summary() -> None:
    assert build_commit_message("0.2.0", "feat: add allocation preview") == (
        "release v0.2.0: feat: add allocation preview"
    )
