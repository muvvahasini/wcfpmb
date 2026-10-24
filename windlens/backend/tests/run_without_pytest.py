import sys, types, traceback, inspect
sys.path.insert(0, "/home/claude/windlens/backend")
# minimal pytest shim (pytest not installable offline)
pt = types.ModuleType("pytest")
class _Approx:
    def __init__(s, v): s.v = v
    def __eq__(s, o): return abs(o - s.v) < 1e-6 * max(1, abs(s.v))
pt.approx = lambda v: _Approx(v)
class _Raises:
    def __init__(s, exc): s.exc = exc
    def __enter__(s): return s
    def __exit__(s, t, v, tb):
        assert t is not None and issubclass(t, s.exc), "did not raise"
        return True
pt.raises = lambda e: _Raises(e)
sys.modules["pytest"] = pt
import importlib; mod = importlib.import_module("tests.test_core")
p = f = 0
for n, fn in inspect.getmembers(mod, inspect.isfunction):
    if n.startswith("test_"):
        try: fn(); p += 1; print("PASS", n)
        except Exception: f += 1; print("FAIL", n); traceback.print_exc()
print(f"{p} passed, {f} failed")
