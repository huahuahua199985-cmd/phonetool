"""生成 1000 万+ 条测试数据，并用独立路径（phonenumbers.parse 字符串）算出标准答案。
用法: python gen_testdata.py <输出根目录> [规模系数，默认1.0]"""
import csv, json, multiprocessing as mp, os, random, sys, time
import numpy as np
import phonenumbers
from phonenumbers import carrier, PhoneNumberType

CC = {"IN": "91", "ID": "62", "TH": "66"}
KEYS = ["IN", "ID", "TH"]
MOBILE = (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE)


def truth_chunk(args):
    ci, nats = args
    cc = CC[KEYS[ci]]
    ok, names = [], []
    for n in nats.tolist():
        try:
            pn = phonenumbers.parse(f"+{cc}{n}", None)
            v = phonenumbers.is_valid_number(pn) and phonenumbers.number_type(pn) in MOBILE
        except Exception:
            v = False
        if v:
            ok.append(True); names.append(carrier.name_for_number(pn, "en") or "未知运营商")
        else:
            ok.append(False); names.append("")
    return ci, nats, ok, names


def gen_candidates(rng, scale):
    out = {}
    n = int(3_600_000 * scale)
    d0 = rng.integers(6, 10, n); out[0] = d0 * 10**9 + rng.integers(0, 10**9, n)
    n = int(3_400_000 * scale)
    ln = rng.choice([10, 11, 12], n, p=[.15, .5, .35]); rest = ln - 1
    out[1] = np.array([8 * 10**int(r) + rng.integers(0, 10**int(r)) if False else 0 for r in []], dtype=np.uint64)
    parts = []
    for L in (10, 11, 12):
        m = int((ln == L).sum())
        parts.append(8 * 10**(L - 1) + rng.integers(0, 10**(L - 1), m))
    # 少量 9 位
    m = int(30000 * scale); parts.append(8 * 10**8 + rng.integers(0, 10**8, m))
    out[1] = np.concatenate(parts)
    n = int(1_600_000 * scale)
    d0 = rng.choice([6, 8, 9], n); out[2] = d0 * 10**8 + rng.integers(0, 10**8, n)
    return {k: np.unique(v.astype(np.uint64)) for k, v in out.items()}


def gen_special(rng, scale):
    """固话 / 位数错误：只能用带 + 的写法；返回 {ci: array}"""
    s = {}
    m = int(120_000 * scale)
    land = {0: 10**9 + rng.integers(10**7, 10**8 - 1, m) + 10**9 * 0,  # 11xxxxxxxx 类（1 开头 10 位）
            1: 21 * 10**7 + rng.integers(0, 10**7, m),             # 21xxxxxxx
            2: 2 * 10**7 + rng.integers(0, 10**7, m)}              # 2xxxxxxx
    land[0] = 11 * 10**8 + rng.integers(0, 10**8, m)
    wl = {0: [9 * 10**8 + rng.integers(0, 10**8, m), 98 * 10**9 + rng.integers(0, 10**9, m)],   # 9位 / 11位
          1: [8 * 10**6 + rng.integers(0, 10**6, m), 8 * 10**12 + rng.integers(0, 10**12, m)],  # 7位 / 13位
          2: [8 * 10**7 + rng.integers(0, 10**7, m), 8 * 10**9 + rng.integers(0, 10**9, m)]}    # 8位 / 10位
    for ci in range(3):
        s[ci] = np.unique(np.concatenate([land[ci]] + wl[ci]).astype(np.uint64))
    return s


