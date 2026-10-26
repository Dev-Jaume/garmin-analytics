"""Backend Windows explícit: cap fallback a fitxers ni lectura d'entorn."""

import sys

SERVICE = "GarminRunningAnalytics"
ACCOUNT = "personal-api-key"


class CredentialUnavailable(RuntimeError):
    pass


class WindowsCredentials:
    def __init__(self, backend=None):
        self._backend = backend

    def _store(self):
        if self._backend is None:
            if sys.platform != "win32":
                raise CredentialUnavailable("Cal Windows Credential Manager")
            from keyring.backends.Windows import WinVaultKeyring

            self._backend = WinVaultKeyring()
        return self._backend

    def save(self, key: str):
        if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise CredentialUnavailable("Format de clau invàlid")
        try:
            self._store().set_password(SERVICE, ACCOUNT, key)
        except Exception:
            raise CredentialUnavailable("No s'ha pogut desar al gestor segur de Windows") from None

    def get(self):
        try:
            return self._store().get_password(SERVICE, ACCOUNT)
        except Exception:
            raise CredentialUnavailable("Gestor segur de Windows no disponible") from None

    def delete(self):
        try:
            self._store().delete_password(SERVICE, ACCOUNT)
        except Exception:
            raise CredentialUnavailable("No s'ha pogut eliminar la credencial") from None
