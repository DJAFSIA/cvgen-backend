from fastapi import HTTPException


def http_error(status_code: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    """Erreur API avec un code stable (traduit par le frontend) et un message de secours.

    Corps de reponse : {"detail": {"code": "...", "message": "..."}}
    """
    return HTTPException(status_code=status_code, detail={"code": code, "message": message}, headers=headers)
