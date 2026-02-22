"""World bounded context — regions, locations, player movement."""

from app.domain.world.service import (
    create_location,
    create_region,
    get_location,
    get_location_by_name,
    get_locations,
    get_region,
    get_region_by_name,
    get_regions,
    move_character,
)

__all__ = [
    "create_location",
    "create_region",
    "get_location",
    "get_location_by_name",
    "get_locations",
    "get_region",
    "get_region_by_name",
    "get_regions",
    "move_character",
]
