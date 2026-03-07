"""Order model for delivery route optimizer."""

from pydantic import BaseModel


class Order(BaseModel):
    """A single delivery order."""

    id: int
    city: str
    address: str
    house: str
    lat: float | None = None
    lng: float | None = None
    time_start: str | None = None
    time_end: str | None = None
