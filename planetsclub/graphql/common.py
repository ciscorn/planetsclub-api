"""共通"""

from datetime import datetime
from typing import Optional

from ariadne import InterfaceType, ScalarType
from dateutil.parser import parse as parse_datetime

datetime_scalar = ScalarType("DateTime")


@datetime_scalar.serializer
def serialize_datetime(value):
    return value.isoformat(timespec="milliseconds")


@datetime_scalar.value_parser
def parse_datetime_value(value) -> Optional[datetime]:
    if value:
        d = parse_datetime(value)
        if d.tzinfo is None:
            raise ValueError("Timezone must be specified")
        return d
    else:
        return None


pagable = InterfaceType("Pagable")

resolvers = [datetime_scalar, pagable]
