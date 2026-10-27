"""Allow unchanged, archived QA probes to import the renamed native modules.

This alias exists in the test process only, never in the shipped application.
Historical evidence is immutable; current tests import tutor_ai directly.
"""
import importlib
import sys

sys.modules["aitutor"] = importlib.import_module("tutor_ai")
for name in ("addresses", "audit", "crypto", "desktop", "documents", "education", "errors",
             "history", "providers", "service", "storage"):
    sys.modules["aitutor." + name] = importlib.import_module("tutor_ai." + name)
