"""从任意文本里提取手机号并做形状分类（纯字符串规则，不调用 phonenumbers，保证速度）。"""
import os
import re
import zipfile

import numpy as np

from .countries import COUNTRIES, shape_ok

# 候选：可带 + ，数字之间允许 空格 - ( ) . 不间断空格
CAND = re.compile(r"(?<!\d)(\+[  ]?)?[(]?\d[\d  ()\-.]{4,}\d(?!\d)")
DATE_LIKE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$")
NONDIGIT = re.compile(r"\D+")

INTL00 = {"00" + c.cc for c in COUNTRIES}
ERR_UNKNOWN = -1          # 形似手机号但无法判断国家
MIN_DIGITS, MAX_DIGITS = 7, 15


def hint_for_path(rel_path: str, selected):
    """根据路径里的文件夹/文件名判断国家提示，返回国家 key 或 None。"""
    toks = set(re.split(r"[^0-9a-zA-Z一-鿿]+", rel_path.lower()))
    toks2 = rel_path.lower()
    for c in COUNTRIES:
        if c.key not in selected:
            continue
        for h in c.hints:
            if len(h) <= 2:
                if h in toks:
                    return c.key
            elif h in toks2:
                return c.key
    return None


class Classifier:
    def __init__(self, selected, hint=None):
        self.sel = [c for c in COUNTRIES if c.key in selected]
        self.hint = hint
        self.only = self.sel[0].key if len(self.sel) == 1 else None
        self.idx = {c.key: i for i, c in enumerate(COUNTRIES)}

    def _pick(self, cands, trunk, nat):
        """多个国家形状都吻合时的取舍：提示 > 规则优先级。"""
        if len(cands) == 1:
            return cands[0]
        if self.hint:
            for c in cands:
                if c.key == self.hint:
                    return c
        keys = {c.key: c for c in cands}
        n = len(nat)
        if n == 9 and "TH" in keys:      # 9 位本地号：泰国更常见
            return keys["TH"]
        if trunk:                        # 0 开头书写：印尼/泰国优先
            for c in cands:
                if c.trunk0_first:
                    return c
        return cands[0]                  # 无 0 的 10 位：印度优先（COUNTRIES 顺序）

    def classify(self, text):
        """返回 None（不是手机号）/ 'foreign'（其他国家）/ (kind, country_idx, nat_int|digits_str)
        kind: 'ok' 形状吻合；'err' 形似号码但形状不符。"""
        s = text.strip("  (")
        plus = s.startswith("+")
        d = NONDIGIT.sub("", s)
        L = len(d)
        if L < MIN_DIGITS or L > MAX_DIGITS + 2:
            return None
        if not plus and DATE_LIKE.match(s):
            return None
        intl = plus
        if not plus and d.startswith("00") and L >= 9:
            intl, d = True, d[2:]
            L -= 2
        if L > MAX_DIGITS:
            return None
        if intl:
            for c in COUNTRIES:
                if d.startswith(c.cc):
                    if c not in self.sel:
                        return "foreign"
                    nat = d[len(c.cc):]
                    if nat.startswith("0"):
                        nat = nat[1:]
                    return self._make(c, nat)
            return "foreign"
        trunk = d[0] == "0"
        if not trunk:
            # 不带 + 的国家码写法：6281…  、 91987…
            for c in self.sel:
                if d.startswith(c.cc):
                    nat = d[len(c.cc):]
                    if nat.startswith("0"):
                        nat = nat[1:]
                    if shape_ok(c, nat):
                        return ("ok", self.idx[c.key], int(nat))
        nat = d[1:] if trunk else d
        cands = [c for c in self.sel if shape_ok(c, nat)]
        if cands:
            c = self._pick(cands, trunk, nat)
            return ("ok", self.idx[c.key], int(nat))
        if trunk and L >= 8:
            # 0 开头但形状不符（固话/位数不对…）：归到提示国家或唯一选中的国家
            key = self.hint or self.only
            if key:
                c = next(x for x in self.sel if x.key == key)
                return self._make(c, nat)
            return ("err", ERR_UNKNOWN, d)
        return None

    def _make(self, c, nat):
        if nat and not nat.startswith("0") and len(nat) <= 15:
            if shape_ok(c, nat):
                return ("ok", self.idx[c.key], int(nat))
            return ("err", self.idx[c.key], int(nat))
        return ("err", ERR_UNKNOWN, c.cc + nat)

    def _split_trunk(self, text):
        """多个 0 开头的号码用空格粘在一起时拆开：每段必须单独是合法形状，拆不干净就不拆。"""
        toks = re.split(r"[ \u00a0]+", text.strip())
        n = len(toks)

        def starts0(t):
            t = t.lstrip("(")
            return t.startswith("0") and not t.startswith("00")

        if sum(1 for t in toks[1:] if starts0(t)) < 1 or not starts0(toks[0]):
            return None
        out, i = [], 0
        while i < n:
            hit = None
            for j in range(i + 1, min(n, i + 8) + 1):
                if j == n or starts0(toks[j]):
                    rr = self.classify(" ".join(toks[i:j]))
                    if rr and rr != "foreign" and rr[0] == "ok":
                        hit = (j, rr)
                        break
            if not hit:
                return None
            out.append(hit[1])
            i = hit[0]
        return out if len(out) > 1 else None

    def parse_candidate(self, text):
        r = self.classify(text)
        if r == "foreign":
            return ["foreign"]
        if r is not None and r[0] == "ok":
            if (" " in text or "\u00a0" in text) and text.count("0") >= 2:
                sp = self._split_trunk(text)
                if sp:
                    return sp
            return [r]
        has_space = " " in text or "\u00a0" in text
        if has_space:
            toks = re.split(r"[ \u00a0]+", text.strip())
            sp = self._split_trunk(text)
            if sp:
                return sp
            # 以 + 或 00 开头的片段是新号码的起点（多个国际格式号码粘在一起）
            segs, cur = [], []
            for t in toks:
                t2 = t.lstrip("(")
                if cur and (t2.startswith("+") or (t2[:4] in INTL00 and (len(t2) == 4 or len(t2) >= 11) and len(NONDIGIT.sub("", " ".join(cur))) >= 9)):
                    segs.append(cur)
                    cur = []
                cur.append(t)
            if cur:
                segs.append(cur)
            if len(segs) > 1:
                out = []
                for sg in segs:
                    out += self.parse_candidate(" ".join(sg))
                return out
        if r is not None and text.lstrip(" (").startswith("+"):
            return [r]                      # 明确带 + 的号码，形状不符就是错误号码，不再拆
        if has_space:
            sp = self._split_trunk(text)
            if sp:
                return sp
            out, i, n = [], 0, len(toks)
            while i < n:
                hit = None
                for j in range(min(n, i + 8), i, -1):   # 一个号码最多 8 组
                    rr = self.classify(" ".join(toks[i:j]))
                    if rr and rr != "foreign" and rr[0] == "ok":
                        hit = (j, rr)
                        break
                if hit:
                    out.append(hit[1])
                    i = hit[0]
                else:
                    i += 1
            if out:
                return out
            # 没有任何合法形状：找 0 开头的错误号码（固话等），避免被前面的杂项数字吞掉
            i = 0
            while i < n:
                hit = None
                for j in range(min(n, i + 8), i, -1):
                    rr = self.classify(" ".join(toks[i:j]))
                    if rr and rr != "foreign" and rr[0] == "err":
                        hit = (j, rr)
                        break
                if hit:
                    out.append(hit[1])
                    i = hit[0]
                else:
                    i += 1
            if out:
                return out
        return [r] if r is not None else []


