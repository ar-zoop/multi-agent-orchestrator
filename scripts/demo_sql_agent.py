import argparse

from dotenv import load_dotenv

from orchestrator.agents.sql_agent import answer_question, generate_sql, render_table
from orchestrator.providers.chain import build_provider_chain, default_providers

load_dotenv()

SAMPLE_QUESTIONS = [
    "How many loans are currently delinquent?",
    "What is the total outstanding loan amount for borrowers with a credit score below 650?",
    "List the 5 most recent payments that were marked as missed, most recent first.",
    "What is the total amount of interest accrued (from the ledger) for loan ID 42?",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--sql-only", action="store_true")
    parser.add_argument("question", nargs="*")
    args = parser.parse_args()

    provider = build_provider_chain(default_providers())
    questions = [" ".join(args.question)] if args.question else SAMPLE_QUESTIONS

    for question in questions:
        print(f"Q: {question}")
        if args.sql_only:
            print(f"SQL:\n{generate_sql(question, provider, model=args.model)}")
        else:
            answer = answer_question(question, provider, model=args.model)
            print(f"SQL:\n{answer.sql}")
            print(f"Rows ({answer.result.row_count}):")
            print(render_table(answer.result, max_rows=10))
            print(f"Answer: {answer.answer}")
        print("-" * 70)

    usage = getattr(provider, "usage_by_provider", {})
    for name, stats in usage.items():
        print(f"{name}: {stats.calls} calls, {stats.input_tokens} in, "
              f"{stats.output_tokens} out, ${stats.cost:.6f}")


if __name__ == "__main__":
    main()
