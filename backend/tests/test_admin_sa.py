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
    settings_page = sa.get("/admin/sa/settings")
    assert settings_page.status_code == 200
    assert "Google Drive app" in settings_page.text
    assert "Google reCAPTCHA" in settings_page.text
    assert "Login rate limit" in settings_page.text
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
    assert "Authenticator is on" in done.text
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


def _user_id(email: str) -> str:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        assert user is not None
        return user.id
    finally:
        db.close()


def test_superadmin_can_block_and_unblock_user():
    sa = _sa_client()
    created = client.post(
        "/auth/register",
        json={"email": "blocked@example.com", "password": "password123", "full_name": "Soon Blocked"},
    )
    assert created.status_code == 201, created.text
    uid = _user_id("blocked@example.com")

    blocked = sa.post(f"/admin/sa/users/{uid}/block", follow_redirects=False)
    assert blocked.status_code in (302, 303)
    assert "notice=blocked" in blocked.headers["location"]
    users = sa.get("/admin/sa/users")
    assert "blocked@example.com" in users.text
    assert "Unblock" in users.text

    web = TestClient(app)
    login = web.post("/admin/login", data={"email": "blocked@example.com", "password": "password123"})
    assert login.status_code == 401
    assert "blocked" in login.text.lower()

    api = client.post("/auth/login", data={"username": "blocked@example.com", "password": "password123"})
    assert api.status_code == 401
    assert "blocked" in api.json()["detail"].lower()

    restored = sa.post(f"/admin/sa/users/{uid}/unblock", follow_redirects=False)
    assert restored.status_code in (302, 303)
    ok = web.post("/admin/login", data={"email": "blocked@example.com", "password": "password123"}, follow_redirects=False)
    assert ok.status_code in (302, 303)
    assert ok.headers["location"].endswith("/admin/modules")


def test_superadmin_cannot_block_self():
    sa = _sa_client()
    uid = _user_id("root@example.com")
    r = sa.post(f"/admin/sa/users/{uid}/block", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "notice=self" in r.headers["location"]
    db = SessionLocal()
    try:
        me = db.query(models.User).filter(models.User.email == "root@example.com").first()
        assert me.blocked is False
    finally:
        db.close()


def test_app_approve_without_totp_gates_web_login():
    email = "deviceonly@example.com"
    data = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Device Only"},
    ).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    session = TestClient(app)
    first = session.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=False)
    assert first.headers["location"].endswith("/admin/modules")
    on = session.post("/admin/security/app-approve", data={"enabled": "1"}, follow_redirects=False)
    assert on.status_code in (302, 303)
    assert "app-on" in on.headers["location"]
    page = session.get("/admin/security")
    assert page.status_code == 200
    assert "Approve from the app" in page.text
    session.post("/admin/logout")

    web = TestClient(app)
    step = web.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=False)
    assert step.headers["location"].endswith("/admin/login/2fa")
    wait = web.get("/admin/login/2fa")
    assert wait.status_code == 200
    assert "Verify code" not in wait.text
    assert "Vault app" in wait.text

    pending = client.get("/auth/login-challenges", headers=headers)
    assert pending.status_code == 200
    rows = pending.json()
    assert len(rows) == 1
    cid = rows[0]["id"]
    assert client.post(f"/auth/login-challenges/{cid}/approve", headers=headers).status_code == 204
    status = web.get("/admin/login/2fa/status")
    assert status.json()["status"] == "approved"
    modules = web.get("/admin/modules")
    assert modules.status_code == 200
    assert "Your five vaults" in modules.text


def test_superadmin_can_clear_app_approve():
    email = "lostphone@example.com"
    created = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Lost Phone"},
    )
    assert created.status_code == 201
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        user.app_approve = True
        db.commit()
        uid = user.id
    finally:
        db.close()
    sa = _sa_client()
    cleared = sa.post(f"/admin/sa/users/{uid}/disable-app-approve", follow_redirects=False)
    assert cleared.status_code in (302, 303)
    assert "app-off" in cleared.headers["location"]
    web = TestClient(app)
    login = web.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=False)
    assert login.status_code in (302, 303)
    assert login.headers["location"].endswith("/admin/modules")


def _pending_qr_id(email: str) -> str | None:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            return None
        row = (
            db.query(models.LoginChallenge)
            .filter(
                models.LoginChallenge.user_id == user.id,
                models.LoginChallenge.kind == "qr",
                models.LoginChallenge.status == "pending",
            )
            .order_by(models.LoginChallenge.created_at.desc())
            .first()
        )
        return row.id if row else None
    finally:
        db.close()


def test_qr_payload_parse():
    from app.login_challenge import parse_qr_payload, qr_payload
    cid = "a" * 32
    assert parse_qr_payload(qr_payload(cid)) == cid
    assert parse_qr_payload(cid.upper()) == cid
    assert parse_qr_payload("https://evil.example/" + cid) is None


