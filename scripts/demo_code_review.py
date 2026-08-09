import argparse
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from orchestrator.agents.code_review_agent import format_review, review_diff
from orchestrator.providers.chain import build_provider_chain, default_providers

load_dotenv()


def read_diff(args) -> str:
    if args.file:
        return Path(args.file).read_text()
    if args.git:
        return subprocess.run(
            ["git", "diff", args.git], capture_output=True, text=True, check=True
        ).stdout
    return sys.stdin.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="path to a unified diff file")
    parser.add_argument("--git", help="git revision range to diff, for example main...HEAD")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--allow-any-line", action="store_true")
    args = parser.parse_args()

    diff = read_diff(args)
    if not diff.strip():
        parser.error("no diff supplied - use --file, --git, or pipe a diff on stdin")

    provider = build_provider_chain(default_providers())
    comments = review_diff(
        diff,
        provider,
        model=args.model,
        restrict_to_changed_lines=not args.allow_any_line,
    )
    print(format_review(comments))


if __name__ == "__main__":
    main()
