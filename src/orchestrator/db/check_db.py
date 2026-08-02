import psycopg2

for host in ['127.0.0.1', 'localhost']:
    params = {'host': host, 'port': 5432, 'user': 'admin', 'password': 'password', 'dbname': 'loan_bank_db'}
    try:
        conn = psycopg2.connect(**params)
        print(host, 'ok')
        conn.close()
    except Exception as e:
        print(host, type(e).__name__, e)
