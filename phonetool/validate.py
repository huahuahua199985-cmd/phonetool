"""用 phonenumbers 校验号码、识别运营商（在进程池里分块执行）。"""
import numpy as np
import phonenumbers
from phonenumbers import PhoneNumber, PhoneNumberType, carrier

from .countries import COUNTRIES

R_LANDLINE, R_NOTMOBILE, R_LENGTH, R_INVALID = 1, 2, 3, 4
REASONS = {R_LANDLINE: "固话", R_NOTMOBILE: "非手机号码类型", R_LENGTH: "位数不对", R_INVALID: "号段不存在/无效"}
MOBILE_TYPES = (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE)
UNKNOWN_CARRIER = "未知运营商"


def validate_chunk(args):
    cidx, arr = args
    cc = int(COUNTRIES[cidx].cc)
    region = COUNTRIES[cidx].region
    names, name_idx = [], {}
    good, good_c, bad, bad_r = [], [], [], []
    for n in arr.tolist():
        pn = PhoneNumber(country_code=cc, national_number=n)
        if phonenumbers.is_valid_number(pn):
            t = phonenumbers.number_type(pn)
            if t in MOBILE_TYPES:
                nm = carrier.name_for_number(pn, "en") or UNKNOWN_CARRIER
                ci = name_idx.get(nm)
                if ci is None:
                    ci = name_idx[nm] = len(names)
                    names.append(nm)
                good.append(n)
                good_c.append(ci)
                continue
            bad.append(n)
            bad_r.append(R_LANDLINE if t == PhoneNumberType.FIXED_LINE else R_NOTMOBILE)
            continue
        bad.append(n)
        poss = phonenumbers.is_possible_number_with_reason(pn)
        bad_r.append(R_INVALID if poss == phonenumbers.ValidationResult.IS_POSSIBLE else R_LENGTH)
    return (cidx, np.asarray(good, dtype=np.uint64), np.asarray(good_c, dtype=np.uint16), names,
            np.asarray(bad, dtype=np.uint64), np.asarray(bad_r, dtype=np.uint8))
