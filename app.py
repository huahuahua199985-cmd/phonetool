"""手机号整理工具 - 桌面界面（Tkinter，中文）"""
import multiprocessing as mp
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from phonetool import __version__, engine
from phonetool.countries import COUNTRIES


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"手机号整理工具 v{__version__}")
        self.geometry("760x640")
        self.minsize(680, 560)
        self.q = queue.Queue()
        self.running = False
        self.cancel_flag = False
        self.v_in = tk.StringVar()
        self.v_out = tk.StringVar()
        self.v_pack = tk.StringVar(value="100000")
        self.v_fmt = tk.StringVar(value="txt")
        self.v_cc = tk.BooleanVar(value=True)
        self.v_nocc = tk.BooleanVar(value=False)
        self.v_c = {c.key: tk.BooleanVar(value=True) for c in COUNTRIES}
        self._build()
        self.after(100, self._poll)

    def _build(self):
        pad = {"padx": 10, "pady": 5}
        f = ttk.Frame(self)
        f.pack(fill="x", **pad)
        ttk.Label(f, text="输入文件夹：").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.v_in).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(f, text="选择…", command=lambda: self._pick(self.v_in)).grid(row=0, column=2)
        ttk.Label(f, text="输出文件夹：").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(f, textvariable=self.v_out).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(f, text="选择…", command=lambda: self._pick(self.v_out)).grid(row=1, column=2)
        f.columnconfigure(1, weight=1)

        g = ttk.LabelFrame(self, text="选项")
        g.pack(fill="x", **pad)
        r = ttk.Frame(g)
        r.pack(fill="x", padx=8, pady=4)
        ttk.Label(r, text="国家：").pack(side="left")
        for c in COUNTRIES:
            ttk.Checkbutton(r, text=f"{c.name} +{c.cc}", variable=self.v_c[c.key]).pack(side="left", padx=8)
        r = ttk.Frame(g)
        r.pack(fill="x", padx=8, pady=4)
        ttk.Label(r, text="每包数量：").pack(side="left")
        ttk.Spinbox(r, from_=1, to=100000000, increment=10000, textvariable=self.v_pack, width=12).pack(side="left", padx=6)
        ttk.Label(r, text="输出格式：").pack(side="left", padx=(20, 0))
        ttk.Radiobutton(r, text="TXT", value="txt", variable=self.v_fmt).pack(side="left", padx=4)
        ttk.Radiobutton(r, text="XLSX", value="xlsx", variable=self.v_fmt).pack(side="left", padx=4)
        r = ttk.Frame(g)
        r.pack(fill="x", padx=8, pady=4)
        ttk.Label(r, text="号码格式：").pack(side="left")
        ttk.Checkbutton(r, text="带国家码（如 +62812…）", variable=self.v_cc).pack(side="left", padx=8)
        ttk.Checkbutton(r, text="不带国家码（如 812…）", variable=self.v_nocc).pack(side="left", padx=8)

        b = ttk.Frame(self)
        b.pack(fill="x", **pad)
        self.btn = ttk.Button(b, text="开始整理", command=self.start)
        self.btn.pack(side="left")
        self.btn_cancel = ttk.Button(b, text="取消", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=8)
        self.btn_open = ttk.Button(b, text="打开输出文件夹", command=self._open_out)
        self.btn_open.pack(side="right")
        self.bar = ttk.Progressbar(self, maximum=1000)
        self.bar.pack(fill="x", **pad)
        self.status = ttk.Label(self, text="就绪")
        self.status.pack(anchor="w", padx=10)
        self.txt = tk.Text(self, wrap="word", height=18)
        self.txt.pack(fill="both", expand=True, **pad)

    def _pick(self, var):
        d = filedialog.askdirectory(title="选择文件夹")
        if d:
            var.set(d)

    def _open_out(self):
        d = self.v_out.get()
        if not d or not os.path.isdir(d):
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", d])
        elif sys.platform.startswith("win"):
            os.startfile(d)  # noqa
        else:
            subprocess.Popen(["xdg-open", d])

    def _cancel(self):
        self.cancel_flag = True
        self.status.config(text="正在取消…")

    def start(self):
        if self.running:
            return
        inp, out = self.v_in.get().strip(), self.v_out.get().strip()
        if not inp or not os.path.isdir(inp):
            return messagebox.showwarning("提示", "请先选择有效的输入文件夹")
        if not out:
            return messagebox.showwarning("提示", "请先选择输出文件夹")
        sel = [k for k, v in self.v_c.items() if v.get()]
        if not sel:
            return messagebox.showwarning("提示", "请至少勾选一个国家")
        if not (self.v_cc.get() or self.v_nocc.get()):
            return messagebox.showwarning("提示", "号码格式请至少勾选一项")
        try:
            pack = int(self.v_pack.get())
            assert pack > 0
        except Exception:
            return messagebox.showwarning("提示", "每包数量必须是正整数")
        a, b = os.path.abspath(inp), os.path.abspath(out)
        if b == a or b.startswith(a + os.sep):
            return messagebox.showwarning("提示", "输出文件夹不能放在输入文件夹里面，请换一个")
        if os.path.isdir(b) and os.listdir(b):
            if not messagebox.askyesno("确认", "输出文件夹不是空的，同名文件会被覆盖。继续吗？"):
                return
        cfg = {"input_dir": inp, "output_dir": out, "countries": sel, "pack_size": pack, "fmt": self.v_fmt.get(),
               "with_cc": self.v_cc.get(), "without_cc": self.v_nocc.get()}
        self.running, self.cancel_flag = True, False
        self.btn.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.txt.delete("1.0", "end")
        self.bar["value"] = 0
        threading.Thread(target=self._work, args=(cfg,), daemon=True).start()

    def _work(self, cfg):
        try:
            rep = engine.run(cfg, lambda f, m: self.q.put(("p", f, m)), lambda: self.cancel_flag)
            self.q.put(("done", rep["_text"]))
        except engine.Cancelled:
            self.q.put(("cancel",))
        except Exception as e:  # noqa
            import traceback
            self.q.put(("err", f"{e}\n{traceback.format_exc()}"))

    def _poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "p":
                    self.bar["value"] = m[1] * 1000
                    self.status.config(text=m[2])
                else:
                    self.running = False
                    self.btn.config(state="normal")
                    self.btn_cancel.config(state="disabled")
                    if m[0] == "done":
                        self.bar["value"] = 1000
                        self.status.config(text="完成")
                        self.txt.insert("end", m[1])
                    elif m[0] == "cancel":
                        self.status.config(text="已取消")
                    else:
                        self.status.config(text="出错")
                        self.txt.insert("end", "运行出错：\n" + m[1])
        except queue.Empty:
            pass
        self.after(100, self._poll)


if __name__ == "__main__":
    mp.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":      # 打包后自检用：app --cli 输入 输出
        from phonetool.cli import main
        main(sys.argv[2:])
    else:
        App().mainloop()
