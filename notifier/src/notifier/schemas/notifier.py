from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel

#
# NotifyMail
#


class NotifyMailRequest(BaseModel):
    user_id: str
    subject: str
    text: str


class NotifyMailResponse(BaseModel):
    task_id: UUID


#
# NotifyEmailVerifyMail
#


class NotifyEmailVerifyMailRequest(BaseModel):
    user_id: str
    email: str
    url: str


class NotifyEmailVerifyMailResponse(BaseModel):
    task_id: UUID


#
# NotifyPasswordResetMail
#


class NotifyPasswordResetMailRequest(BaseModel):
    category: str
    email: str
    url: str


class NotifyPasswordResetMailResponse(BaseModel):
    task_id: UUID


#
# NotifyDeleteGPUMail
#


class NotifyDeleteGPUMailRequest(BaseModel):
    user_id: str
    bookings: list[object]
    desktops: list[object]
    deployments: list[object]
    text: str


class NotifyDeleteGPUMailResponse(BaseModel):
    pass


# NOT IMPLEMENTED


class NotImplementedResponse(BaseModel):
    error: str = "This endpoint is not implemented yet. Please check back later."


#
# NotifyFrontend
#


class NotifyFrontendRequestLevel(Enum):
    unspecified = "unspecified"
    success = "success"
    warning = "warning"
    danger = "danger"
    info = "info"


class NotifyFrontendRequest(BaseModel):
    user_id: str
    level: NotifyFrontendRequestLevel
    message: str


class NotifyFrontendResponse(BaseModel):
    pass


#
# NotfyFrontendDesktopTimeLimit
#


class NotifyFrontendDesktopTimeLimitRequest(BaseModel):
    user_id: str
    desktop_name: str
    timestamp: datetime


class NotifyFrontendDesktopTimeLimitResponse(BaseModel):
    pass


#
# NotifyFrontendSearchingResources
#


class NotifyFrontendSearchingResourcesRequest(BaseModel):
    user_id: str


class NotifyFrontendSearchingResourcesResponse(BaseModel):
    pass


#
# NotifyGuest
#


class NotifyGuestRequest(BaseModel):
    desktop_id: str
    message: str


class NotifyGuestResponse(BaseModel):
    pass
