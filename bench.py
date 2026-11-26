"""运行命令并每 0.5 秒采样整个进程树的内存（RSS 之和），报告峰值与耗时。"""
import json, subprocess, sys, time, psutil
cmd = sys.argv[2:]; log = sys.argv[1]
t0 = time.time(); p = subprocess.Popen(cmd, stdout=open(log, "w"), stderr=subprocess.STDOUT)
ps = psutil.Process(p.pid); peak = 0; peak_main = 0; samples = []
while p.poll() is None:
    try:
        kids = ps.children(recursive=True); tot = ps.memory_info().rss + sum(k.memory_info().rss for k in kids if k.is_running())
        peak = max(peak, tot); peak_main = max(peak_main, ps.memory_info().rss)
        samples.append((round(time.time() - t0, 1), tot >> 20, len(kids)))
    except psutil.Error:
        pass
    time.sleep(0.5)
res = {"elapsed_s": round(time.time() - t0, 1), "peak_total_rss_MB": peak >> 20, "peak_main_process_rss_MB": peak_main >> 20, "exit": p.returncode}
json.dump({"result": res, "samples": samples}, open(log + ".mem.json", "w"))
print(json.dumps(res))
