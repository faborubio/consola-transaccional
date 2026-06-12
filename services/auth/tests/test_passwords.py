from app.services.passwords import hash_password, verify_password


def test_roundtrip():
    hashed = hash_password("Demo1234!")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "Demo1234!")


def test_password_incorrecta():
    hashed = hash_password("Demo1234!")
    assert not verify_password(hashed, "otraClave99")


def test_hash_invalido_no_explota():
    assert not verify_password("basura-no-es-hash", "Demo1234!")
