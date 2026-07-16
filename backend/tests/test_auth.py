import uuid

import pytest
from pydantic import ValidationError

from app.core.exceptions import AuthenticationException
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.schemas.user import ChangePasswordRequest


def test_password_hashing():
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)

def test_password_complexity_validation():
    # Weak password - missing number
    with pytest.raises(ValidationError) as excinfo:
        ChangePasswordRequest(current_password="oldPassword1!", new_password="UppercaseNoDigit!")
    assert "at least one digit" in str(excinfo.value)

    # Weak password - missing uppercase
    with pytest.raises(ValidationError) as excinfo:
        ChangePasswordRequest(current_password="oldPassword1!", new_password="lowercase123!")
    assert "at least one uppercase letter" in str(excinfo.value)

    # Weak password - missing special character
    with pytest.raises(ValidationError) as excinfo:
        ChangePasswordRequest(current_password="oldPassword1!", new_password="UppercaseAndDigit123")
    assert "at least one special character" in str(excinfo.value)

    # Strong password - passed
    req = ChangePasswordRequest(current_password="oldPassword1!", new_password="StrongPassword123!")
    assert req.new_password == "StrongPassword123!"

def test_jwt_token_flow():
    subject = str(uuid.uuid4())
    token = create_access_token(subject=subject, extra_claims={"role": "admin"})

    decoded = decode_access_token(token)
    assert decoded["sub"] == subject
    assert decoded["role"] == "admin"
    assert decoded["type"] == "access"

def test_jwt_decode_failure():
    with pytest.raises(AuthenticationException):
        decode_access_token("invalid.token.signature")
