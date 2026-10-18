import pytest

from ledger.account import Account
from ledger.errors import CurrencyMismatch, InsufficientFunds
from ledger.fx import convert
from ledger.money import Money
from ledger.report import statement, to_csv


def test_money():
    assert Money.from_str("12.5") == Money(1250)
    assert Money.from_str("-3.07") == Money(-307)
    assert str(Money(1250) + Money(5)) == "12.55 USD"
    with pytest.raises(CurrencyMismatch):
        Money(1, "USD") + Money(1, "EUR")


def test_account():
    a = Account("ana")
    a.deposit(Money(1000))
    a.withdraw(Money(300))
    assert a.balance == Money(700)
    with pytest.raises(InsufficientFunds):
        a.withdraw(Money(5000))
    with pytest.raises(ValueError):
        a.deposit(Money(0))


def test_reports():
    a = Account("ana")
    a.deposit(Money(1000))
    assert statement(a).splitlines()[-1] == "balance  10.00 USD"
    assert to_csv(a) == "kind,cents,currency\ndeposit,1000,USD\n"


def test_fx():
    assert convert(Money(1000, "USD"), "EUR") == Money(900, "EUR")
    assert convert(Money(800, "GBP"), "USD") == Money(1000, "USD")
