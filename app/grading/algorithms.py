"""
grading/algorithms.py
=====================
Pure Python Algorithm Engine for CBC Computations
Back To Front Development

SECURITY:
    - Fail-Fast Architecture: Uses assertions to immediately trap impossible
      states (e.g. scores > 100) before they can propagate to the database.
"""

class CBCTranslator:
    """
    Stateless translator for CBC competency scaling.
    """

    @staticmethod
    def translate_percentage(score: float) -> int:
        """
        Translates a raw 0-100 percentage into the standard 1-4 CBC Competency Scale.
        
        Scale Definitions:
            4: Exceeding Expectation (80 - 100)
            3: Meeting Expectation (65 - 79.9)
            2: Approaching Expectation (50 - 64.9)
            1: Below Expectation (0 - 49.9)
        """
        assert isinstance(score, (int, float)), f"Score must be a number, got {type(score)}"
        assert 0.0 <= score <= 100.0, f"Critical Fault: Score {score} is out of bounds (0-100)."

        if score >= 80.0:
            return 4
        elif score >= 65.0:
            return 3
        elif score >= 50.0:
            return 2
        else:
            return 1
