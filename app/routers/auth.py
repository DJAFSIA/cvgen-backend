from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.utilisateur import Utilisateur
from app.models.profil import Profil
from app.schemas.utilisateur import UtilisateurCreate, UtilisateurLogin, Token, UtilisateurResponse

router = APIRouter()

@router.post("/inscription", response_model=Token, status_code=201)
def inscription(data: UtilisateurCreate, db: Session = Depends(get_db)):
    existant = db.query(Utilisateur).filter(Utilisateur.email == data.email).first()
    if existant:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    utilisateur = Utilisateur(
        nom=data.nom,
        prenom=data.prenom,
        email=data.email,
        mot_de_passe=hash_password(data.mot_de_passe),
    )
    db.add(utilisateur)
    db.flush()

    profil = Profil(utilisateur_id=utilisateur.id)
    db.add(profil)
    db.commit()
    db.refresh(utilisateur)

    token = create_access_token({"sub": str(utilisateur.id)})
    return Token(access_token=token, utilisateur=utilisateur)


@router.post("/login", response_model=Token)
def login(data: UtilisateurLogin, db: Session = Depends(get_db)):
    utilisateur = db.query(Utilisateur).filter(Utilisateur.email == data.email).first()
    if not utilisateur or not verify_password(data.mot_de_passe, utilisateur.mot_de_passe):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )
    token = create_access_token({"sub": str(utilisateur.id)})
    return Token(access_token=token, utilisateur=utilisateur)


@router.get("/me", response_model=UtilisateurResponse)
def me(db: Session = Depends(get_db), current_user: Utilisateur = Depends(lambda: None)):
    from app.core.security import get_current_user
    return current_user
