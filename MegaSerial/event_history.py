"""Independent panel retention with a chronological index over the same events."""
from collections import OrderedDict, deque
from itertools import islice

DEFAULT_CAPACITY = 10000
MAX_CAPACITY = 1000000


class EventHistory:
    def __init__(self, recent_limit=6000):
        self._events = OrderedDict()
        self._recent = OrderedDict()
        self._recent_limit = recent_limit
        self.evicted_recently = False
        self._panels = {}
        self._next = 0
        self._capacities = {'11': DEFAULT_CAPACITY}

    def configure(self, capacities):
        if capacities == self._capacities:
            return
        events = list(self)
        self._capacities = dict(capacities)
        self.clear()
        for event in events:
            self.append(event)

    def append(self, event):
        ident = event.get('panel_id')
        if ident not in self._capacities:
            ident = '11'
        bucket = self._panels.setdefault(ident, deque())
        key = self._next
        self._next += 1
        self._events[key] = event
        self._recent[key] = None
        if len(self._recent) > self._recent_limit:
            self._recent.popitem(last=False)
        self.evicted_recently = False
        bucket.append(key)
        if len(bucket) > self._capacities[ident]:
            oldest = bucket.popleft()
            event = self._events.pop(oldest)
            self.evicted_recently = oldest in self._recent
            if self.evicted_recently:
                self._recent = OrderedDict.fromkeys(reversed(list(islice(
                    reversed(self._events), self._recent_limit))))
            return event
        return None

    def clear(self):
        self._events.clear()
        self._recent.clear()
        self._panels.clear()
        self._next = 0

    def __iter__(self):
        return iter(self._events.values())

    def __reversed__(self):
        return reversed(self._events.values())

    def __len__(self):
        return len(self._events)

    def __getitem__(self, index):
        if index == -1:
            return next(reversed(self))
        if index == 0:
            return next(iter(self))
        return list(self)[index]
