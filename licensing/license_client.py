"""
licensing/license_client.py
===========================
SDK de licenciamento para o VEO3 Automator.

Único módulo responsável pela lógica de ativação, validação e
desativação de licenças. Comunica-se com Edge Functions do Supabase.
"""

import hashlib
import hmac
import json
import os
import platform
import socket
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class LicenseStatus(Enum):
    ACTIVE = "active"
    NOT_ACTIVATED = "not_activated"
    REVOKED = "revoked"
    GRACE_PERIOD = "grace_period"
    EXPIRED_OFFLINE = "expired_offline"
    EXPIRED = "expired"


@dataclass
class ActivationResult:
    success: bool
    token: Optional[str] = None
    license_info: Optional[dict] = None
    error: Optional[str] = None


# ── Configuration ─────────────────────────────────────────────────────────────

SUPABASE_URL = "https://ypndvfrqjahxvgmhvyjf.supabase.co"
FUNCTIONS_BASE = f"{SUPABASE_URL}/functions/v1"
KEYRING_SERVICE = "VEO3Automator"
KEYRING_USERNAME = "license_token"
GRACE_DAYS = 7
APP_VERSION = "2.0.0"


# ── Fingerprint ───────────────────────────────────────────────────────────────

def _get_disk_serial() -> str:
    """Get disk serial number (best effort)."""
    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["diskutil", "info", "/"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "Volume UUID" in line or "Disk / Partition UUID" in line:
                    return line.split(":")[-1].strip()
        elif sys.platform == "win32":
            result = subprocess.run(
                ["wmic", "diskdrive", "get", "SerialNumber"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if len(lines) > 1:
                return lines[1]
    except Exception:
        pass
    return "unknown-disk"


def generate_fingerprint() -> str:
    """Generate SHA-256 fingerprint from hardware identifiers."""
    mac_addr = str(uuid.getnode())
    disk_serial = _get_disk_serial()
    cpu_model = platform.processor() or "unknown-cpu"
    hostname = socket.gethostname()

    raw = f"{mac_addr}|{disk_serial}|{cpu_model}|{hostname}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── Keyring (secure token storage) ────────────────────────────────────────────

def _store_token(token: str) -> None:
    """Store JWT in OS keychain."""
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
    except Exception:
        # Fallback: store in DATA_DIR (less secure but functional)
        _fallback_token_path().write_text(token, encoding="utf-8")


def _read_token() -> Optional[str]:
    """Read JWT from OS keychain."""
    try:
        import keyring
        token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if token:
            return token
    except Exception:
        pass
    # Fallback
    p = _fallback_token_path()
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return None


def _delete_token() -> None:
    """Remove JWT from OS keychain."""
    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        pass
    p = _fallback_token_path()
    if p.exists():
        p.unlink()


def _fallback_token_path() -> Path:
    return _data_dir() / ".license_token"


# ── Cache (offline grace) ────────────────────────────────────────────────────

def _data_dir() -> Path:
    raw = os.environ.get("VEO3_DATA_DIR")
    if raw:
        return Path(raw)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "VEO3"
    return Path.home() / "Library" / "Application Support" / "VEO3"


def _cache_path() -> Path:
    return _data_dir() / "license_cache.json"


def _sign_cache(data: dict, fingerprint: str) -> str:
    """HMAC-SHA256 of the cache content using fingerprint as key."""
    raw = json.dumps(data, sort_keys=True).encode("utf-8")
    return hmac.new(fingerprint.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def _write_cache(data: dict) -> None:
    fp = generate_fingerprint()
    data["_hmac"] = _sign_cache(data, fp)
    _cache_path().parent.mkdir(parents=True, exist_ok=True)
    _cache_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_cache() -> Optional[dict]:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        stored_hmac = data.pop("_hmac", None)
        fp = generate_fingerprint()
        expected = _sign_cache(data, fp)
        if not hmac.compare_digest(stored_hmac or "", expected):
            return None  # Tampered
        return data
    except Exception:
        return None


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _post(endpoint: str, body: Optional[dict] = None, token: Optional[str] = None) -> dict:
    """POST to Edge Function. Returns dict with 'status' and parsed JSON."""
    import requests

    url = f"{FUNCTIONS_BASE}/{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.post(url, json=body, headers=headers, timeout=15)
        return {"status": resp.status_code, "data": resp.json()}
    except requests.ConnectionError:
        return {"status": 0, "data": {}, "offline": True}
    except requests.Timeout:
        return {"status": 0, "data": {}, "offline": True}
    except Exception as e:
        return {"status": -1, "data": {"error": str(e)}}


def _get(endpoint: str, token: Optional[str] = None) -> dict:
    """GET to Edge Function."""
    import requests

    url = f"{FUNCTIONS_BASE}/{endpoint}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        return {"status": resp.status_code, "data": resp.json()}
    except requests.ConnectionError:
        return {"status": 0, "data": {}, "offline": True}
    except requests.Timeout:
        return {"status": 0, "data": {}, "offline": True}
    except Exception as e:
        return {"status": -1, "data": {"error": str(e)}}


# ── License Client ────────────────────────────────────────────────────────────

class LicenseClient:
    """Main licensing API — single point of contact for launcher.py and app.py."""

    def __init__(self) -> None:
        self._fingerprint = generate_fingerprint()

    # ── Activate ──────────────────────────────────────────────────────────

    def activate(self, license_key: str) -> ActivationResult:
        """Activate a license key on this device."""
        os_name = "macos" if sys.platform == "darwin" else "windows"
        os_version = platform.version()
        hostname = socket.gethostname()

        resp = _post("license-activate", body={
            "licenseKey": license_key,
            "fingerprint": self._fingerprint,
            "os": os_name,
            "osVersion": os_version,
            "hostname": hostname,
            "appVersion": APP_VERSION,
        })

        if resp.get("offline"):
            return ActivationResult(
                success=False,
                error="Sem conexão com a internet. Tente novamente.",
            )

        status = resp["status"]
        data = resp["data"]

        if status == 200:
            token = data.get("token", "")
            _store_token(token)

            lic = data.get("license", {})
            _write_cache({
                "last_validated_at": datetime.now(timezone.utc).isoformat(),
                "license_key_hint": license_key[:4] + "-****-****-****-" + license_key[-4:],
                "plan": lic.get("plan", ""),
                "expires_at": lic.get("expiresAt"),
                "max_devices": lic.get("maxDevices", 3),
                "active_devices": lic.get("activeDevices", 1),
                "status": "active",
            })

            return ActivationResult(
                success=True,
                token=token,
                license_info=lic,
            )

        error_map = {
            404: "Chave de licença não encontrada.",
            403: "Licença suspensa ou revogada.",
            402: "Licença expirada.",
            429: f"Limite de dispositivos atingido ({data.get('maxDevices', '?')}).",
        }
        return ActivationResult(
            success=False,
            error=error_map.get(status, data.get("error", "Erro desconhecido.")),
        )

    # ── Validate ──────────────────────────────────────────────────────────

    def validate(self) -> LicenseStatus:
        """Validate current license. Returns status enum."""
        token = _read_token()
        if not token:
            return LicenseStatus.NOT_ACTIVATED

        resp = _post("license-validate", token=token)

        # Offline path
        if resp.get("offline"):
            return self._check_offline_grace()

        status = resp["status"]
        data = resp["data"]

        if status == 200:
            # Update cache
            lic = data.get("license", {})
            _write_cache({
                "last_validated_at": datetime.now(timezone.utc).isoformat(),
                "license_key_hint": self._get_cached_key_hint(),
                "plan": lic.get("plan", ""),
                "expires_at": lic.get("expiresAt"),
                "max_devices": lic.get("maxDevices", 3),
                "active_devices": lic.get("activeDevices", 0),
                "status": "active",
            })

            # Token rotation
            new_token = data.get("token")
            if new_token:
                _store_token(new_token)

            return LicenseStatus.ACTIVE

        if status == 401:
            reason = data.get("reason", "")
            if reason in ("revoked", "device_revoked"):
                return LicenseStatus.REVOKED
            # Token expired / invalid → treat as not activated
            _delete_token()
            return LicenseStatus.NOT_ACTIVATED

        if status == 402:
            return LicenseStatus.EXPIRED

        # Other errors → try offline grace
        return self._check_offline_grace()

    # ── Deactivate ────────────────────────────────────────────────────────

    def deactivate(self) -> bool:
        """Deactivate this device. Returns True on success."""
        token = _read_token()
        if not token:
            return False

        resp = _post("license-deactivate", token=token)

        # Even if offline, clean up locally
        _delete_token()
        try:
            _cache_path().unlink()
        except Exception:
            pass

        if resp.get("offline"):
            return True  # Local cleanup done; server will see device inactive

        return resp.get("status") == 200

    # ── Stored info ───────────────────────────────────────────────────────

    def get_stored_license_info(self) -> Optional[dict]:
        """Read cached license info without hitting the server."""
        return _read_cache()

    # ── Private ───────────────────────────────────────────────────────────

    def _check_offline_grace(self) -> LicenseStatus:
        cache = _read_cache()
        if not cache:
            return LicenseStatus.NOT_ACTIVATED

        last_str = cache.get("last_validated_at")
        if not last_str:
            return LicenseStatus.EXPIRED_OFFLINE

        try:
            last = datetime.fromisoformat(last_str)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except Exception:
            return LicenseStatus.EXPIRED_OFFLINE

        now = datetime.now(timezone.utc)
        if now - last <= timedelta(days=GRACE_DAYS):
            return LicenseStatus.GRACE_PERIOD

        return LicenseStatus.EXPIRED_OFFLINE

    def _get_cached_key_hint(self) -> str:
        cache = _read_cache()
        if cache:
            return cache.get("license_key_hint", "VEO3-****-****-****-****")
        return "VEO3-****-****-****-****"
