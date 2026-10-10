import pytest

from problem1_part2.implementation.expectations import candidate_values, is_valid_for, matches
from problem1_part2.implementation.facets import FACETS, ValueType, get_facet
from problem1_part2.implementation.schemas import Expectation


def test_facet_ids_are_unique():
    ids = [facet.id for facet in FACETS]
    assert len(ids) == len(set(ids))


def test_get_facet_unknown_raises():
    with pytest.raises(KeyError):
        get_facet("does_not_exist")


@pytest.mark.parametrize(
    ("expectation", "value", "expected"),
    [
        (Expectation(values=["yes"]), "Yes", True),
        (Expectation(values=["yes"]), "no", False),
        (Expectation(version_spec="<1.30"), "1.29.1", True),
        (Expectation(version_spec="<1.30"), "1.30.0", False),
        (Expectation(version_spec=">=1.30"), "1.31.0rc1", True),
        (Expectation(version_spec="<1.30"), "latest", None),
    ],
)
def test_matches(expectation, value, expected):
    assert matches(expectation, value) is expected


def test_is_valid_for_checks_shape_and_domain():
    reverse_proxy = get_facet("reverse_proxy")
    version = get_facet("streamlit_version")
    assert is_valid_for(reverse_proxy, Expectation(values=["yes"]))
    assert not is_valid_for(reverse_proxy, Expectation(values=["maybe"]))
    assert not is_valid_for(reverse_proxy, Expectation(version_spec="<1"))
    assert is_valid_for(version, Expectation(version_spec="<1.30"))
    assert not is_valid_for(get_facet("error_message"), Expectation(values=["x"]))


def test_version_candidates_cover_both_sides_of_each_boundary():
    expectations = [Expectation(version_spec="<1.30"), Expectation(version_spec=">=1.35")]
    candidates = candidate_values(get_facet("streamlit_version"), expectations)

    for expectation in expectations:
        outcomes = {matches(expectation, value) for value in candidates}
        assert outcomes == {True, False}


def test_text_facets_have_no_candidates():
    facet = get_facet("error_message")
    assert facet.value_type is ValueType.TEXT
    assert candidate_values(facet, []) == []
