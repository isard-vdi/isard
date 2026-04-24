from typing import Literal, Optional

from pydantic import BaseModel, Field

USER_ROLE = Literal["user", "advanced", "manager", "admin"]


class UserFromCSV(BaseModel):
    """_From api/schemas/user_from_csv.yml_"""

    username: str = Field(pattern="^[A-Za-z0-9._@%+-]+$", max_length=40)
    name: str = Field(max_length=50)
    email: str = ""
    group: str
    category: str
    role: USER_ROLE


class ProviderQuotaModel(BaseModel):
    """Provider quota information model"""

    used: Optional[int] = None
    relative: Optional[float] = None
    quota: Optional[int] = None
    total: Optional[int] = None
    free: Optional[int] = None


class UserStorageModel(BaseModel):
    """User storage configuration model"""

    user_id: Optional[str] = None
    provider_id: Optional[str] = None
    password: Optional[str] = None
    email: Optional[str] = None
    displayname: Optional[str] = None
    quota: Optional[int] = None
    web: Optional[str] = None
    dav: Optional[str] = None
    tls: Optional[bool] = None
    verify_cert: Optional[bool] = None
    token: Optional[str] = None
    token_web: Optional[str] = None
    token_davs: Optional[str] = None
    provider_quota: Optional[ProviderQuotaModel] = None
