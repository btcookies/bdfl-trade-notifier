from .franchise import Franchise


class LeagueFranchises:
    def __init__(self):
        self._franchises = {}

    def __repr__(self):
        return self._franchises.__repr__()

    def add_franchise(self, franchise: Franchise):
        self._franchises[franchise.franchise_id] = franchise

        return self._franchises

    def get_franchises(self):
        return self._franchises
