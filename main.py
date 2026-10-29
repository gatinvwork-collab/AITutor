"""Desktop entry point for Tutor-AI."""

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    import sys
    from tutor_ai.desktop import run

    raise SystemExit(run(smoke="--smoke" in sys.argv, diagnostics="--diagnostics" in sys.argv))
