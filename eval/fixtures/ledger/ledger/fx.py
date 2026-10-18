from ledger.money import Money

# Units of each currency per 1 USD.
RATES = {"USD": 1.0, "EUR": 0.9, "GBP": 0.8}


def convert(amount, to_currency):
    if amount.currency == to_currency:
        return amount
    usd = amount.cents / RATES[amount.currency]
    return Money(round(usd * RATES[to_currency]), to_currency)