def forms_mixed(ci, nat, r):
    n = str(nat); cc = CC[KEYS[ci]]
    if ci == 0:
        f = [f"+91{n}", f"91{n}", f"+91 {n[:5]} {n[5:]}", f"+91-{n[:5]}-{n[5:]}", f"(+91) {n[:5]}-{n[5:]}",
             f"0091 {n}", n, f"{n[:5]} {n[5:]}", f"+91 {n[:3]}-{n[3:6]}-{n[6:]}"]
        if n[0] != "8":
            f += [f"0{n}", f"0{n[:5]} {n[5:]}"]
    elif ci == 1:
        f = [f"+62{n}", f"62{n}", f"+62 {n[:3]}-{n[3:7]}-{n[7:]}", f"+62 (0){n[:3]} {n[3:7]} {n[7:]}",
             f"0062{n}", f"+62-{n[:3]}-{n[3:]}"]
        if len(n) >= 10:
            f += [f"0{n}", f"0{n[:3]}-{n[3:7]}-{n[7:]}", f"(0{n[:3]}) {n[3:7]}-{n[7:]}", f"0{n[:3]} {n[3:7]} {n[7:]}", f"0{n[:3]}.{n[3:7]}.{n[7:]}"]
    else:
        f = [f"+66{n}", f"66{n}", f"+66 {n[:2]} {n[2:5]} {n[5:]}", f"+66-{n[:2]}-{n[2:5]}-{n[5:]}", f"+66 (0) {n[:2]} {n[2:5]} {n[5:]}",
             f"0{n}", f"0{n[:2]}-{n[2:5]}-{n[5:]}", f"0{n[:2]} {n[2:5]} {n[5:]}", f"(0{n[:2]}) {n[2:5]}-{n[5:]}"]
    return r.choice(f)


def forms_hint(ci, nat, r):
    n = str(nat)
    return r.choice([n, forms_mixed(ci, nat, r), forms_mixed(ci, nat, r)])


def forms_plus(ci, nat, r):
    n = str(nat); cc = CC[KEYS[ci]]
    return r.choice([f"+{cc}{n}", f"+{cc} {n[:3]} {n[3:]}", f"+{cc}-{n[:2]}-{n[2:]}", f"00{cc}{n}"])


NAMES = ["Budi", "Siti", "Somchai", "Amit", "Priya", "Dewi", "Ratree", "Rahul", "Agus", "Napat"]
CITIES = ["Jakarta", "Mumbai", "Bangkok", "Delhi", "Surabaya", "Chiang Mai", "Pune"]
NOISE = ["ORD-20240115-8812", "2024-01-15 10:23:45", "price 1,299.50", "id 12345678901234567890", "ref#99887766554433221100",
         "2023/12/31", "v2.3.14", "backup 20240101", "zip 560001"]
FOREIGN = ["+1 415 555 2671", "+44 7911 123456", "+86 138 0013 8000", "+81 90-1234-5678", "+65 9123 4567"]


def render_line(rec, r, fmt, kind):
    """rec: (ci, nat, mode) mode: 0 mixed, 1 hint, 2 plus-only, 3 raw unknown-string"""
    ci, nat, mode = rec
    if mode == 3:
        s = nat  # 字符串 0xxxxxxxxx
        return f"{s[:3]}-{s[3:]}" if r.random() < .5 else f"({s[:3]}) {s[3:]}"
    if mode == 2:
        return forms_plus(ci, nat, r)
    return forms_hint(ci, nat, r) if mode == 1 else forms_mixed(ci, nat, r)