def new_stats(n):
    return {"read": [0] * n, "foreign": 0}


def process_text(text, clf, acc, stats):
    """acc: {'keys': [list per country of ints], 'unk': set of str, 'errs': {country_idx: set(int)}}"""
    keys = acc["keys"]
    read = stats["read"]
    for m in CAND.finditer(text):
        for r in clf.parse_candidate(m.group(0)):
            if r == "foreign":
                stats["foreign"] += 1
                continue
            _, ci, nat = r
            if ci == ERR_UNKNOWN:
                acc["unk"].add(nat)
                read_unknown(stats)
            else:
                keys[ci].append(nat)
                read[ci] += 1


def read_unknown(stats):
    stats["unknown"] = stats.get("unknown", 0) + 1


# ---------------- 文件级读取 ----------------
TEXT_EXT = {".txt", ".csv", ".tsv", ".log"}
SHEET_EXT = {".xlsx", ".xls", ".xlsm", ".xlsb"}
TASK_BYTES = 48 * 1024 * 1024


def scan_files(folder):
    files = []
    for root, _, names in os.walk(folder):
        for n in names:
            if n.startswith(("~$", ".")):
                continue
            ext = os.path.splitext(n)[1].lower()
            if ext in TEXT_EXT or ext in SHEET_EXT:
                files.append(os.path.join(root, n))
    files.sort()
    return files


