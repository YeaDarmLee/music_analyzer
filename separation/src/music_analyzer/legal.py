"""Single source of truth for legal policy versions and consent validation.

Consent is independent of the authentication method: any provider (email today, SNS later)
must hand a verified user id to `AuthStore.record_consents` after `require_consents` passes.
"""
from __future__ import annotations

TERMS_VERSION = "2026-10-08"
PRIVACY_VERSION = "2026-10-08"
COPYRIGHT_POLICY_VERSION = "2026-10-08"
RIGHTS_CONFIRMATION_VERSION = COPYRIGHT_POLICY_VERSION  # the checkbox text is defined by the copyright policy

REQUIRED_CONSENTS = {"TERMS": TERMS_VERSION, "PRIVACY": PRIVACY_VERSION}


class ConsentError(ValueError):
    pass


def require_consents(consents):
    """Return the validated {type: version} map or raise; the account must not be created otherwise."""
    if not isinstance(consents, dict):
        raise ConsentError("이용약관과 개인정보 수집·이용에 동의해 주세요.")
    for kind, version in REQUIRED_CONSENTS.items():
        if consents.get(kind) != version:
            raise ConsentError("이용약관과 개인정보 수집·이용에 동의해 주세요.")
    return dict(REQUIRED_CONSENTS)


def public_versions():
    return {"terms": TERMS_VERSION, "privacy": PRIVACY_VERSION, "copyright": COPYRIGHT_POLICY_VERSION}
