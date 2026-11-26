"""国家配置。以后要加新国家：在 COUNTRIES 里加一项，并在 shape_ok 里补一条号码形状规则即可。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Country:
    key: str          # 内部代号
    name: str         # 中文名（输出文件夹名）
    cc: str           # 国家码（不带 +）
    region: str       # phonenumbers 区域代码
    hints: tuple      # 文件夹/文件名里的提示词（小写），用于无法判断时的归属
    # 本地号码（去掉国家码和前导 0 之后）形状：首位集合 + 允许的长度范围
    first: str
    min_len: int
    max_len: int
    trunk0_first: bool  # 带前导 0 书写时是否优先考虑本国（印尼/泰国习惯写 0 开头）


COUNTRIES = [
    Country("IN", "印度", "91", "IN", ("india", "indian", "印度", "in"), "6789", 10, 10, False),
    Country("ID", "印尼", "62", "ID", ("indonesia", "印尼", "印度尼西亚", "id"), "8", 9, 12, True),
    Country("TH", "泰国", "66", "TH", ("thailand", "thai", "泰国", "th"), "689", 9, 9, True),
]
BY_KEY = {c.key: c for c in COUNTRIES}


def shape_ok(c: Country, nat: str) -> bool:
    return bool(nat) and nat[0] in c.first and c.min_len <= len(nat) <= c.max_len
