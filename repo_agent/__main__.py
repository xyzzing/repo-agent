"""Module entry so `python3 -m repo_agent` honors the process exit-code
contract, not just the in-process main() return."""
import sys

from repo_agent.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
