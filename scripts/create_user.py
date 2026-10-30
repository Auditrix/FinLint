"""Create a FinLint account. There is no sign up page on purpose.

In a finance team someone responsible decides who gets access, and with what
role. Run from the repository root, with PostgreSQL up:

    python scripts/create_user.py nara --role reviewer
    python scripts/create_user.py sowb --role analyst
    python scripts/create_user.py cfo --role signer

The password is asked for and never echoed, so it does not land in your shell
history. Roles: analyst (uploads and reads), reviewer (also marks findings as
intentional), signer (reads only). See src/finlint/auth.py.

Inside the Docker container:

    docker compose exec app python scripts/create_user.py nara --role reviewer
"""

import argparse
import getpass
import sys

from finlint import auth
from finlint.rag.store import DATABASE_URL

import psycopg


def main():
    parser = argparse.ArgumentParser(description="Create a FinLint account.")
    parser.add_argument("username")
    parser.add_argument("--role", required=True, choices=auth.ROLES)
    args = parser.parse_args()

    password = getpass.getpass(f"Password for {args.username} (at least {auth.MIN_PASSWORD} characters): ")
    if getpass.getpass("Type it again: ") != password:
        sys.exit("The two passwords did not match. Nothing was created.")

    # A plain connection: this needs no vector search, and the tables are
    # created here too, so the script works before the API has ever started.
    with psycopg.connect(DATABASE_URL) as conn:
        for statement in auth.SCHEMA:
            conn.execute(statement)
        conn.commit()
        try:
            user = auth.create_user(conn, args.username, args.role, password)
        except ValueError as error:
            sys.exit(str(error))
    print(f"Created {user.username} as {user.role}.")


if __name__ == "__main__":
    main()
