import os
import urllib.request
import urllib.error
import json
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db import get_db

# Local JWT secret for testing/mock tokens
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-local-triage-jwt-key")
JWT_ALGORITHM = "HS256"

security = HTTPBearer()

def get_supabase_project_ref():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    try:
        if "postgres." in db_url:
            part = db_url.split("postgres.")[1]
            ref = part.split(":")[0].split("@")[0]
            return ref
    except Exception:
        pass
    return None

def verify_supabase_token(token: str) -> dict:
    """
    Validates the token against the Supabase Auth API.
    Returns the user data dict if valid, else returns None.
    """
    project_ref = get_supabase_project_ref()
    if not project_ref:
        return None
        
    url = f"https://{project_ref}.supabase.co/auth/v1/user"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                user_data = json.loads(response.read().decode())
                return user_data
    except Exception:
        return None
    return None

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> dict:
    token = credentials.credentials
    
    # 1. Check if it is a mock token for local dev/testing
    if token.startswith("mock-token-"):
        role = token.split("mock-token-")[1]
        user_row = db.execute(
            text("SELECT user_id, role, display_name FROM UserRole WHERE role = :role LIMIT 1"),
            {"role": role}
        ).fetchone()
        
        if not user_row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"No seeded user found with role '{role}' for mock token authentication."
            )
            
        return {
            "user_id": str(user_row[0]),
            "role": user_row[1],
            "display_name": user_row[2],
            "email": f"{role}@test.com"
        }
        
    # 2. Try to decode the token locally first
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")
        if user_id and email:
            user_row = db.execute(
                text("SELECT role, display_name FROM UserRole WHERE user_id = :id"),
                {"id": user_id}
            ).fetchone()
            if user_row:
                return {
                    "user_id": user_id,
                    "role": user_row[0],
                    "display_name": user_row[1],
                    "email": email
                }
    except jwt.PyJWTError:
        pass
        
    # 3. Validate against live Supabase Auth API
    supabase_user = verify_supabase_token(token)
    if supabase_user:
        user_id = supabase_user.get("id")
        email = supabase_user.get("email")
        
        user_row = db.execute(
            text("SELECT role, display_name FROM UserRole WHERE user_id = :id"),
            {"id": user_id}
        ).fetchone()
        
        if not user_row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User authenticated successfully, but no business role is assigned."
            )
            
        return {
            "user_id": user_id,
            "role": user_row[0],
            "display_name": user_row[1],
            "email": email
        }
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials or expired session."
    )
