import logging
from datetime import datetime

import requests

# reference:
# https://support.tigoenergy.com/hc/en-us/articles/200863027-How-To-use-the-Tigo-Energy-API
# https://support.tigoenergy.com/hc/en-us/article_attachments/360041622173
#

logger = logging.getLogger(__name__)

API_V3_BASE = "https://api2.tigoenergy.com/api/v3"
API_V4_BASE = "https://ei.tigoenergy.com/api/v4"

# objectTypeIds used by get_current_flow:
# 36 - Home consumption   [W] > greater than 0 means consuming
# 14 - Grid consumption   [W] > greater than 0 means producing, less than 0 means consuming
# 56 - Battery consumption [W] > greater than 0 means accumulating, less than 0 means discharging
# 46 - Battery percentage [W] > greater than 0 means accumulating, less than 0 means discharging
# 62 - Solar production   [W] > greater than 0 means producing
OBJECT_TYPE_GRID = "14"
OBJECT_TYPE_HOME = "36"
OBJECT_TYPE_BATTERY = "56"
OBJECT_TYPE_BATTERY_PERC = "46"
OBJECT_TYPE_SOLAR = "62"

SERIES_PROPERTY_MAP = {
    "Battery Energy": "battery_energy",  # energy used to charge battery
    "Consumption": "consumption",  # home consumption
    "Solar": "solar",  # solar production
    "Net Energy": "net_energy",  # calculated: = solar - home consumption - battery power
}


class TigoApi:
    """Tigo Energy API client for interacting with Tigo systems and data."""

    def __init__(
        self,
        username: str = "",
        password: str = "",
        token: str | None = None,
        timeout: float = 30,
    ):
        """Initialize the API client with credentials."""
        self.username = username
        self.password = password
        self.auth_token = token
        self.user_id = None
        self.timeout = timeout
        self._session = requests.Session()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.auth_token}"}

    def _get(self, url: str, **kwargs):
        response = self._session.get(url, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response.json()

    def login(self):
        """Log in and get authentication token."""
        result = self._get(
            f"{API_V3_BASE}/users/login",
            auth=(self.username, self.password),
        )
        self.auth_token = result["user"]["auth"]
        self.user_id = result["user"]["user_id"]
        return result

    def get_systems(self):
        """Get systems using the authentication token."""
        return self._get(f"{API_V3_BASE}/systems", headers=self._auth_headers())

    def get_sources(self, system_id: int):
        """Get sources for a given system."""
        return self._get(
            f"{API_V3_BASE}/sources/system",
            headers=self._auth_headers(),
            params={"system_id": system_id},
        )

    def get_historical_data(self, system_id: int, start: datetime, end: datetime):
        """Get hourly historical data for a system."""
        params = {
            "systemId": system_id,
            "view": "dist",
            "output": "echart",
            "type": "bar",
            "agg": "hour",
            "start": start.isoformat(timespec="seconds"),
            "end": end.date().isoformat(),
            "reclaimed": "false",
            "outOfSync": "false",
        }
        json_resp = self._get(
            f"{API_V4_BASE}/data/aggregate",
            headers=self._auth_headers(),
            params=params,
        )
        logger.debug("Fetched historical aggregate for system %s", system_id)

        combined_data = {}
        for series in json_resp.get("series", []):
            output_property = SERIES_PROPERTY_MAP.get(series.get("name"))
            if not output_property:
                continue
            for time_stamp, value in series.get("data", []):
                entry = combined_data.setdefault(time_stamp, {"time": time_stamp})
                entry[output_property] = value

        return list(combined_data.values())

    def get_current_flow(self, system_id: int):
        """Get current energy flow for a system."""
        params = [
            ("systemId", system_id),
            ("aggregate", "now"),
            ("objectTypeIds[]", OBJECT_TYPE_GRID),
            ("objectTypeIds[]", "32"),
            ("objectTypeIds[]", OBJECT_TYPE_HOME),
            ("objectTypeIds[]", OBJECT_TYPE_BATTERY_PERC),
            ("objectTypeIds[]", OBJECT_TYPE_BATTERY),
            ("objectTypeIds[]", "58"),
            ("objectTypeIds[]", OBJECT_TYPE_SOLAR),
            ("objectTypeIds[]", "57"),
        ]
        json_resp = self._get(
            f"{API_V4_BASE}/data/aggregate",
            headers=self._auth_headers(),
            params=params,
        )
        object_types = json_resp.get("objectTypeIds", {})

        def first_value(object_type_id: str):
            values = object_types.get(object_type_id, [None])
            return values[0] if values else None

        time_values = json_resp.get("time", [None])
        return {
            "home_consumption": first_value(OBJECT_TYPE_HOME),
            "solar_production": first_value(OBJECT_TYPE_SOLAR),
            "grid_production": first_value(OBJECT_TYPE_GRID),
            "battery_consumption": first_value(OBJECT_TYPE_BATTERY),
            "battery_percentage": first_value(OBJECT_TYPE_BATTERY_PERC),
            "time": time_values[0] if time_values else None,
            "timezone": json_resp.get("timezone"),
        }
