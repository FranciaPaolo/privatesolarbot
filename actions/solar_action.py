from dataclasses import dataclass
from typing import Mapping
from datetime import datetime

from actions.tigoapi import TigoApi


class SolarAction:

    system_id: int = None  # TODO: adapt to your system ID

    def __init__(self, system_id: int, tigo_api: TigoApi):
        self.system_id = system_id
        self.tigo_api = tigo_api

    def get_status(self) -> dict[str, object]:
        """Return current solar, battery, and grid readings from the Tigo API.

        Returns a dictionary with the following keys:
        - solar_kw: current solar production in kW
        - produced_energy_today_kwh: energy produced today in kWh
        - consumed_energy_today_kwh: energy consumed today in kWh
        - battery_pct: current battery percentage
        - grid_kw: current grid consumption in kW
        - home_consumptions_kw: current home consumption in kW
        """

        data: dict[str, object] = {
            "solar_kw": None,
            "produced_energy_today_kwh": None,
            "consumed_energy_today_kwh": None,
            "battery_pct": None,
            "battery_consumption_kw": None,
            "grid_kw": None,
            "home_consumptions_kw": None,
        }

        try:
            # 1. Get current flow data from Tigo API
            current_flow: dict[str, object] = self.tigo_api.get_current_flow(self.system_id)

            data["solar_kw"] = current_flow.get("solar_production", "0")/1000  # convert W to kW
            data["produced_energy_today_kwh"] = "tbd"
            data["consumed_energy_today_kwh"] = "tbd"
            data["battery_pct"] = current_flow.get("battery_percentage", "0")
            data["battery_consumption_kw"] = -1*(current_flow.get("battery_consumption", "0")/1000)  # convert W to kW
            data["grid_kw"] = -1*(current_flow.get("grid_production", "0")/1000)  # convert W to kW
            data["home_consumptions_kw"] = current_flow.get("home_consumption", "0")/1000  # convert W to kW

            # 2. Get historical data for today to calculate "produced energy today" and "consumed energy today"
            today_data = self.tigo_api.get_historical_data(
                self.system_id,
                start=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                end=datetime.now(),
            )

            produced_energy_today_kwh = sum(
                0 if entry.get("solar", 0) is None else entry.get("solar", 0)
                for entry in today_data
            )
            data["produced_energy_today_kwh"] = produced_energy_today_kwh/1000  # convert Wh to kWh

            # consumed energy today
            print("today_data", today_data)
            consumed_energy_today_kwh = sum(
                0 if entry.get("consumption", 0) is None else entry.get("consumption", 0)
                for entry in today_data
            )
            data["consumed_energy_today_kwh"] = consumed_energy_today_kwh/1000  # convert Wh to kWh

            return data
        except Exception as e:
            return {"error": str(e)}





