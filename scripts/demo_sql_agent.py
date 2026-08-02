from dotenv import load_dotenv

from orchestrator.agents.sql_agent import generate_sql
from orchestrator.providers.openai_provider import OpenAIProvider

load_dotenv()

SAMPLE_QUESTIONS = [
    "How many loans are currently delinquent?",
    "What is the total outstanding loan amount for borrowers with a credit score below 650?",
    "List the 5 most recent payments that were marked as missed, most recent first.",
    "What is the total amount of interest accrued (from the ledger) for loan ID 42?",
]


def main():
    provider = OpenAIProvider()
    model = "gpt-4o-mini"

    for question in SAMPLE_QUESTIONS:
        print(f"Q: {question}")
        sql = generate_sql(question, provider, model=model)
        print(f"SQL:\n{sql}\n")
        print("-" * 60)


if __name__ == "__main__":
    main()