def _bom(path):
    with open(path, "rb") as f:
        b = f.read(4)
    if b.startswith(b"\xff\xfe") or b.startswith(b"\xfe\xff"):
        return "utf-16"
    return None


def plan_tasks(files, root):
    """把文件切成任务：大文本按字节区间切，表格整个文件一个任务。"""
    tasks = []
    for p in files:
        ext = os.path.splitext(p)[1].lower()
        rel = os.path.relpath(p, root)
        try:
            size = os.path.getsize(p)
        except OSError as e:
            tasks.append((p, rel, "error", 0, 0, f"无法访问：{e}"))
            continue
        if ext in SHEET_EXT:
            tasks.append((p, rel, "sheet", 0, size, None))
        elif _bom_safe(p):
            tasks.append((p, rel, "text16", 0, size, None))
        else:
            start = 0
            if size == 0:
                tasks.append((p, rel, "text", 0, 0, None))
            while start < size:
                end = min(size, start + TASK_BYTES)
                tasks.append((p, rel, "text", start, end, None))
                start = end
    return tasks


def _bom_safe(p):
    try:
        return _bom(p)
    except OSError:
        return None


def _read_text_range(path, start, end, clf, acc, stats):
    with open(path, "rb") as f:
        if start > 0:
            f.seek(start - 1)
            f.readline()          # 丢掉上一个任务负责的那一行
        pos = f.tell()
        buf = []
        size = 0
        while pos < end:
            line = f.readline()
            if not line:
                break
            pos += len(line)
            buf.append(line)
            size += len(line)
            if size >= 4 * 1024 * 1024:
                process_text(b"".join(buf).decode("latin-1"), clf, acc, stats)
                buf, size = [], 0
        if buf:
            process_text(b"".join(buf).decode("latin-1"), clf, acc, stats)


def _read_text16(path, clf, acc, stats):
    with open(path, "r", encoding="utf-16", errors="ignore") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            if not chunk.endswith("\n"):
                chunk += f.readline()
            process_text(chunk, clf, acc, stats)


def _cell_text(v):
    if v is None or v == "":
        return None
    if isinstance(v, float):
        if v != v:
            return None
        return str(int(v)) if v.is_integer() else None
    if isinstance(v, bool):
        return None
    return str(v)


def _read_sheet(path, clf, acc, stats):
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_path(path)
    for name in wb.sheet_names:
        sh = wb.get_sheet_by_name(name)
        batch, n = [], 0
        for row in sh.iter_rows():
            for v in row:
                t = _cell_text(v)
                if t:
                    batch.append(t)
            n += 1
            if n >= 20000:
                process_text("\n".join(batch), clf, acc, stats)
                batch, n = [], 0
        if batch:
            process_text("\n".join(batch), clf, acc, stats)


def run_task(args):
    """进程池里执行的单个读取任务。返回 dict，永不抛异常。"""
    task, selected = args
    path, rel, kind, start, end, preerr = task
    ncty = len(COUNTRIES)
    res = {"path": path, "rel": rel, "bytes": end - start, "error": preerr,
           "keys": [None] * ncty, "unk": [], "stats": None}
    if preerr:
        return res
    acc = {"keys": [[] for _ in range(ncty)], "unk": set()}
    stats = new_stats(ncty)
    try:
        clf = Classifier(selected, hint_for_path(rel, selected))
        if kind == "sheet":
            _read_sheet(path, clf, acc, stats)
        elif kind == "text16":
            _read_text16(path, clf, acc, stats)
        else:
            _read_text_range(path, start, end, clf, acc, stats)
    except Exception as e:  # noqa
        res["error"] = f"{type(e).__name__}: {e}"
        # 已读部分丢弃以免半截数据造成统计混乱
        return res
    for i in range(ncty):
        if acc["keys"][i]:
            res["keys"][i] = np.unique(np.asarray(acc["keys"][i], dtype=np.uint64))
    res["unk"] = list(acc["unk"])
    res["stats"] = stats
    return res
