"""Bullion trading contracts and lots per contract (E28): the parameters."""

import pytest
from pydantic import ValidationError

from tradedisha.parameters.model import Bullion, ParameterSet
from tradedisha.parameters.schema import describe


def test_defaults_trade_the_full_contracts_one_lot_each() -> None:
    b = Bullion()
    assert (b.contract_for("GOLD"), b.contract_for("SILVER")) == ("GOLD", "SILVER")
    assert [b.lots_for(c) for c in ("GOLD", "GOLDM", "SILVER", "SILVERM")] == [1, 1, 1, 1]


def test_each_metal_picks_its_contract_and_each_contract_its_lots() -> None:
    b = Bullion(gold_contract="GOLDM", goldm_lots=3, silver_contract="SILVERM", silverm_lots=2)
    assert (b.contract_for("GOLD"), b.contract_for("SILVER")) == ("GOLDM", "SILVERM")
    assert (b.lots_for("GOLDM"), b.lots_for("SILVERM"), b.lots_for("GOLD")) == (3, 2, 1)


@pytest.mark.parametrize(
    "bad",
    [
        {"gold_contract": "SILVERM"},  # another metal's contract
        {"silver_contract": "GOLD"},
        {"goldm_lots": 0},
        {"silver_lots": 101},
    ],
)
def test_contracts_belong_to_their_metal_and_lots_are_bounded(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Bullion.model_validate(bad)


def test_a_version_saved_with_one_lots_value_still_loads() -> None:
    """Versions stored before E28 have `lots`; it becomes every contract's default."""
    b = Bullion.model_validate({"lots": 4})
    assert [b.lots_for(c) for c in ("GOLD", "GOLDM", "SILVER", "SILVERM")] == [4, 4, 4, 4]
    kept = Bullion.model_validate({"lots": 4, "goldm_lots": 2})
    assert (kept.lots_for("GOLDM"), kept.lots_for("SILVER")) == (2, 4)
    assert "lots" not in kept.model_dump()


def test_the_editor_offers_the_contracts_as_choices() -> None:
    specs = {s.path: s for s in describe(ParameterSet())}
    assert specs["bullion.gold_contract"].choices == ["GOLD", "GOLDM"]
    assert specs["bullion.silver_contract"].choices == ["SILVER", "SILVERM"]
    assert specs["bullion.goldm_lots"].kind == "integer"
    assert "bullion.lots" not in specs
