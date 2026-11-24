"""Small pdfplumber helpers shared by the PDF statement parsers."""

from typing import Any

from pdfplumber.page import Page

_LINE_TOLERANCE = 2.0


def group_lines(page: Page) -> list[list[dict[str, Any]]]:
    """
    Group a page's words into visual lines.

    :param page: the PDF page.
    :return: lines top to bottom, each a list of words left to right.
    """
    words = sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict[str, Any]]] = []
    for word in words:
        if lines and abs(float(word["top"]) - float(lines[-1][0]["top"])) <= (
            _LINE_TOLERANCE
        ):
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]
