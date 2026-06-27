"""
Autorizace - jednoduchý systém rolí na základě API klíčů.

Rozlišuje dva kroky, které se v praxi často pletou:
- AUTENTIZACE - je tenhle klíč vůbec platný? (kdo jsi)
- AUTORIZACE  - smí tenhle klíč provést TUHLE konkrétní akci? (co můžeš dělat)

Dvě role:
- "read"  - může jen číst data (GET endpointy)
- "admin" - může navíc vynutit nové stažení dat a vidět provozní statistiky

V produkčním prostředí by se tohle nahradilo OAuth2/JWT a rolemi v databázi,
ale princip - ověření identity, přiřazení role, kontrola oprávnění před akcí -
je úplně stejný.
"""
import logging

from fastapi import Header, HTTPException

import config

logger = logging.getLogger(__name__)

# Pořadí rolí - admin smí vše, co smí read, a ještě něco navíc.
_ROLE_RANK = {"read": 1, "admin": 2}


def _load_key_roles() -> dict[str, str]:
    """Sestaví mapování {api_klic: role} z proměnných prostředí."""
    roles: dict[str, str] = {}
    if config.API_KEY_READ:
        roles[config.API_KEY_READ] = "read"
    if config.API_KEY_ADMIN:
        roles[config.API_KEY_ADMIN] = "admin"
    return roles


def require_role(minimum_role: str):
    """
    Factory funkce - vrátí FastAPI dependency, která ověří API klíč
    a zkontroluje, že jeho role je dostatečná pro danou akci.

    Použití v endpointu:
        @app.get("/neco")
        def neco(role: str = Depends(require_role("admin"))):
            ...
    """

    async def dependency(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
        key_roles = _load_key_roles()

        if not key_roles:
            logger.error("Žádné API klíče nejsou nastaveny v .env (API_KEY_READ/API_KEY_ADMIN).")
            raise HTTPException(
                status_code=500,
                detail="Server nemá nakonfigurované API klíče - kontaktuj administrátora.",
            )

        role = key_roles.get(x_api_key)

        # --- Autentizace: je klíč platný? ---
        if role is None:
            logger.warning("Pokus o přístup s neplatným API klíčem.")
            raise HTTPException(status_code=401, detail="Neplatný API klíč.")

        # --- Autorizace: stačí role na tuhle akci? ---
        if _ROLE_RANK[role] < _ROLE_RANK[minimum_role]:
            logger.warning(
                "Klíč s rolí '%s' se pokusil o akci vyžadující roli '%s'.", role, minimum_role
            )
            raise HTTPException(
                status_code=403,
                detail=f"Tato akce vyžaduje roli '{minimum_role}', tvůj klíč má roli '{role}'.",
            )

        return role

    return dependency


require_read = require_role("read")
require_admin = require_role("admin")