def write_file(job):
    path, kind, recs, seed = job
    r = random.Random(seed)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    foreign_n = 0
    extra = [0, 0, 0]
    if kind == "txt":
        with open(path, "w", encoding="utf-8") as f:
            for rec in recs:
                s = render_line(rec, r, "txt", kind)
                x = r.random()
                if x < .06: s = f"tel: {s} (whatsapp)"
                elif x < .08: s = f"{r.choice(NAMES)} {s}"
                elif x < .09: s = r.choice(NOISE) + " " + s
                elif x < .10 and rec[2] != 3:
                    s = s + " " + render_line(rec, r, "txt", kind); extra[rec[0]] += 1  # 同行同号写两次
                f.write(s + "\n")
                if r.random() < .004:
                    f.write(r.choice(NOISE) + "\n")
                if r.random() < .004:
                    f.write(r.choice(FOREIGN) + "\n"); foreign_n += 1
    elif kind == "csv":
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("name,city,phone,note,phone2\n")
            for rec in recs:
                s = render_line(rec, r, "csv", kind)
                if "," in s: s = f'"{s}"'
                note = r.choice(["call after 5pm", "vip", '"hello, world"', "", "new"])
                f.write(f"{r.choice(NAMES)},{r.choice(CITIES)},{s},{note},\n")
                if r.random() < .004:
                    f.write(f"x,y,{r.choice(FOREIGN)},,\n"); foreign_n += 1
    elif kind == "xlsx":
        import xlsxwriter
        wb = xlsxwriter.Workbook(path, {"constant_memory": True})
        ws = wb.add_worksheet("data"); ws.write_row(0, 0, ["name", "phone", "city"])
        row = 1
        for rec in recs:
            s = render_line(rec, r, "xlsx", kind)
            if s.isdigit() and not s.startswith("0") and r.random() < .5:
                ws.write_number(row, 1, int(s))
            else:
                ws.write_string(row, 1, s)
            ws.write_string(row, 0, r.choice(NAMES)); ws.write_string(row, 2, r.choice(CITIES))
            row += 1
            if r.random() < .004:
                ws.write_string(row, 1, r.choice(FOREIGN)); row += 1; foreign_n += 1
        wb.close()
    return path, len(recs), foreign_n, extra


