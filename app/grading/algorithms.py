"""
grading/algorithms.py
=====================
Pure Python Algorithm Engine for CBC Computations
Back To Front Development

SECURITY:
    - Fail-Fast Architecture: Uses explicit validation to trap impossible
      score states before they can propagate to the database.
"""


class CBCTranslator:
    """
    Stateless translator for CBC competency scaling.
    """

    @staticmethod
    def translate_percentage(score: float) -> int:
        """
        Translates a raw 0-100 percentage into the 1-4 CBC Competency Scale.

        Scale Definitions:
            4: Exceeding Expectation (80 - 100)
            3: Meeting Expectation (65 - 79.9)
            2: Approaching Expectation (50 - 64.9)
            1: Below Expectation (0 - 49.9)
        """
        if not isinstance(score, (int, float)):
            raise ValueError("score must be a numeric percentage")
        if not 0.0 <= score <= 100.0:
            raise ValueError("score must be between 0 and 100")

        if score >= 80.0:
            return 4
        if score >= 65.0:
            return 3
        if score >= 50.0:
            return 2
        return 1
