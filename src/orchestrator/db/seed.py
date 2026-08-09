import random
from datetime import date

from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from faker import Faker

from orchestrator.db.connection import connect

load_dotenv()

fake = Faker()
borrower_ids = []
loan_ids = []
loans = []

with connect(read_only=False, autocommit=False) as conn:
    with conn.cursor() as cur:
        for _ in range(25):
            cur.execute(
                """
                INSERT INTO Borrower (first_name, last_name, phone, email, credit_score, annual_income)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING borrower_id
                """,
                (
                    fake.first_name(),
                    fake.last_name(),
                    fake.phone_number()[:20],
                    fake.unique.email(),
                    fake.random_int(min=550, max=820),
                    fake.random_int(min=35000, max=250000),
                ),
            )
            borrower_ids.append(cur.fetchone()[0])
        for borrower_id in borrower_ids:
            for _ in range(random.randint(1, 2)):
                origination_date = fake.date_between(start_date="-3y", end_date="today")
                loan_amount = fake.random_int(min=150000, max=800000)
                interest_rate = round(random.uniform(3.5, 8.0), 3)
                term_months = random.choice([180, 240, 360])

                cur.execute(
                    """
                    INSERT INTO Loan (borrower_id, origination_date, loan_amount, loan_type, interest_rate, term_months, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING loan_id
                    """,
                    (
                        borrower_id,
                        origination_date,
                        loan_amount,
                        random.choice(["purchase_mortgage", "refinance", "heloc", "hardship_modification"]),
                        interest_rate,
                        term_months,
                        random.choices(
                            ["active", "delinquent", "forbearance", "paid_off", "default"],
                            weights=[70, 12, 5, 10, 3],
                        )[0],
                    ),
                )
                loan_id = cur.fetchone()[0]
                loan_ids.append(loan_id)
                loans.append(
                    {
                        "loan_id": loan_id,
                        "origination_date": origination_date,
                        "loan_amount": loan_amount,
                        "interest_rate": interest_rate,
                        "term_months": term_months,
                    }
                )

        payment_count = 0
        ledger_count = 0

        for loan in loans:
            monthly_payment = round(loan["loan_amount"] / loan["term_months"], 2)
            monthly_interest_rate = loan["interest_rate"] / 100 / 12
            balance = loan["loan_amount"]

            cur.execute(
                """
                INSERT INTO Ledger (loan_id, transaction_type, amount, balance_after, transaction_date)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (loan["loan_id"], "disbursement", loan["loan_amount"], balance, loan["origination_date"]),
            )
            ledger_count += 1

            months_elapsed = min(
                (date.today().year - loan["origination_date"].year) * 12
                + (date.today().month - loan["origination_date"].month),
                loan["term_months"],
            )

            due_date = loan["origination_date"]
            for _ in range(months_elapsed):
                due_date += relativedelta(months=1)
                interest_portion = round(balance * monthly_interest_rate, 2)
                principal_portion = round(monthly_payment - interest_portion, 2)

                status = random.choices(
                    ["on_time", "late", "missed", "partial"],
                    weights=[75, 12, 8, 5],
                )[0]

                if status == "missed":
                    payment_date = None
                    amount_paid = None
                    paid_principal = None
                    paid_interest = None
                else:
                    payment_date = due_date if status != "late" else due_date + relativedelta(days=random.randint(1, 20))
                    amount_paid = monthly_payment if status != "partial" else round(monthly_payment * random.uniform(0.4, 0.9), 2)
                    paid_principal = principal_portion if status != "partial" else round(amount_paid * (principal_portion / monthly_payment), 2)
                    paid_interest = interest_portion if status != "partial" else round(amount_paid - paid_principal, 2)

                cur.execute(
                    """
                    INSERT INTO Payment (loan_id, due_date, payment_date, amount_due, amount_paid, principal_portion, interest_portion, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        loan["loan_id"],
                        due_date,
                        payment_date,
                        monthly_payment,
                        amount_paid,
                        paid_principal,
                        paid_interest,
                        status,
                    ),
                )
                payment_count += 1

                if status != "missed":
                    balance = round(balance - paid_principal, 2)
                    cur.execute(
                        """
                        INSERT INTO Ledger (loan_id, transaction_type, amount, balance_after, transaction_date)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (loan["loan_id"], "payment", amount_paid, balance, due_date),
                    )
                    ledger_count += 1

        conn.commit()

print(f"Inserted {len(borrower_ids)} borrowers, {len(loan_ids)} loans, {payment_count} payments, {ledger_count} ledger entries")
