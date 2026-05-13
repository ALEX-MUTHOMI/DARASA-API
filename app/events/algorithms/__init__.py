"""Deterministic algorithms for the event backbone.

The database layer stores facts, but the safety rules that decide whether a
fact is valid live here.  Keeping these functions side-effect-free makes the
event backbone easier to test offline and safer to adapt to a future broker.
"""