def test_qr_login_unknown_email_does_not_leak():
    web = TestClient(app)
    page = web.get("/admin/login/qr")
    assert page.status_code == 200
    assert "Scan from the phone" in page.text
    wait = web.post("/admin/login/qr", data={"email": "missing-qr@example.com"})
    assert wait.status_code == 200
    assert "Scan to sign in" in wait.text
    assert "qr-frame" in wait.text
    assert _pending_qr_id("missing-qr@example.com") is None


def test_qr_login_app_grant_redirects_home():
    email = "qrlogin@example.com"
    data = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "QR Login"},
    ).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    web = TestClient(app)
    wait = web.post("/admin/login/qr", data={"email": email})
    assert wait.status_code == 200
    assert "Scan to sign in" in wait.text
    assert "Verify code" not in wait.text
    cid = _pending_qr_id(email)
    assert cid
    listed = client.get("/auth/login-challenges", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []
    peeked = client.get(f"/auth/login-challenges/{cid}", headers=headers)
    assert peeked.status_code == 200
    assert peeked.json()["id"] == cid
    assert client.post(f"/auth/login-challenges/{cid}/approve", headers=headers).status_code == 204
    status = web.get("/admin/login/qr/status")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "approved"
    assert body["redirect"] == "/admin/modules"
    home = web.get("/admin/modules")
    assert home.status_code == 200
    assert "Your five vaults" in home.text


def test_qr_login_wrong_account_cannot_grant():
    owner = client.post(
        "/auth/register",
        json={"email": "qrowner@example.com", "password": "password123", "full_name": "QR Owner"},
    ).json()
    other = client.post(
        "/auth/register",
        json={"email": "qrother@example.com", "password": "password123", "full_name": "QR Other"},
    ).json()
    web = TestClient(app)
    web.post("/admin/login/qr", data={"email": "qrowner@example.com"})
    cid = _pending_qr_id("qrowner@example.com")
    assert cid
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/auth/login-challenges/{cid}", headers=other_headers).status_code == 404
    assert client.post(f"/auth/login-challenges/{cid}/approve", headers=other_headers).status_code == 404
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    assert client.post(f"/auth/login-challenges/{cid}/deny", headers=owner_headers).status_code == 204
    status = web.get("/admin/login/qr/status")
    assert status.json()["status"] == "denied"


def test_qr_login_blocked_account_is_dummy_wait():
    email = "qrblocked@example.com"
    created = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "QR Blocked"},
    )
    assert created.status_code == 201
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        user.blocked = True
        db.commit()
    finally:
        db.close()
    web = TestClient(app)
    wait = web.post("/admin/login/qr", data={"email": email})
    assert wait.status_code == 200
    assert "Scan to sign in" in wait.text
    assert _pending_qr_id(email) is None


def test_superadmin_saves_google_app():
    from app.drive_backup import oauth_creds, oauth_ready

    sa = _sa_client()
    saved = sa.post(
        "/admin/sa/settings/google",
        data={"client_id": "sa-id.apps.googleusercontent.com", "client_secret": "sa-secret-value"},
        follow_redirects=False,
    )
    assert saved.status_code in (302, 303)
    db = SessionLocal()
    try:
        assert oauth_ready(db) is True
        assert oauth_creds(db) == ("sa-id.apps.googleusercontent.com", "sa-secret-value")
    finally:
        db.close()
    page = sa.get("/admin/sa/settings")
    assert page.status_code == 200
    assert "sa-id.apps.googleusercontent.com" in page.text
    assert "sa-secret-value" not in page.text
    assert "Ready" in page.text


_FAKE_SA = (
    '{"type":"service_account","project_id":"raspberrypi-valut",'
    '"private_key":"-----BEGIN PRIVATE KEY-----\\nfake\\n-----END PRIVATE KEY-----\\n",'
    '"client_email":"firebase-adminsdk@raspberrypi-valut.iam.gserviceaccount.com"}'
)


def test_superadmin_saves_fcm_service_account():
    from app.server_settings import fcm_service_account

    sa = _sa_client()
    saved = sa.post(
        "/admin/sa/settings/fcm",
        data={"service_account": _FAKE_SA},
        follow_redirects=False,
    )
    assert saved.status_code in (302, 303)
    assert "saved=fcm" in (saved.headers.get("location") or "")
    db = SessionLocal()
    try:
        account = fcm_service_account(db)
        assert account is not None
        assert account["project_id"] == "raspberrypi-valut"
        assert account["client_email"].startswith("firebase-adminsdk@")
    finally:
        db.close()
    page = sa.get("/admin/sa/settings")
    assert page.status_code == 200
    assert "BEGIN PRIVATE KEY" not in page.text
    assert "raspberrypi-valut" in page.text
    assert "Firebase Cloud Messaging" in page.text
    assert "Ready" in page.text


def test_superadmin_rejects_invalid_fcm_json():
    sa = _sa_client()
    bad = sa.post(
        "/admin/sa/settings/fcm",
        data={"service_account": "AAAA-not-a-service-account"},
        follow_redirects=False,
    )
    assert bad.status_code in (302, 303)
    assert "err=fcm" in (bad.headers.get("location") or "")


