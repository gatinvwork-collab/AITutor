"""Desktop entry point for Tutor-AI."""

if __name__ == "__main__":
    import sys
    from tutor_ai.desktop import run

    raise SystemExit(run(smoke="--smoke" in sys.argv))
