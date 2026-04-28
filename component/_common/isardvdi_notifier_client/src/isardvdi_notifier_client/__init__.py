"""A client library for accessing Notifier API. Used only through internal microservices."""

from .client import AuthenticatedClient, Client

__all__ = (
    "AuthenticatedClient",
    "Client",
)