_HARDENING_KEYS = (
    "recaptcha_site_key", "recaptcha_secret", "recaptcha_enabled",
    "login_max_attempts", "login_lockout_minutes", "login_rate_limit_enabled",
)


def _clear_hardening():
    db = SessionLocal()
    try:
        db.query(models.ServerSetting).filter(
            models.ServerSetting.key.in_(_HARDENING_KEYS),
        ).delete(synchronize_session=False)
        db.query(models.LoginAttempt).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_superadmin_saves_recaptcha():
    sa = _sa_client()
    try:
        saved = sa.post(
            "/admin/sa/settings/recaptcha",
            data={"enabled": "1", "site_key": "sa-site-key", "secret": "sa-secret-key"},
            follow_redirects=False,
        )
        assert saved.status_code in (302, 303)
        assert "saved=recaptcha" in (saved.headers.get("location") or "")
        assert "err=recaptcha" not in (saved.headers.get("location") or "")
        page = sa.get("/admin/sa/settings")
        assert page.status_code == 200
        assert "sa-site-key" in page.text
        assert "sa-secret-key" not in page.text
        login = TestClient(app).get("/admin/login")
        assert "g-recaptcha" in login.text
        assert "sa-site-key" in login.text
        blocked = TestClient(app).post(
            "/admin/login",
            data={"email": "root@example.com", "password": "password123"},
        )
        assert blocked.status_code == 401
        assert "not a robot" in blocked.text
        api = client.post("/auth/login", data={"username": "root@example.com", "password": "password123"})
        assert api.status_code == 200
    finally:
        _clear_hardening()


def test_superadmin_recaptcha_needs_both_keys():
    sa = _sa_client()
    try:
        saved = sa.post(
            "/admin/sa/settings/recaptcha",
            data={"enabled": "1", "site_key": "only-site", "secret": ""},
            follow_redirects=False,
        )
        assert saved.status_code in (302, 303)
        assert "err=recaptcha" in (saved.headers.get("location") or "")
        login = TestClient(app).get("/admin/login")
        assert "g-recaptcha" not in login.text
    finally:
        _clear_hardening()


def test_superadmin_saves_login_rate_limit():
    sa = _sa_client()
    email = "ratelimit-sa@example.com"
    created = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Rate Limit SA"},
    )
    assert created.status_code == 201, created.text
    try:
        saved = sa.post(
            "/admin/sa/settings/lockout",
            data={"enabled": "1", "max_attempts": "2", "lockout_minutes": "20"},
            follow_redirects=False,
        )
        assert saved.status_code in (302, 303)
        assert "saved=lockout" in (saved.headers.get("location") or "")
        page = sa.get("/admin/sa/settings")
        assert page.status_code == 200
        assert 'value="2"' in page.text
        assert 'value="20"' in page.text
        web = TestClient(app)
        web.post("/admin/login", data={"email": email, "password": "nope"})
        web.post("/admin/login", data={"email": email, "password": "nope"})
        locked = web.post("/admin/login", data={"email": email, "password": "password123"})
        assert locked.status_code == 401
        assert "Too many failed attempts" in locked.text
        api = client.post("/auth/login", data={"username": email, "password": "password123"})
        assert api.status_code == 429
    finally:
        _clear_hardening()


def test_superadmin_can_turn_off_rate_limit():
    sa = _sa_client()
    email = "nolock@example.com"
    created = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "No Lock"},
    )
    assert created.status_code == 201, created.text
    try:
        sa.post(
            "/admin/sa/settings/lockout",
            data={"max_attempts": "2", "lockout_minutes": "15"},
            follow_redirects=False,
        )
        web = TestClient(app)
        web.post("/admin/login", data={"email": email, "password": "nope"})
        web.post("/admin/login", data={"email": email, "password": "nope"})
        ok = web.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=False)
        assert ok.status_code in (302, 303)
        assert ok.headers["location"].endswith("/admin/modules")
    finally:
        _clear_hardening()


def test_owner_cannot_open_server_settings():
    owner = TestClient(app)
    r = owner.post(
        "/auth/register",
        json={"email": "nosettings@example.com", "password": "password123", "full_name": "No Settings"},
    )
    assert r.status_code == 201
    owner.post("/admin/login", data={"email": "nosettings@example.com", "password": "password123"}, follow_redirects=False)
    denied = owner.get("/admin/sa/settings", follow_redirects=False)
    assert denied.status_code in (302, 303)
    assert "/admin/sa/settings" not in (denied.headers.get("location") or "")
    posted = owner.post(
        "/admin/sa/settings/recaptcha",
        data={"enabled": "1", "site_key": "x", "secret": "y"},
        follow_redirects=False,
    )
    assert posted.status_code in (302, 303)
    assert "/admin/sa/settings" not in (posted.headers.get("location") or "")
