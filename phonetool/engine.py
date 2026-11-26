"""主流程：扫描 → 分块提取 → 跨文件去重 → 校验+分运营商 → 分包输出 → 报告。"""
import json
import multiprocessing as mp
import os
import time
from collections import defaultdict

import numpy as np

from . import __version__
from .countries import COUNTRIES
from .extract import plan_tasks, run_task, scan_files
from .output import XLSX_MAX_ROWS, safe_name, write_errors_csv, write_pack
from .validate import REASONS, UNKNOWN_CARRIER, validate_chunk

MERGE_THRESHOLD = 6_000_000
VALIDATE_CHUNK = 100_000


class Cancelled(Exception):
    pass


def _merge(parts):
    if len(parts) == 1:
        return parts[0]
    return np.unique(np.concatenate(parts))


def run(cfg, progress=None, cancel=None):
    """cfg: input_dir, output_dir, countries(list of keys), pack_size, fmt('txt'|'xlsx'),
    with_cc(bool), without_cc(bool), workers(optional). 返回 report dict。"""
    t0 = time.time()
    progress = progress or (lambda frac, msg: None)
    cancel = cancel or (lambda: False)
    selected = list(cfg["countries"])
    workers = cfg.get("workers") or max(1, (os.cpu_count() or 2) - 1)
    pack_size = max(1, int(cfg.get("pack_size", 100000)))
    fmt = cfg.get("fmt", "txt")
    if fmt == "xlsx":
        pack_size = min(pack_size, XLSX_MAX_ROWS)
    out_dir = cfg["output_dir"]
    n = len(COUNTRIES)

    files = scan_files(cfg["input_dir"])
    tasks = plan_tasks(files, cfg["input_dir"])
    total_bytes = sum(max(t[4] - t[3], 1) for t in tasks) or 1
    progress(0.0, f"找到 {len(files)} 个文件，开始读取…")

    ctx = mp.get_context("spawn")
    parts = [[] for _ in range(n)]
    parts_len = [0] * n
    read = [0] * n
    unk_read = 0
    foreign = 0
    unk_set = set()
    failed = {}
    ok_files = set()
    done_bytes = 0

    with ctx.Pool(workers) as pool:
        # ---- 阶段1：读取 ----
        for res in pool.imap_unordered(run_task, [(t, selected) for t in tasks], chunksize=1):
            if cancel():
                pool.terminate()
                raise Cancelled()
            done_bytes += max(res["bytes"], 1)
            if res["error"]:
                failed.setdefault(res["rel"], res["error"])
            else:
                ok_files.add(res["rel"])
                st = res["stats"]
                for i in range(n):
                    read[i] += st["read"][i]
                    if res["keys"][i] is not None:
                        parts[i].append(res["keys"][i])
                        parts_len[i] += len(res["keys"][i])
                foreign += st["foreign"]
                unk_read += st.get("unknown", 0)
                unk_set.update(res["unk"])
                for i in range(n):
                    if parts_len[i] > MERGE_THRESHOLD:
                        parts[i] = [_merge(parts[i])]
                        parts_len[i] = len(parts[i][0])
            progress(0.45 * done_bytes / total_bytes, f"读取中… {done_bytes / total_bytes:.0%}")

        uniq = [(_merge(p) if p else np.empty(0, dtype=np.uint64)) for p in parts]
        del parts
        unique_counts = [len(u) for u in uniq]
        progress(0.45, f"去重完成：{sum(unique_counts):,} 个唯一号码，开始校验…")

        # ---- 阶段2：校验 + 运营商 ----
        jobs = []
        for ci in range(n):
            u = uniq[ci]
            for s in range(0, len(u), VALIDATE_CHUNK):
                jobs.append((ci, u[s:s + VALIDATE_CHUNK]))
        total_jobs = max(len(jobs), 1)
        groups = defaultdict(list)           # (ci, carrier) -> [arrays]
        errs = [[] for _ in range(n)]        # per country: (nat arr, reason arr)
        for k, r in enumerate(pool.imap_unordered(validate_chunk, jobs, chunksize=1)):
            if cancel():
                pool.terminate()
                raise Cancelled()
            ci, good, good_c, names, bad, bad_r = r
            if len(good):
                for j, nm in enumerate(names):
                    groups[(ci, nm)].append(good[good_c == j])
            if len(bad):
                errs[ci].append((bad, bad_r))
            progress(0.45 + 0.30 * (k + 1) / total_jobs, f"校验中… {(k + 1) / total_jobs:.0%}")
        del uniq

        # ---- 阶段3：输出 ----
        write_jobs = []
        pack_counts = defaultdict(int)       # (ci, carrier) -> packs
        valid_counts = defaultdict(int)
        formats = []
        if cfg.get("with_cc", True):
            formats.append(("带国家码", True))
        if cfg.get("without_cc"):
            formats.append(("不带国家码", False))
        if not formats:
            formats = [("带国家码", True)]
        ext = "xlsx" if fmt == "xlsx" else "txt"
        for (ci, nm), arrs in sorted(groups.items()):
            c = COUNTRIES[ci]
            arr = np.sort(np.concatenate(arrs))
            valid_counts[(ci, nm)] = len(arr)
            folder = os.path.join(out_dir, c.name, safe_name(nm))
            npk = (len(arr) + pack_size - 1) // pack_size
            pack_counts[(ci, nm)] = npk
            for k in range(npk):
                chunk = arr[k * pack_size:(k + 1) * pack_size]
                for label, with_cc in formats:
                    prefix = f"+{c.cc}" if with_cc else ""
                    fname = f"{c.name}_{safe_name(nm)}_{k + 1:04d}_{label}.{ext}"
                    write_jobs.append((os.path.join(folder, fname), fmt, prefix, chunk))
        written = 0
        for k, _ in enumerate(pool.imap_unordered(write_pack, write_jobs, chunksize=1)):
            if cancel():
                pool.terminate()
                raise Cancelled()
            written += 1
            progress(0.75 + 0.20 * written / max(len(write_jobs), 1), f"写出分包… {written}/{len(write_jobs)}")

    # ---- 错误号码清单 ----
    err_dir = os.path.join(out_dir, "错误号码")
    err_files, err_counts, err_reason = [], [0] * n, [defaultdict(int) for _ in range(n)]
    for ci in range(n):
        if not errs[ci]:
            continue
        c = COUNTRIES[ci]
        nat = np.concatenate([e[0] for e in errs[ci]])
        rs = np.concatenate([e[1] for e in errs[ci]])
        order = np.argsort(nat)
        nat, rs = nat[order], rs[order]
        err_counts[ci] = len(nat)
        for code, cnt in zip(*np.unique(rs, return_counts=True)):
            err_reason[ci][REASONS[int(code)]] = int(cnt)
        rows = ((f"+{c.cc}{x}", REASONS[int(r)]) for x, r in zip(nat.tolist(), rs.tolist()))
        err_files += write_errors_csv(os.path.join(err_dir, f"{c.name}_错误号码"), rows)
    if unk_set:
        rows = ((x, "无法识别国家/格式") for x in sorted(unk_set))
        err_files += write_errors_csv(os.path.join(err_dir, "未识别国家_错误号码"), rows)

    # ---- 报告 ----
    elapsed = time.time() - t0
    countries_rep = {}
    for ci, c in enumerate(COUNTRIES):
        if c.key not in selected:
            continue
        ops = {nm: {"有效号码": valid_counts[(i, nm)], "分包数": pack_counts[(i, nm)]}
               for (i, nm) in sorted(valid_counts) if i == ci}
        valid = sum(v["有效号码"] for v in ops.values())
        countries_rep[c.name] = {
            "读取号码数(含重复)": read[ci],
            "去重后号码数": unique_counts[ci],
            "重复号码数": read[ci] - unique_counts[ci],
            "有效手机号": valid,
            "错误号码": err_counts[ci],
            "错误原因": dict(err_reason[ci]),
            "运营商": ops,
            "分包数": sum(v["分包数"] for v in ops.values()),
        }
    report = {
        "软件版本": __version__,
        "耗时(秒)": round(elapsed, 1),
        "读取文件数": len(ok_files),
        "读取失败文件数": len(failed),
        "读取失败文件": failed,
        "无法识别国家的号码": {"读取": unk_read, "去重后(已写入错误清单)": len(unk_set)},
        "已忽略的其他国家号码": foreign,
        "每包数量": pack_size,
        "输出格式": fmt.upper(),
        "号码格式": [f[0] for f in formats],
        "各国家": countries_rep,
        "总分包数": sum(pack_counts.values()),
        "错误清单文件": [os.path.relpath(f, out_dir) for f in err_files],
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "汇总报告.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    text = format_report(report)
    with open(os.path.join(out_dir, "汇总报告.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    progress(1.0, "完成")
    report["_text"] = text
    return report


def format_report(r):
    L = ["========== 手机号整理汇总 ==========",
         f"耗时：{r['耗时(秒)']} 秒    读取文件：{r['读取文件数']} 个    失败：{r['读取失败文件数']} 个",
         f"输出格式：{r['输出格式']}    号码格式：{'、'.join(r['号码格式'])}    每包：{r['每包数量']:,}    总分包数：{r['总分包数']}",
         ""]
    for name, d in r["各国家"].items():
        L += [f"【{name}】读取 {d['读取号码数(含重复)']:,}｜重复 {d['重复号码数']:,}｜去重后 {d['去重后号码数']:,}｜"
              f"有效 {d['有效手机号']:,}｜错误 {d['错误号码']:,}｜分包 {d['分包数']}"]
        if d["错误原因"]:
            L.append("    错误原因：" + "，".join(f"{k} {v:,}" for k, v in d["错误原因"].items()))
        for op, v in d["运营商"].items():
            L.append(f"    {op}：{v['有效号码']:,}（{v['分包数']} 包）")
        L.append("")
    u = r["无法识别国家的号码"]
    L.append(f"无法识别国家的号码：读取 {u['读取']:,}，去重后 {u['去重后(已写入错误清单)']:,}（已写入错误清单）")
    L.append(f"已忽略的其他国家号码：{r['已忽略的其他国家号码']:,}")
    if r["读取失败文件"]:
        L.append("\n读取失败的文件：")
        for k, v in r["读取失败文件"].items():
            L.append(f"  - {k}：{v}")
    L.append("\n说明：“有效”指去重后的有效手机号；错误号码已单独导出到「错误号码」文件夹。")
    return "\n".join(L)