def main():
    root = sys.argv[1]; scale = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    t0 = time.time(); rng = np.random.default_rng(20260101)
    os.makedirs(root, exist_ok=True)
    data_dir = os.path.join(root, "input"); truth_dir = os.path.join(root, "truth")
    os.makedirs(truth_dir, exist_ok=True)
    cand = gen_candidates(rng, scale); special = gen_special(rng, scale)
    print("candidates", {k: len(v) for k, v in cand.items()}, flush=True)
    # ---- 标准答案：独立路径判定 ----
    jobs = []
    for ci in range(3):
        allu = np.unique(np.concatenate([cand[ci], special[ci]]))
        for s in range(0, len(allu), 50000):
            jobs.append((ci, allu[s:s + 50000]))
    truth = {ci: {"nat": [], "ok": [], "name": []} for ci in range(3)}
    with mp.get_context("spawn").Pool() as pool:
        for ci, nats, ok, names in pool.imap_unordered(truth_chunk, jobs):
            truth[ci]["nat"].append(nats); truth[ci]["ok"].extend(ok); truth[ci]["name"].extend(names)
        print("truth done", round(time.time() - t0), "s", flush=True)
        exp = {"countries": {}}
        uniq_recs = {}
        for ci in range(3):
            nat = np.concatenate(truth[ci]["nat"]); ok = np.array(truth[ci]["ok"]); nm = np.array(truth[ci]["name"])
            o = np.argsort(nat); nat, ok, nm = nat[o], ok[o], nm[o]
            names = sorted(set(nm[ok].tolist())); idx = {n: i for i, n in enumerate(names)}
            cidx = np.array([idx[x] for x in nm[ok].tolist()], dtype=np.uint16)
            np.savez(os.path.join(truth_dir, f"{KEYS[ci]}.npz"), valid=nat[ok], carrier=cidx, names=np.array(names), invalid=nat[~ok])
            exp["countries"][KEYS[ci]] = {"unique": int(len(nat)), "valid": int(ok.sum()), "invalid": int((~ok).sum()),
                                          "carriers": {n: int((nm[ok] == n).sum()) for n in names}}
            is_special = np.isin(nat, special[ci])
            uniq_recs[ci] = (nat, is_special)
        # ---- 组装记录：每个唯一号码至少出现一次，约 45% 再重复一次（换写法/换文件）----
        recs = []   # (ci, nat, mode)
        hint_recs = {0: [], 1: [], 2: []}
        for ci in range(3):
            nat, sp = uniq_recs[ci]
            dup = rng.random(len(nat)) < .45
            nat_all = np.concatenate([nat, nat[dup]]); sp_all = np.concatenate([sp, sp[dup]])
            ish = (rng.random(len(nat_all)) < .12) & ~sp_all
            for x, s_, h in zip(nat_all.tolist(), sp_all.tolist(), ish.tolist()):
                (hint_recs[ci] if h else recs).append((ci, x, 2 if s_ else 0))
        # 无法识别国家的固话串：0 + 以 2-5/7 开头，8~10 位；每个写 1~2 次
        unk = set()
        ur = random.Random(7)
        while len(unk) < int(30000 * scale):
            unk.add("0" + str(ur.choice([2, 3, 4, 5])) + "".join(ur.choice("0123456789") for _ in range(ur.choice([7, 8, 9]))))
        unk = sorted(unk)
        for s in unk:
            recs.append((0, s, 3));
            if ur.random() < .4: recs.append((0, s, 3))
        random.Random(1).shuffle(recs)
        total_records = len(recs) + sum(len(v) for v in hint_recs.values())
        # ---- 分文件 ----
        jobs = []; seed = 0
        def add(prefix, kind, rs, per):
            nonlocal seed
            for i in range(0, len(rs), per):
                seed += 1
                jobs.append((os.path.join(data_dir, f"{prefix}_{seed:04d}.{kind}"), kind, rs[i:i + per], seed))
        i = 0; n = len(recs)
        a = int(n * .55); b = int(n * .85)
        add("mixed/txt/list", "txt", recs[:a], 450_000)
        add("mixed/csv/contacts", "csv", recs[a:b], 450_000)
        add("mixed/xlsx/book", "xlsx", recs[b:], 120_000)
        hname = {0: "india_data", 1: "印尼数据", 2: "thailand"}
        for ci in range(3):
            rs = hint_recs[ci]; h = len(rs)
            add(f"{hname[ci]}/h", "txt", rs[:h // 2], 450_000)
            add(f"{hname[ci]}/h", "csv", rs[h // 2:h * 3 // 4], 450_000)
            add(f"{hname[ci]}/h", "xlsx", rs[h * 3 // 4:], 120_000)
        foreign = 0
        extra_read = [0, 0, 0]
        for p, c, fn, ex_ in pool.imap_unordered(write_file, jobs):
            foreign += fn
            for q in range(3): extra_read[q] += ex_[q]
        print("files written", len(jobs), round(time.time() - t0), "s", flush=True)
    # ---- 特殊文件 ----
    sp = os.path.join(data_dir, "special"); os.makedirs(sp, exist_ok=True)
    open(os.path.join(sp, "empty.txt"), "w").close()
    open(os.path.join(sp, "bad.xlsx"), "wb").write(os.urandom(5000))
    open(os.path.join(sp, "bad.xls"), "wb").write(b"not an excel")
    open(os.path.join(sp, "readme.docx"), "w").write("ignored")
    exp["failed_files"] = ["special/bad.xlsx", "special/bad.xls"]
    exp["total_records"] = total_records
    exp["unknown_country_unique"] = len(unk)
    exp["foreign_min"] = foreign
    # 每国读取条数：非 mode3 记录
    exp["read"] = {}
    allr = {0: 0, 1: 0, 2: 0}
    for r_ in recs:
        if r_[2] != 3: allr[r_[0]] += 1
    for ci in range(3): allr[ci] += len(hint_recs[ci])
    for ci in range(3): exp["countries"][KEYS[ci]]["read"] = allr[ci] + extra_read[ci]
    exp["unknown_read"] = sum(1 for r_ in recs if r_[2] == 3)
    json.dump(exp, open(os.path.join(truth_dir, "expected.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(exp, ensure_ascii=False, indent=1))
    print("total records", total_records, "elapsed", round(time.time() - t0), "s")


if __name__ == "__main__":
    mp.freeze_support(); main()
