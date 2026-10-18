import csv
import io


def statement(account):
    lines = [f"Statement for {account.owner}"]
    for kind, amount in account.transactions:
        lines.append(f"{kind:<9}{amount}")
    lines.append(f"{'balance':<9}{account.balance}")
    return "\n".join(lines)


def to_csv(account):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["kind", "cents", "currency"])
    for kind, amount in account.transactions:
        writer.writerow([kind, amount.cents, amount.currency])
    return buf.getvalue()
