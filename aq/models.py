from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class DateTimePair(BaseModel):
    utc: datetime
    local: Optional[datetime] = None


class Period(BaseModel):
    datetimeFrom: DateTimePair
    datetimeTo: Optional[DateTimePair] = None


class Parameter(BaseModel):
    id: int
    name: str
    units: str

    @field_validator("name")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class FlagInfo(BaseModel):
    hasFlags: bool = False


class RawMeasurement(BaseModel):
    value: float = Field(ge=0)
    parameter: Parameter
    period: Period
    flagInfo: Optional[FlagInfo] = None


class Record(BaseModel):
    city: str
    country: str
    location_id: int
    location_name: str
    sensor_id: int
    coordinates: Coordinates
    measurement: RawMeasurement
