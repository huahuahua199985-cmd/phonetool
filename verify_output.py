"""把软件输出与 gen_testdata 的标准答案逐项对账。用法: python verify_output.py <truth目录> <输出目录> <每包数量> [fmt]"""
import glob, json, os, sys
import numpy as np

truth_dir, out_dir, pack = sys.argv[1], sys.argv[2], int(sys.argv[3])
KEYS = ["IN", "ID", "TH"]; NAME = {"IN": "印度", "ID": "印尼", "TH": "泰国"}; CC = {"IN": 91, "ID": 62, "TH": 66}
exp = json.load(open(os.path.join(truth_dir, "expected.json")))
rep = json.load(open(os.path.join(out_dir, "汇总报告.json")))
bad = []
def check(name, a, b):
    ok = a == b
    print(("PASS " if ok else "FAIL ") + f"{name}: 软件={a} 标准答案={b}")
    if not ok: bad.append(name)

check("读取失败文件", sorted(rep["读取失败文件"].keys()), sorted(exp["failed_files"]))
check("无法识别国家(去重)", rep["无法识别国家的号码"]["去重后(已写入错误清单)"], exp["unknown_country_unique"])
check("无法识别国家(读取)", rep["无法识别国家的号码"]["读取"], exp["unknown_read"])
print("其他国家号码忽略数", rep["已忽略的其他国家号码"], "(生成器写入 >= %d)" % exp["foreign_min"])
for k in KEYS:
    t = exp["countries"][k]; r = rep["各国家"][NAME[k]]; z = np.load(os.path.join(truth_dir, f"{k}.npz"))
    check(f"{k} 读取条数", r["读取号码数(含重复)"], t["read"])
    check(f"{k} 去重后", r["去重后号码数"], t["unique"])
    check(f"{k} 有效", r["有效手机号"], t["valid"])
    check(f"{k} 错误", r["错误号码"], t["invalid"])
    check(f"{k} 运营商分布", {a: b["有效号码"] for a, b in r["运营商"].items()}, t["carriers"])
    # 逐号对账：读输出文件
    got = {}
    names = z["names"].tolist(); exp_by = {n: np.sort(z["valid"][z["carrier"] == i]) for i, n in enumerate(names)}
    ok_all = True; packs_ok = True; npacks = 0
    for car in os.listdir(os.path.join(out_dir, NAME[k])):
        files = sorted(glob.glob(os.path.join(out_dir, NAME[k], car, "*带国家码.txt")) + glob.glob(os.path.join(out_dir, NAME[k], car, "*带国家码.xlsx")))
        files = [f for f in files if "不带国家码" not in f]
        arrs, sizes = [], []
        for f in files:
            if f.endswith(".txt"):
                lines = open(f, encoding="utf-8").read().split("\n")[:-1]
            else:
                from python_calamine import CalamineWorkbook
                lines = [str(r[0]) for r in CalamineWorkbook.from_path(f).get_sheet_by_index(0).to_python()]
            sizes.append(len(lines))
            assert all(l.startswith(f"+{CC[k]}") for l in lines)
            arrs.append(np.array([int(l[len(str(CC[k])) + 1:]) for l in lines], dtype=np.uint64))
        npacks += len(files)
        allv = np.concatenate(arrs) if arrs else np.empty(0, np.uint64)
        if car not in exp_by or not np.array_equal(np.sort(allv), exp_by[car]) or len(np.unique(allv)) != len(allv):
            ok_all = False
        lim = min(pack, 1_000_000) if files and files[0].endswith("xlsx") else pack
        if any(s > lim for s in sizes) or any(s != lim for s in sizes[:-1]): packs_ok = False
    check(f"{k} 逐号对账(输出文件内容=标准答案)", ok_all, True)
    check(f"{k} 分包大小正确", packs_ok, True)
    check(f"{k} 分包数(报告=磁盘)", r["分包数"], npacks)
    # 错误清单
    ef = sorted(glob.glob(os.path.join(out_dir, "错误号码", f"{NAME[k]}_错误号码*.csv")))
    got = []
    for f in ef:
        got += [int(l.split(",")[0][len(str(CC[k])) + 1:]) for l in open(f, encoding="utf-8-sig").read().split("\n")[1:] if l]
    check(f"{k} 错误清单逐号对账", sorted(got) == sorted(z["invalid"].tolist()), True)
print("\n结果：", "全部通过" if not bad else f"有 {len(bad)} 项不通过：{bad}")
sys.exit(1 if bad else 0)
