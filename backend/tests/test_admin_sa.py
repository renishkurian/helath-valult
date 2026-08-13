from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)


def _promote(email: str, role: str = "superadmin") -> None:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        assert user is not None
        user.role = role
        db.commit()
    finally:
        db.close()


def _sa_client():
    email = "root@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Root Admin"},
    )
    if r.status_code == 201:
        _promote(email)
    elif r.status_code != 409:
        raise AssertionError(r.text)
    else:
        _promote(email)
    session = TestClient(app)
    login = session.post(
        "/admin/login",
        data={"email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303), login.text[:300]
    return session


def test_owner_is_kept_out_of_superadmin():
    owner = TestClient(app)
    r = owner.post(
        "/auth/register",
        json={"email": "plain@example.com", "password": "password123", "full_name": "Plain Owner"},
    )
    assert r.status_code == 201, r.text
    login = owner.post(
        "/admin/login",
        data={"email": "plain@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)
    denied = owner.get("/admin/sa", follow_redirects=False)
    assert denied.status_code in (302, 303)
    assert denied.headers["location"].endswith("/admin/modules")
    modules = owner.get("/admin/modules")
    assert "Super Admin" not in modules.text
    assert "Control plane" not in modules.text


def test_superadmin_pages_render():
    sa = _sa_client()
    home = sa.get("/admin/sa")
    assert home.status_code == 200
    assert "Control plane" in home.text
    assert "All users" in home.text
    users = sa.get("/admin/sa/users")
    assert users.status_code == 200
    assert "root@example.com" in users.text
    online = sa.get("/admin/sa/online")
    assert online.status_code == 200
    assert "Online now" in online.text
    assert "root@example.com" in online.text
    logins = sa.get("/admin/sa/logins")
    assert logins.status_code == 200
    assert "Login attempts" in logins.text
    form = sa.get("/admin/sa/signup")
    assert form.status_code == 200
    assert "Create user" in form.text
    modules = sa.get("/admin/modules")
    assert "Super Admin" in modules.text


def test_superadmin_can_create_owner():
    sa = _sa_client()
    r = sa.post(
        "/admin/sa/signup",
        data={
            "full_name": "New Vault",
            "email": "newvault@example.com",
            "password": "password123",
            "role": "owner",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "newvault@example.com" in r.text
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == "newvault@example.com").first()
        assert user is not None
        assert user.role == models.UserRole.owner.value
        self_person = db.query(models.Person).filter(models.Person.user_id == user.id).first()
        assert self_person is not None
    finally:
        db.close()
    listed = sa.get("/admin/sa/users?q=newvault")
    assert "newvault@example.com" in listed.text


def test_web_2fa_login_and_sa_can_turn_it_off():
    from app.security import totp_code

    email = "twofa@example.com"
    data = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Two Factor"},
    ).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    setup = client.post("/auth/totp/setup", headers=headers)
    secret = setup.json()["secret"]
    assert client.post("/auth/totp/enable", json={"code": totp_code(secret)}, headers=headers).status_code == 204

    locked = TestClient(app)
    step = locked.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=False)
    assert step.status_code in (302, 303)
    assert step.headers["location"].endswith("/admin/login/2fa")
    challenge = locked.get("/admin/login/2fa")
    assert challenge.status_code == 200
    assert "6-digit code" in challenge.text
    assert "Waiting on your phone" in challenge.text
    bad = locked.post("/admin/login/2fa", data={"code": "000000"}, follow_redirects=False)
    assert bad.status_code == 401
    assert "not valid" in bad.text
    ok = locked.post("/admin/login/2fa", data={"code": totp_code(secret)}, follow_redirects=False)
    assert ok.status_code in (302, 303)
    assert ok.headers["location"].endswith("/admin/modules")

    sa = _sa_client()
    users = sa.get("/admin/sa/users?q=twofa")
    assert "twofa@example.com" in users.text
    assert "Turn off" in users.text
    db = SessionLocal()
    try:
        target = db.query(models.User).filter(models.User.email == email).first()
        assert target.totp_enabled is True
        user_id = target.id
    finally:
        db.close()
    cleared = sa.post(f"/admin/sa/users/{user_id}/disable-2fa", follow_redirects=True)
    assert cleared.status_code == 200
    assert "Two-factor turned off" in cleared.text
    after = TestClient(app)
    login = after.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=False)
    assert login.status_code in (302, 303)
    assert login.headers["location"].endswith("/admin/modules")


def test_security_page_enables_2fa():
    from app.security import totp_code
    from app.database import SessionLocal
    from app import crypto

    email = "web2fa@example.com"
    session = TestClient(app)
    assert session.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Web Twofa"},
    ).status_code == 201
    login = session.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=False)
    assert login.status_code in (302, 303)
    page = session.get("/admin/security")
    assert page.status_code == 200
    assert "Set up authenticator" in page.text
    start = session.post("/admin/security/setup", follow_redirects=True)
    assert start.status_code == 200
    assert "Confirm with a code" in start.text
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        secret = crypto.decrypt_text(user.totp_secret_enc)
    finally:
        db.close()
    done = session.post("/admin/security/enable", data={"code": totp_code(secret)}, follow_redirects=True)
    assert done.status_code == 200
    assert "Two-factor is on" in done.text
    session.post("/admin/logout")
    gated = session.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=False)
    assert gated.headers["location"].endswith("/admin/login/2fa")


