"""分包写出 TXT / XLSX。"""
import os
import re

XLSX_MAX_ROWS = 1_000_000   # 低于 Excel 单表上限 1,048,576，留余量


def safe_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", s).strip(" .")
    return (s or "未知")[:60]


def write_pack(args):
    """args: (path, fmt, prefix, numbers(list/ndarray))"""
    path, fmt, prefix, arr = args
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nums = arr.tolist()
    if fmt == "txt":
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join([prefix + str(x) for x in nums]))
            f.write("\n")
    else:
        import xlsxwriter
        wb = xlsxwriter.Workbook(path, {"constant_memory": True, "strings_to_numbers": False})
        ws = wb.add_worksheet("号码")
        for i, x in enumerate(nums):
            ws.write_string(i, 0, prefix + str(x))
        wb.close()
    return path, len(nums)


def write_errors_csv(path_base, rows):
    """错误号码清单：CSV（UTF-8 带 BOM，Excel 直接打开），超过 100 万行自动拆分。返回文件列表。"""
    os.makedirs(os.path.dirname(path_base), exist_ok=True)
    files, part, f, n = [], 0, None, 0
    for number, reason in rows:
        if f is None or n >= XLSX_MAX_ROWS - 1:
            if f:
                f.close()
            part += 1
            p = f"{path_base}.csv" if part == 1 else f"{path_base}_{part}.csv"
            f = open(p, "w", encoding="utf-8-sig", newline="")
            f.write("号码,原因\n")
            files.append(p)
            n = 0
        f.write(f"{number},{reason}\n")
        n += 1
    if f:
        f.close()
    return files
