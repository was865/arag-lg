"""題の答え（specs/034 R12）: 題集の cases は answers.py の計算そのもの（手で書いた数字は無い）。"""

from pathlib import Path

from harukaze_sim import answers

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "eval/assets/harukaze_plant/world.db"
GOLDEN = ROOT / "eval/suites/harukaze_plant/golden.yaml"


def test_golden_cases_are_the_computed_answers() -> None:
    text = GOLDEN.read_text()
    body = text.split("\ncases:\n", 1)[1]
    assert body == answers.draft(answers.compute_all(DB))


def test_every_case_has_facts_and_evidence() -> None:
    for c, a in answers.compute_all(DB):
        assert a.key_facts and all(f for f in a.key_facts), c.id
        assert a.evidence, c.id
        assert c.expect_tools or c.relevant_documents, c.id
    assert len(answers.CASES) >= 30