def test_app_can_approve_web_login():
    from app.security import totp_code

    email = "pushlogin@example.com"
    data = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Push Login"},
    ).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    secret = client.post("/auth/totp/setup", headers=headers).json()["secret"]
    assert client.post("/auth/totp/enable", json={"code": totp_code(secret)}, headers=headers).status_code == 204

    web = TestClient(app)
    step = web.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=False)
    assert step.headers["location"].endswith("/admin/login/2fa")
    pending = client.get("/auth/login-challenges", headers=headers)
    assert pending.status_code == 200
    rows = pending.json()
    assert len(rows) == 1
    cid = rows[0]["id"]
    assert client.post(f"/auth/login-challenges/{cid}/approve", headers=headers).status_code == 204
    status = web.get("/admin/login/2fa/status")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "approved"
    modules = web.get("/admin/modules")
    assert modules.status_code == 200
    assert "Your five vaults" in modules.text


def test_app_can_deny_web_login():
    from app.security import totp_code

    email = "denylogin@example.com"
    data = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Deny Login"},
    ).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    secret = client.post("/auth/totp/setup", headers=headers).json()["secret"]
    assert client.post("/auth/totp/enable", json={"code": totp_code(secret)}, headers=headers).status_code == 204

    web = TestClient(app)
    web.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=False)
    cid = client.get("/auth/login-challenges", headers=headers).json()[0]["id"]
    assert client.post(f"/auth/login-challenges/{cid}/deny", headers=headers).status_code == 204
    status = web.get("/admin/login/2fa/status")
    assert status.json()["status"] == "denied"
    page = web.get("/admin/login/2fa", follow_redirects=True)
    assert "denied" in page.text.lower() or "Sign in" in page.text or "Welcome back" in page.text


def test_signup_rejects_duplicate_and_short_password():
    sa = _sa_client()
    short = sa.post(
        "/admin/sa/signup",
        data={"full_name": "X", "email": "short@example.com", "password": "abc", "role": "owner"},
    )
    assert short.status_code == 400
    assert "8 characters" in short.text
    first = sa.post(
        "/admin/sa/signup",
        data={
            "full_name": "Dup User",
            "email": "dup@example.com",
            "password": "password123",
            "role": "owner",
        },
        follow_redirects=False,
    )
    assert first.status_code in (302, 303), first.text[:300]
    again = sa.post(
        "/admin/sa/signup",
        data={
            "full_name": "Dup User",
            "email": "dup@example.com",
            "password": "password123",
            "role": "owner",
        },
    )
    assert again.status_code == 409
    assert "already exists" in again.text
