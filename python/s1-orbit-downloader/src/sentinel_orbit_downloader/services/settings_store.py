from __future__ import annotations

import base64
import ctypes
from dataclasses import dataclass
from pathlib import Path

from sentinel_orbit_downloader.storage.db import connect, get_setting, set_setting


EARTHDATA_USERNAME_KEY = "earthdata.username"
EARTHDATA_PASSWORD_KEY = "earthdata.password_dpapi"


@dataclass(frozen=True)
class EarthdataSettings:
    username: str | None
    has_password: bool


def get_earthdata_settings(db_path: Path) -> EarthdataSettings:
    with connect(db_path) as connection:
        username = get_setting(connection, EARTHDATA_USERNAME_KEY)
        encrypted_password = get_setting(connection, EARTHDATA_PASSWORD_KEY)
    return EarthdataSettings(
        username=username,
        has_password=bool(encrypted_password),
    )


def get_saved_earthdata_credentials(db_path: Path) -> tuple[str | None, str | None]:
    with connect(db_path) as connection:
        username = get_setting(connection, EARTHDATA_USERNAME_KEY)
        encrypted_password = get_setting(connection, EARTHDATA_PASSWORD_KEY)
    if not encrypted_password:
        return username, None
    return username, dpapi_decrypt(encrypted_password)


def save_earthdata_credentials(db_path: Path, username: str, password: str) -> EarthdataSettings:
    final_username = username.strip()
    if not final_username:
        raise ValueError("Earthdata username cannot be empty")
    if not password:
        raise ValueError("Earthdata password cannot be empty")

    encrypted_password = dpapi_encrypt(password)
    with connect(db_path) as connection:
        set_setting(connection, EARTHDATA_USERNAME_KEY, final_username)
        set_setting(connection, EARTHDATA_PASSWORD_KEY, encrypted_password)
    return EarthdataSettings(username=final_username, has_password=True)


def clear_earthdata_credentials(db_path: Path) -> None:
    with connect(db_path) as connection:
        connection.execute(
            "DELETE FROM settings WHERE key IN (?, ?)",
            (EARTHDATA_USERNAME_KEY, EARTHDATA_PASSWORD_KEY),
        )


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


try:
    kernel32 = ctypes.windll.kernel32
    crypt32 = ctypes.windll.crypt32
except AttributeError:
    kernel32 = None
    crypt32 = None


CRYPTPROTECT_UI_FORBIDDEN = 0x01


def dpapi_encrypt(value: str) -> str:
    ensure_windows_dpapi()
    raw = value.encode("utf-8")
    in_blob = bytes_to_blob(raw)
    out_blob = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "sentinel-orbit-downloader",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        encrypted = blob_to_bytes(out_blob)
    finally:
        free_blob(out_blob)
    return base64.b64encode(encrypted).decode("ascii")


def dpapi_decrypt(encoded_value: str) -> str:
    ensure_windows_dpapi()
    encrypted = base64.b64decode(encoded_value.encode("ascii"))
    in_blob = bytes_to_blob(encrypted)
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        decrypted = blob_to_bytes(out_blob)
    finally:
        free_blob(out_blob)
    return decrypted.decode("utf-8")


def ensure_windows_dpapi() -> None:
    if crypt32 is None or kernel32 is None:
        raise RuntimeError("Earthdata local credential storage currently requires Windows")


def bytes_to_blob(value: bytes) -> DATA_BLOB:
    if not value:
        buffer = (ctypes.c_ubyte * 1)()
        return DATA_BLOB(0, ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    return DATA_BLOB(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))


def blob_to_bytes(blob: DATA_BLOB) -> bytes:
    if not blob.cbData or not blob.pbData:
        return b""
    return bytes(ctypes.string_at(blob.pbData, blob.cbData))


def free_blob(blob: DATA_BLOB) -> None:
    if blob.pbData:
        kernel32.LocalFree(blob.pbData)
