# https://en.wikipedia.org/wiki/Disjoint-set_data_structure

import collections
from typing import FrozenSet, Generic, Generator, Tuple, TypeVar

T = TypeVar("T")


class DisjointSet(Generic[T]):
    def __init__(self):
        self.parent = {}
        self.rank = {}

    def make_set(self, e: T):
        if e in self.parent:
            return
        self.parent[e] = e
        self.rank[e] = 0

    # find with path compression
    def find(self, e: T):
        self.make_set(e)
        prev = e
        while self.parent[e] != e:
            prev = e
            e = self.parent[e]
            self.parent[prev] = e
        return e

    # union by rank
    def union(self, x: T, y: T):
        x_root = self.find(x)
        y_root = self.find(y)
        if x_root == y_root:
            return  # already in the same set
        if self.rank[x] < self.rank[y]:
            x_root, y_root = y_root, x_root

        self.parent[y_root] = x_root
        if self.rank[x_root] == self.rank[y_root]:
            self.rank[x_root] += 1

    def sets(self) -> FrozenSet[FrozenSet[T]]:
        sets = collections.defaultdict(set)
        for e in self.parent:
            sets[self.find(e)].add(e)
        return frozenset(frozenset(s) for s in sets.values())

    def sorted(self) -> Tuple[Tuple[T, ...]]:
        """Sorted tuple of sorted tuples edition of sets()."""
        return tuple(sorted(tuple(sorted(s)) for s in self.sets()))
