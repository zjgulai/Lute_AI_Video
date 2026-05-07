#!/usr/bin/env python3
"""Create the initial admin account for the admin panel.

Usage:
    python scripts/create_admin.py <email> <password>
    python scripts/create_admin.py <email> <password> --force

The script requires a running PostgreSQL database (reads DATABASE_URL from
environment or .env). Run this once during initial setup, or to add
additional admin accounts with --force.

Passwords must be at least 12 characters.
"""

import asyncio
import os
import sys

import bcrypt
from dotenv import load_dotenv

load_dotenv()


MIN_PASSWORD_LENGTH = 12
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))


async def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python scripts/create_admin.py <email> <password> [--force]")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    password = sys.argv[2]
    force = "--force" in sys.argv

    if "@" not in email or "." not in email:
        print("Error: invalid email format")
        sys.exit(1)

    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Error: password must be at least {MIN_PASSWORD_LENGTH} characters")
        sys.exit(1)

    # Hash password
    password_hash = bcrypt.hashpw(
        password.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode()

    try:
        from src.storage.db import get_pool, is_pg_available

        if not is_pg_available():
            print("Error: PostgreSQL not available. Check DATABASE_URL.")
            sys.exit(1)

        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check for existing admin
            existing = await conn.fetchrow(
                "SELECT id, email FROM admin_accounts WHERE email = $1",
                email,
            )

            if existing:
                if not force:
                    print(
                        f"Admin account already exists: {existing['email']} "
                        f"(id={existing['id']})"
                    )
                    print("Use --force to update the password.")
                    sys.exit(0)
                else:
                    await conn.execute(
                        "UPDATE admin_accounts SET password_hash = $1 WHERE email = $2",
                        password_hash,
                        email,
                    )
                    print(f"Password updated for admin: {email}")
                    return

            # Create new admin
            row = await conn.fetchrow(
                """
                INSERT INTO admin_accounts (email, password_hash)
                VALUES ($1, $2)
                RETURNING id, email, created_at
                """,
                email,
                password_hash,
            )
            print(f"Admin account created: {row['email']} (id={row['id']})")

    except ImportError as exc:
        print(f"Error: unable to import database module — {exc}")
        print("Make sure you're running from the project root with the virtualenv active.")
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
