"""checkpoint 写盘被跳过之后必须有人接着写（P0 回归套件）。

现场事故：某一类（remaining）的 checkpoint 连续 8 天没落盘，进程 CPU 跑满、
日志里一个字都没有；每次重启都从旧 offset 再全量重折一遍（548MB 日志里
350MB 要重扫）。根因是写盘路径的三条「静默跳过」——状态锁被占、状态不可
序列化、收集为空——其中任何一条成立就 `continue`，下一次不一定轮得到它。

钉住四件事：
  1. 跳过必须留痕（节流日志）并登记补写，绝不静默；
  2. 补写线程在锁释放后**真的把文件写出来**，业务请求线程全程不阻塞；
  3. 写成功后取补写计划，退避计数归零（下次再跳过从头退避）；
  4. 加载到的 checkpoint 落后日志很多时必须告警（「重启后又卡了」的线索）。

No network: usage/accounts live in a temp directory.
"""
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp(prefix="wb-retry-save-")
USAGE_DIR = os.path.join(_TMP, "usage")
ACCOUNTS_DIR = os.path.join(_TMP, "accounts")
os.makedirs(USAGE_DIR, exist_ok=True)
os.makedirs(ACCOUNTS_DIR, exist_ok=True)
os.environ["WB_PROXY_USAGE_DIR"] = USAGE_DIR
os.environ["ACCOUNTS_DIR"] = ACCOUNTS_DIR
# 补写退避压到毫秒级，节流阈值关掉：套件要的是「会不会写」，不是等 30 秒。
os.environ["WB_USAGE_CACHE_RETRY_MIN_SECONDS"] = "0.05"
os.environ["WB_USAGE_CACHE_MIN_SECONDS"] = "0"
# 日志文件当场建出来：_usage_log_key() 要拿到真实 (size, dev, inode)。
with open(os.path.join(USAGE_DIR, "usage.jsonl"), "wb") as _fh:
    _fh.write(b'{"at": 1}\n')

import wb_proxy as P

P.ACCOUNTS_DIR = ACCOUNTS_DIR

PASS = FAIL = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [PASS] " + label)
    else:
        FAIL += 1
        print("  [FAIL] " + label + ("  " + str(extra) if extra else ""))


# 拦截模块级 log()，套件要断言「有没有留痕」。
LOGS = []
_REAL_LOG = P.log


def _capture(message):
    LOGS.append(str(message))


P.log = _capture

OFFSET = 3 * 1024 * 1024      # 超过写盘字节阈值（1MB），保证判定为「该写」
CHECKPOINT = P._usage_cache_kind_path("remaining")


def reset_state(offset=OFFSET):
    """给 remaining 一份可序列化的活状态，并让写盘判定认为「有推进、该写」。"""
    P._remaining_state.update({
        "events": [],
        "usage": {},
        "keys": set(),
        "day": "",
        "log": {"offset": offset, "key": P._usage_log_key(), "tail": b"x"},
        "file": {"offset": 0, "key": None, "tail": b""},
    })
    with P._usage_cache_lock:
        P._usage_cache_progress["remaining"] = offset
        P._usage_cache_checkpointed.pop("remaining", None)
        P._usage_cache_last_attempt = 0.0


def clear_all():
    P._usage_cache_clear_retry("remaining")
    with P._usage_cache_lock:
        P._usage_cache_progress.pop("remaining", None)
        P._usage_cache_checkpointed.pop("remaining", None)
    try:
        os.remove(CHECKPOINT)
    except OSError:
        pass


print("[1] 状态锁被占：跳过要留痕 + 登记补写，且不阻塞请求线程")
del LOGS[:]
reset_state()
holder_taken = threading.Event()
holder_release = threading.Event()


def holder():
    with P._remaining_state_lock:
        holder_taken.set()
        holder_release.wait(15)


t = threading.Thread(target=holder, daemon=True)
t.start()
holder_taken.wait(5)
started = time.time()
P._usage_cache_maybe_save("remaining", OFFSET)
elapsed = time.time() - started
with P._usage_cache_retry_lock:
    scheduled = "remaining" in P._usage_cache_retry_due
    attempts = P._usage_cache_retry_attempts.get("remaining", 0)
holder_release.set()
t.join(5)

check("跳过不阻塞 (%.3fs)" % elapsed, elapsed < 1.0, elapsed)
check("寄存器里登记了补写", scheduled, P._usage_cache_retry_due)
check("退避计数 +1", attempts == 1, attempts)
check("打了一条 skip 日志", any("skipped" in m and "remaining" in m for m in LOGS), LOGS)

print("[2] 锁释放后补写线程真的把文件写出来")
written = None
deadline = time.time() + 10
while time.time() < deadline:
    if os.path.exists(CHECKPOINT):
        written = True
        break
    time.sleep(0.05)
check("checkpoint 文件已生成", written is True, CHECKPOINT)
with P._usage_cache_lock:
    done = P._usage_cache_checkpointed.get("remaining", 0)
check("checkpointed 追到本类 offset", done == OFFSET, done)

print("[3] 写成功后取补写计划、退避归零")
with P._usage_cache_retry_lock:
    pending = "remaining" in P._usage_cache_retry_due
    attempts_after = P._usage_cache_retry_attempts.get("remaining")
check("补写计划已清除", pending is False, P._usage_cache_retry_due)
check("退避计数归零", attempts_after is None, attempts_after)

print("[4] 跳过日志有节流：短时间内反复跳过不刷屏")
del LOGS[:]
reset_state()
skips = 0
for _ in range(3):
    P._usage_cache_note_skip("remaining", why="test")
skips = len([m for m in LOGS if "skipped" in m])
check("三次跳过只记一条", skips == 1, LOGS)

print("[5] checkpoint 落后日志很多时要告警，落后少时闭嘴")
del LOGS[:]
_real_log_key = P._usage_log_key
P._usage_log_key = lambda path=None: (200 * 1024 * 1024, 1, 1)   # 假装日志 200MB
try:
    P._usage_cache_report_lag("remaining", [{"offset": 198 * 1024 * 1024}])
    check("小幅落后不告警", not LOGS, LOGS)
    P._usage_cache_report_lag("remaining", [{"offset": 10 * 1024 * 1024}])
    check("大幅落后告警一次",
          len([m for m in LOGS if "lag" in m]) == 1, LOGS)
    P._usage_cache_report_lag("remaining", [{"offset": None}, {}])
    check("形状不认识时不告警也不抛",
          len([m for m in LOGS if "lag" in m]) == 1, LOGS)
finally:
    P._usage_log_key = _real_log_key

clear_all()
P.log = _REAL_LOG
print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
