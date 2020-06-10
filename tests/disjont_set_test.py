from nanoemoji.disjoint_set import DisjointSet
import pytest


@pytest.mark.parametrize(
    "items, unions, expected_sets",
    [
        (
            range(1, 10),
            ((2, 3), (4, 5), (6, 7), (5, 6)),
            ((1,), (2, 3), (4, 5, 6, 7), (8,), (9,)),
        ),
        (
            range(10),
            ((0, 10), (1, 9), (2, 8), (0, 1), (0, 8)),
            ((0, 1, 2, 8, 9, 10), (3,), (4,), (5,), (6,), (7,)),
        ),
        (
            ("A", "B", "C", "D", "E", "duck", "an svg path"),
            (("C", "duck"), ("D", "an svg path"), ("A", "D")),
            (("A", "D", "an svg path"), ("B",), ("C", "duck"), ("E",)),
        ),
    ],
)
def test_disjoint_set(items, unions, expected_sets):
    dj = DisjointSet()
    for item in items:
        dj.make_set(item)
    for union in unions:
        dj.union(*union)
    assert dj.sorted() == expected_sets
