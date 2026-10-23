"""Create the first Super Admin owner from the environment. Prints the TOTP URI once."""

import os
import sys

import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session

from vora_api.auth_routes import _hasher
from vora_api.db import get_admin_engine
from vora_api.models import Role, User, UserRole


def main() -> None:
    email = os.environ.get("OWNER_EMAIL", "").strip()
    password = os.environ.get("OWNER_PASSWORD", "")
    if not email or not password:
        print("Set OWNER_EMAIL and OWNER_PASSWORD. Do not commit them.", file=sys.stderr)
        raise SystemExit(2)

    with Session(get_admin_engine()) as session:
        existing = session.scalar(select(User).where(User.email == email))
        if existing:
            print(f"{email} already exists. No change.")
            return
        secret = pyotp.random_base32()
        user = User(
            email=email,
            full_name="Owner",
            password_hash=_hasher.hash(password),
            totp_secret=secret,
            totp_confirmed=False,
            tenant_id=None,
        )
        session.add(user)
        session.flush()
        role = session.scalar(select(Role).where(Role.name == "Owner"))
        if role is None:
            print("Owner role is missing. Run alembic upgrade head.", file=sys.stderr)
            raise SystemExit(1)
        session.add(UserRole(user_id=user.id, role_id=role.id, tenant_id=None))
        session.commit()
        uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Vora 2.0")
        print(uri)


if __name__ == "__main__":
    main()
