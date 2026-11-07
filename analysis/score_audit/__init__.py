"""Audit harness for sustainability-score implementations (formula-agnostic).

interface.py        ScoreModel protocol every audited model is wrapped into
invariants.py       mathematical property checks (universal invariants + policy checks)
fixtures.py         deliberately simple TEST DOUBLES used only to prove the checks detect violations
teammate_adapter.py loader for the teammate's score.py (returns None until the file exists)
audit_score.py      CLI: reproduce scores for all 8 flats + run every check + write a report
"""
