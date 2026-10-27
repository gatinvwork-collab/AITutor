"""Desktop entry point for AI Tutor."""

if __name__ == "__main__":
    import sys
    from aitutor.desktop import run

    raise SystemExit(run(smoke="--smoke" in sys.argv))
