from ledger.errors import InsufficientFunds
from ledger.money import Money


class Account:
    def __init__(self, owner, currency="USD"):
        self.owner = owner
        self.currency = currency
        self.transactions = []  # list of (kind, Money)

    @property
    def balance(self):
        total = Money(0, self.currency)
        for kind, amount in self.transactions:
            total = total + amount if kind == "deposit" else total - amount
        return total

    def deposit(self, amount):
        if amount.cents <= 0:
            raise ValueError("deposit must be positive")
        self.transactions.append(("deposit", amount))

    def withdraw(self, amount):
        if amount.cents <= 0:
            raise ValueError("withdrawal must be positive")
        if amount.cents > self.balance.cents:
            raise InsufficientFunds(str(amount))
        self.transactions.append(("withdraw", amount))
