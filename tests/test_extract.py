from phonetool.extract import Classifier

ALL = ["IN", "ID", "TH"]


def one(text, **kw):
    out = Classifier(ALL, **kw).parse_candidate(text)
    assert len(out) == 1, out
    return out[0]


def test_same_number_many_writings():
    forms = ["081234567890", "6281234567890", "+62 812-3456-7890", "+62 (0)812 3456 7890", "0062 81234567890"]
    assert {one(f) for f in forms} == {("ok", 1, 81234567890)}


def test_india_and_thailand():
    assert one("+91 98765 43210") == ("ok", 0, 9876543210)
    assert one("09876543210") == ("ok", 0, 9876543210)
    assert one("081-234-5678") == ("ok", 2, 812345678)
    assert one("+66 (0) 81 234 5678") == ("ok", 2, 812345678)


def test_landline_is_error_not_dropped():
    assert one("+62 21 5551234")[0] == "err"
    assert one("021-5551234")[0] == "err"


def test_glued_numbers_and_noise():
    c = Classifier(ALL)
    assert len(c.parse_candidate("0812345678 0856789012")) == 2
    assert c.parse_candidate("2024-01-15") == []
    assert c.parse_candidate("+1 415 555 2671") == ["foreign"]


def test_hint_breaks_ties():
    assert one("812345678", hint="ID")[1] == 1
    assert one("8123456789", hint="ID")[1] == 1
    assert one("8123456789")[1] == 0   # 无提示：10 位优先当印度
