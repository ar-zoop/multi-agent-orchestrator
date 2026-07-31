CREATE TABLE Borrower (
    borrower_id     SERIAL PRIMARY KEY,
    first_name      VARCHAR(50) NOT NULL,
    last_name       VARCHAR(50) NOT NULL,
    phone           VARCHAR(20),
    email           VARCHAR(120) UNIQUE,
    credit_score    INT CHECK (credit_score BETWEEN 300 AND 850),
    annual_income   NUMERIC(12,2)
);

CREATE TABLE Loan (
    loan_id           SERIAL PRIMARY KEY,
    borrower_id       INT NOT NULL REFERENCES Borrower(borrower_id),
    origination_date  DATE NOT NULL,
    loan_amount       NUMERIC(12,2) NOT NULL,
    loan_type         VARCHAR(30) NOT NULL CHECK (loan_type IN ('purchase_mortgage', 'refinance', 'heloc', 'hardship_modification')),
    interest_rate     NUMERIC(5,3) NOT NULL,
    term_months       INT NOT NULL,
    status            VARCHAR(20) NOT NULL CHECK (status IN ('active', 'delinquent', 'forbearance', 'paid_off', 'default'))
);

CREATE TABLE Payment (
    payment_id         SERIAL PRIMARY KEY,
    loan_id            INT NOT NULL REFERENCES Loan(loan_id),
    due_date           DATE NOT NULL,
    payment_date       DATE,
    amount_due         NUMERIC(12,2) NOT NULL,
    amount_paid        NUMERIC(12,2),
    principal_portion  NUMERIC(12,2),
    interest_portion   NUMERIC(12,2),
    status             VARCHAR(10) NOT NULL CHECK (status IN ('on_time', 'late', 'missed', 'partial'))
);

CREATE TABLE Ledger (
    ledger_id         SERIAL PRIMARY KEY,
    loan_id           INT NOT NULL REFERENCES Loan(loan_id),
    transaction_type  VARCHAR(20) NOT NULL CHECK (transaction_type IN ('disbursement', 'payment', 'interest_accrual', 'fee', 'charge_off')),
    amount            NUMERIC(12,2) NOT NULL,
    balance_after     NUMERIC(12,2) NOT NULL,
    transaction_date  DATE NOT NULL
);