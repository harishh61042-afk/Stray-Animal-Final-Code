"""Pagination for plain Python lists, with the attributes ``macros/ui.html: pagination`` reads."""


class ListPagination:
    """Same attributes as Flask-SQLAlchemy's ``Pagination`` (``items``, ``page``, ``pages``, ``total`` ...)."""

    def __init__(self, items, page=1, per_page=10):
        items = list(items)
        self.total = len(items)
        self.per_page = max(1, int(per_page))
        self.pages = max(1, -(-self.total // self.per_page))
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 1
        self.page = min(max(1, page), self.pages)
        start = (self.page - 1) * self.per_page
        self.items = items[start:start + self.per_page]

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    def iter_pages(self, left_edge=2, left_current=2, right_current=4, right_edge=2):
        """Page numbers with ``None`` where the list is cut short (same rules as Flask-SQLAlchemy)."""
        last = 0
        for number in range(1, self.pages + 1):
            if (
                number <= left_edge
                or (self.page - left_current <= number < self.page + right_current)
                or number > self.pages - right_edge
            ):
                if last + 1 != number:
                    yield None
                yield number
                last = number
        if last != self.pages and last:
            yield None
