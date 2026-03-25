import json
import os
import base64
import hashlib
import hmac
import time
from datetime import datetime

__all__ = [
    "AUTH_FILE",
    "init_store",
    "ensure_admin_exists",
    "list_users",
    "create_user",
    "authenticate_user",
    "set_user_role",
    "set_user_active",
    "delete_user",
]

HERE = os.path.dirname(__file__)
AUTH_FILE = os.path.join(HERE, "users.json")


def _load():
    if not os.path.exists(AUTH_FILE):
        return {"users": {}}
    with open(AUTH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data):
    tmp = AUTH_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, AUTH_FILE)


def _hash_password(password: str, salt: bytes = None, iterations: int = 200_000):
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "hash": base64.b64encode(dk).decode("ascii"),
        "iter": iterations,
    }


def _verify_password(password: str, record: dict) -> bool:
    try:
        salt = base64.b64decode(record["salt"])
        expected = base64.b64decode(record["hash"])
        it = int(record.get("iter", 200_000))
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, it)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def init_store():
    data = _load()
    if "users" not in data:
        data = {"users": {}}
        _save(data)
    return AUTH_FILE


def ensure_admin_exists():
    data = _load()
    users = data.setdefault("users", {})
    if any(u.get("role") == "admin" and u.get("active", True) for u in users.values()):
        return
    # try to seed from initial_admin.txt
    init_file = os.path.join(HERE, "initial_admin.txt")
    admin_email = "admin@localhost"
    admin_password = None
    if os.path.exists(init_file):
        try:
            with open(init_file, "r", encoding="utf-8") as f:
                txt = f.read()
            for line in txt.splitlines():
                if line.strip().startswith("initial admin:"):
                    admin_email = line.split(":", 1)[1].strip()
                if line.strip().startswith("password:"):
                    admin_password = line.split(":", 1)[1].strip()
        except Exception:
            pass
    if admin_password is None:
        admin_password = "admin" + base64.b64encode(os.urandom(6)).decode("ascii")

    create_user(admin_email, admin_password, role="admin", name="Initial Admin")


def list_users():
    data = _load()
    users = data.get("users", {})
    out = []
    for email, u in users.items():
        out.append({
            "email": email,
            "name": u.get("name") or "",
            "role": u.get("role", "user"),
            "active": bool(u.get("active", True)),
            "created_at": u.get("created_at"),
        })
    return out


def create_user(email: str, password: str, role: str = "user", name: str = None) -> dict:
    email = email.strip().lower()
    if not email or not password:
        raise ValueError("email and password required")
    data = _load()
    users = data.setdefault("users", {})
    if email in users:
        raise ValueError("user exists")
    pwrec = _hash_password(password)
    users[email] = {
        "name": name or "",
        "role": role,
        "active": True,
        "password": pwrec,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    _save(data)
    return {"email": email, "role": role}


def authenticate_user(email: str, password: str):
    email = email.strip().lower()
    data = _load()
    user = data.get("users", {}).get(email)
    if not user or not user.get("active", True):
        return None
    pw = user.get("password")
    if not pw:
        return None
    if _verify_password(password, pw):
        return {"email": email, "name": user.get("name"), "role": user.get("role", "user")}
    return None


def set_user_role(email: str, role: str):
    email = email.strip().lower()
    data = _load()
    users = data.setdefault("users", {})
    if email not in users:
        raise KeyError("no such user")
    users[email]["role"] = role
    _save(data)


def set_user_active(email: str, active: bool):
    email = email.strip().lower()
    data = _load()
    users = data.setdefault("users", {})
    if email not in users:
        raise KeyError("no such user")
    users[email]["active"] = bool(active)
    _save(data)


def delete_user(email: str):
    email = email.strip().lower()
    data = _load()
    users = data.setdefault("users", {})
    if email in users:
        del users[email]
        _save(data)
