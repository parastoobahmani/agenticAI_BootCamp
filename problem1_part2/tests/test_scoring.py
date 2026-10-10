import math

import pytest

from problem1_part2.implementation.facets import get_facet
from problem1_part2.implementation.schemas import Expectation
from problem1_part2.implementation.scoring import UNLISTED_CAUSE, BeliefModel, entropy, prior_belief

YES = Expectation(values=["yes"])
NO = Expectation(values=["no"])


def test_prior_reserves_mass_for_unlisted_cause():
    belief = prior_belief({"h1": 0.6, "h2": 0.2}, unlisted_cause_prior=0.2)
    assert belief == pytest.approx({"h1": 0.6, "h2": 0.2, UNLISTED_CAUSE: 0.2})


def test_prior_without_hypotheses_is_all_unlisted():
    assert prior_belief({}, 0.2) == {UNLISTED_CAUSE: 1.0}


def test_prior_with_zero_confidences_is_uniform_over_listed():
    belief = prior_belief({"h1": 0.0, "h2": 0.0}, 0.2)
    assert belief["h1"] == pytest.approx(0.4)


def test_entropy_of_uniform_pair_is_one_bit():
    assert entropy({"a": 0.5, "b": 0.5}) == pytest.approx(1.0)


def test_update_moves_belief_towards_consistent_hypothesis():
    model = BeliefModel({"h1": {"reverse_proxy": YES}, "h2": {"reverse_proxy": NO}}, noise=0.15)
    belief = {"h1": 0.4, "h2": 0.4, UNLISTED_CAUSE: 0.2}

    after = model.update(belief, get_facet("reverse_proxy"), "yes")

    assert after["h1"] > belief["h1"]
    assert after["h2"] < belief["h2"]
    assert sum(after.values()) == pytest.approx(1.0)


def test_update_with_version_range():
    model = BeliefModel({"h1": {"streamlit_version": Expectation(version_spec="<1.30")}}, noise=0.15)
    belief = {"h1": 0.5, UNLISTED_CAUSE: 0.5}
    facet = get_facet("streamlit_version")

    assert model.update(belief, facet, "1.25.0")["h1"] > 0.5
    assert model.update(belief, facet, "1.35.0")["h1"] < 0.5


def test_discriminating_facet_has_positive_gain_and_shared_one_has_none():
    model = BeliefModel(
        {
            "h1": {"reverse_proxy": YES, "reproduces_locally": NO},
            "h2": {"reverse_proxy": NO, "reproduces_locally": NO},
        },
        noise=0.15,
    )
    belief = {"h1": 0.5, "h2": 0.5}

    assert model.information_gain(belief, get_facet("reverse_proxy")) > 0.3
    # Both predict the same answer: asking cannot tell them apart.
    assert model.information_gain(belief, get_facet("reproduces_locally")) == pytest.approx(0.0, abs=1e-9)
    # Nobody predicts anything about the browser.
    assert model.information_gain(belief, get_facet("browser")) == pytest.approx(0.0, abs=1e-9)


def test_gain_is_bounded_by_current_entropy():
    model = BeliefModel({"h1": {"reverse_proxy": YES}, "h2": {"reverse_proxy": NO}}, noise=0.01)
    belief = {"h1": 0.5, "h2": 0.5}
    gain = model.information_gain(belief, get_facet("reverse_proxy"))
    assert 0.9 < gain <= entropy(belief) + 1e-9


def test_text_facet_has_no_outcomes():
    model = BeliefModel({}, noise=0.15)
    assert model.information_gain({UNLISTED_CAUSE: 1.0}, get_facet("error_message")) == 0.0
    assert not math.isnan(model.information_gain({"h1": 0.5, "h2": 0.5}, get_facet("error_message")))
