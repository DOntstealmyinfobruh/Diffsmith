from dataclasses import dataclass

from ledger.errors import CurrencyMismatch


@dataclass(frozen=True)
class Money:
    """An amount stored as integer cents, so arithmetic is exact."""

    cents: int
    currency: str = "USD"

    @classmethod
    def from_str(cls, text, currency="USD"):
        whole, _, frac = text.strip().partition(".")
        frac = (frac + "00")[:2]
        sign = -1 if whole.startswith("-") else 1
        return cls(sign * (abs(int(whole)) * 100 + int(frac)), currency)

    def _check(self, other):
        if self.currency != other.currency:
            raise CurrencyMismatch(f"{self.currency} vs {other.currency}")

    def __add__(self, other):
        self._check(other)
        return Money(self.cents + other.cents, self.currency)

    def __sub__(self, other):
        self._check(other)
        return Money(self.cents - other.cents, self.currency)

    def __str__(self):
        sign = "-" if self.cents < 0 else ""
        c = abs(self.cents)
        return f"{sign}{c // 100}.{c % 100:02d} {self.currency}"
