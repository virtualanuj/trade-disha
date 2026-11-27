"""Bullion lots and margin per contract (E28, E29): the parameters.

Each contract is a market with its own signals since E29, so there is no contract to
choose: what was `gold_contract` / `silver_contract` is dropped when an old version loads.
"""

import pytest
from pydantic import ValidationError

from tradedisha.parameters.model import Bullion, ParameterSet
from tradedisha.parameters.schema import describe


def test_each_contract_has_its_own_lots_defaulting_to_one() -> None:
    assert [Bullion().lots_for(c) for c in ("GOLD", "GOLDM", "SILVER", "SILVERM")] == [1] * 4
    b = Bullion(goldm_lots=3, silverm_lots=2)
    assert (b.lots_for("GOLDM"), b.lots_for("SILVERM"), b.lots_for("GOLD")) == (3, 2, 1)


@pytest.mark.parametrize(
    ("name", "pct"),
    [("GOLD", 9.0), ("GOLDM", 9.0), ("SILVER", 13.0), ("SILVERM", 13.0)],
)
def test_a_mini_blocks_its_metals_margin(name: str, pct: float) -> None:
    assert Bullion(gold_margin_pct=9.0, silver_margin_pct=13.0).margin_pct(name) == pct


@pytest.mark.parametrize("bad", [{"goldm_lots": 0}, {"silver_lots": 101}])
def test_lots_are_bounded(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Bullion.model_validate(bad)


def test_a_version_saved_with_one_lots_value_still_loads() -> None:
    """Versions stored before E28 have `lots`; it becomes every contract's default."""
    b = Bullion.model_validate({"lots": 4})
    assert [b.lots_for(c) for c in ("GOLD", "GOLDM", "SILVER", "SILVERM")] == [4, 4, 4, 4]
    kept = Bullion.model_validate({"lots": 4, "goldm_lots": 2})
    assert (kept.lots_for("GOLDM"), kept.lots_for("SILVER")) == (2, 4)
    assert "lots" not in kept.model_dump()


def test_a_version_that_chose_a_contract_still_loads() -> None:
    b = Bullion.model_validate({"gold_contract": "GOLDM", "silver_contract": "SILVER"})
    assert "gold_contract" not in b.model_dump()
    assert "silver_contract" not in b.model_dump()


def test_the_editor_has_lots_per_contract_and_no_contract_choice() -> None:
    specs = {s.path: s for s in describe(ParameterSet())}
    assert specs["bullion.goldm_lots"].kind == "integer"
    assert "bullion.gold_contract" not in specs
    assert "bullion.silver_contract" not in specs
    assert "bullion.lots" not in specs
