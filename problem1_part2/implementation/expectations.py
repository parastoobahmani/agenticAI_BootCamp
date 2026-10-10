"""Matching observed / candidate facet values against hypothesis expectations."""

from __future__ import annotations

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from problem1_part2.implementation.facets import Facet, ValueType
from problem1_part2.implementation.schemas import Expectation

# Versions far outside any real Streamlit/Python range, used to cover the open ends
# of version specifiers when enumerating candidate outcomes.
_LOWEST_VERSION = Version("0.0.1")
_HIGHEST_VERSION = Version("9999")


def parse_version(value: str) -> Version | None:
    try:
        return Version(value)
    except InvalidVersion:
        return None


def matches(expectation: Expectation, value: str) -> bool | None:
    """Whether ``value`` satisfies ``expectation``; ``None`` when it cannot be judged."""
    if expectation.values is not None:
        return value.strip().lower() in expectation.values
    version = parse_version(value)
    if version is None:
        return None
    return SpecifierSet(expectation.version_spec).contains(version, prereleases=True)


def is_valid_for(facet: Facet, expectation: Expectation) -> bool:
    """Whether the expectation has the right shape for the facet it is attached to."""
    if facet.value_type is ValueType.CATEGORY:
        return expectation.values is not None and set(expectation.values) <= set(facet.values)
    if facet.value_type is ValueType.VERSION:
        return expectation.version_spec is not None
    return False


def candidate_values(facet: Facet, expectations: list[Expectation]) -> list[str]:
    """Possible answers to a facet, fine-grained enough to tell the expectations apart.

    Category facets use their declared values. For version facets we take every
    boundary version mentioned by a specifier and the points just below/above it,
    which covers each region of the version line that the specifiers distinguish.
    """
    if facet.value_type is ValueType.CATEGORY:
        return list(facet.values)
    if facet.value_type is not ValueType.VERSION:
        return []

    boundaries = {
        boundary
        for expectation in expectations
        if expectation.version_spec
        for spec in SpecifierSet(expectation.version_spec)
        if (boundary := parse_version(spec.version.removesuffix(".*"))) is not None
    }
    if not boundaries:
        return []
    points = {_LOWEST_VERSION, _HIGHEST_VERSION}
    for boundary in boundaries:
        base = boundary.base_version
        points.update({boundary, Version(f"{base}.dev0"), Version(f"{base}.post1")})
    return [str(point) for point in sorted(points)]
