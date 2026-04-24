from typing import Any, Dict, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field


class SimpleResponse(BaseModel):
    """To be returned in response of creation, update or delete"""

    id: str


class SimpleResponsePlural(BaseModel):
    """To be returned in response of creation, update or delete"""

    ids: list


class EmptyResponse(BaseModel):
    """Empty response for operations that don't return data"""

    pass


class DeleteResponse(BaseModel):
    message: Optional[str] = None
    message_code: Optional[str] = None
    tasks_ids: Optional[list[str]] = None


class ErrorResponse(BaseModel):
    error: str
    msg: str
    description_code: str
    function: str
    function_call: str
    description: str
    debug: str
    request: str
    data: str
    params: Optional[Dict[str, Any]]


class UnauthorizedError(BaseModel):
    detail: str


# Generic type variable
T = TypeVar("T")


# Generic pagination response that can be reused for any list type
class PaginationResponseList(BaseModel, Generic[T]):
    rows: list[T] = Field(description="List of items for the current page")
    total: int = Field(description="Total number of items across all pages")
