"""Money is whole cents in rand. Order references carry a Luhn check digit (P1)."""


def rand(cents: int) -> str:
    whole, part = divmod(cents, 100)
    text = f"R{whole:,}".replace(",", " ")
    return f"{text}.{part:02d}" if part else text


def parse_rand(text: str) -> int:
    """'R1 000.50' or '1000,50' -> 100050 cents. Raises ValueError on anything else."""
    cleaned = text.strip().upper().removeprefix("R").replace(" ", "").replace(" ", "")
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    cleaned = cleaned.replace(",", "")
    if not cleaned or cleaned.count(".") > 1:
        raise ValueError(text)
    whole, _, part = cleaned.partition(".")
    if not whole.isdigit() or (part and (not part.isdigit() or len(part) > 2)):
        raise ValueError(text)
    return int(whole) * 100 + int(part.ljust(2, "0") if part else 0)


def luhn_digit(number: str) -> int:
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def order_reference(order_id: int) -> str:
    base = str(order_id + 100)  # at least three digits, so the first reference is FLW-1010
    return f"FLW-{base}{luhn_digit(base)}"


def valid_reference(reference: str) -> bool:
    ref = reference.strip().upper()
    if not ref.startswith("FLW-"):
        return False
    digits = ref[4:]
    return len(digits) >= 4 and digits.isdigit() and luhn_digit(digits[:-1]) == int(digits[-1])
