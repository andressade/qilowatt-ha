from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from qilowatt import EnergyData, MetricsData

from .base_inverter import BaseInverter

class HuaweiInverter(BaseInverter):
    """Implementation for Huawei integrated inverters."""

    def __init__(self, hass: HomeAssistant, config_entry):
        super().__init__(hass, config_entry)
        self.hass = hass
        self.device_id = config_entry.data["device_id"]
        self.all_entities = self.collect_device_entities()

    def collect_device_entities(self):
        """Collect entities from main device and all child devices"""
        device_registry = dr.async_get(self.hass)
        entity_registry = er.async_get(self.hass)
        
        all_entities = {}
        
        # Add main device entities
        for entity in entity_registry.entities.values():
            if entity.device_id == self.device_id and not entity.disabled_by:
                all_entities[entity.entity_id] = entity
        
        # Add child device entities (only those with enabled entities)
        for device in device_registry.devices.values():
            if device.via_device_id == self.device_id:
                enabled_count = sum(1 for e in entity_registry.entities.values() 
                                  if e.device_id == device.id and not e.disabled_by)
                if enabled_count > 0:  # Only include devices with enabled entities
                    for entity in entity_registry.entities.values():
                        if entity.device_id == device.id and not entity.disabled_by:
                            all_entities[entity.entity_id] = entity
        
        return all_entities

    def find_entity_state(self, entity_id):
        """Find entity using dynamic discovery across device hierarchy"""
        # Special case for number entities
        if entity_id == "inverter_power_derating":
            return self.hass.states.get("number.inverter_power_derating")
        
        # Search through all collected entities
        for full_entity_id in self.all_entities:
            if full_entity_id.endswith(entity_id):
                return self.hass.states.get(full_entity_id)
        
        return None

    def get_state_float(self, entity_id, default=0.0):
        """Helper method to get a sensor state as float."""
        state = self.find_entity_state(entity_id)
        if state and state.state not in ("unknown", "unavailable", ""):
            try:
                return float(state.state)
            except ValueError:
                pass
        return default

    def get_state_int(self, entity_id, default=0):
        """Helper method to get a sensor state as int."""
        state = self.find_entity_state(entity_id)
        if state and state.state not in ("unknown", "unavailable", ""):
            try:
                return int(float(state.state))
            except ValueError:
                pass
        return default

    def get_state_text(self, entity_id, default=""):
        """Helper method to get a sensor state as text."""
        state = self.find_entity_state(entity_id)
        if state and state.state not in ("unknown", "unavailable", "", None):
            return str(state.state)
        return default
        
    def get_energy_data(self):
        """Retrieve ENERGY data."""
        power = [
            self.get_state_float("power_meter_phase_a_active_power") * -1,
            self.get_state_float("power_meter_phase_b_active_power") * -1,
            self.get_state_float("power_meter_phase_c_active_power") * -1,
        ]
        today = 0
        total = self.get_state_float("power_meter_consumption") * -1
        
        self.voltage = [
            self.get_state_float("power_meter_phase_a_voltage"),
            self.get_state_float("power_meter_phase_b_voltage"),
            self.get_state_float("power_meter_phase_c_voltage"),
        ]
        
        current = [
            self.get_state_float("power_meter_phase_a_current"),
            self.get_state_float("power_meter_phase_b_current"),
            self.get_state_float("power_meter_phase_c_current"),
        ]
        
        frequency = self.get_state_float("power_meter_frequency")
        
        return EnergyData(
            Power=power,
            Today=today,
            Total=total,
            Current=current,
            Voltage=self.voltage,
            Frequency=frequency,
        )

    def get_metrics_data(self):
        """Retrieve METRICS data."""
        # Calculate PV Power for each string
        pv_voltage_1 = self.get_state_float("pv_1_voltage")
        pv_current_1 = self.get_state_float("pv_1_current")
        pv_voltage_2 = self.get_state_float("pv_2_voltage")
        pv_current_2 = self.get_state_float("pv_2_current")
        
        pv_power = [
            pv_voltage_1 * pv_current_1,
            pv_voltage_2 * pv_current_2,
        ]
        
        # Retrieve PV Voltage and Current
        pv_voltage = [pv_voltage_1, pv_voltage_2]
        pv_current = [pv_current_1, pv_current_2]

        # Load Power and Current
        inverter_active_power = self.get_state_float("active_power")
        # Get grid power directly from the sensor
        power_meter_active_power = self.get_state_float("power_meter_active_power")
        # Load power is inverter output minus grid power
        load_power_total = inverter_active_power - power_meter_active_power
        load_power = [load_power_total]
        
        # Use fixed load current values
        load_current = [0.0, 0.0, 0.0]  # As per payload

        # Battery metrics
        battery_power = [self.get_state_float("charge_discharge_power")]
        battery_current = [self.get_state_float("bus_current")]
        battery_voltage = [self.get_state_float("bus_voltage")]
        battery_soc = self.get_state_int("state_of_capacity")
        battery_temperature = [self.get_state_float("battery_1_bms_temperature")]

        # Inverter metrics
        inverter_status = 2  # As per payload
        inverter_temperature = self.get_state_float("internal_temperature")
        alarm_codes = [0, 0, 0, 0, 0, 0]  # As per payload
        grid_export_limit = self.get_state_float("inverter_power_derating")
        
        # Return metrics data with actual values
        return MetricsData(
            PvPower=pv_power,
            PvVoltage=pv_voltage,
            PvCurrent=pv_current,
            LoadPower=load_power,
            AlarmCodes=alarm_codes,
            BatterySOC=battery_soc,
            LoadCurrent=load_current,
            BatteryPower=battery_power,
            BatteryCurrent=battery_current,
            BatteryVoltage=battery_voltage,
            InverterStatus=inverter_status,
            GridExportLimit=grid_export_limit,
            BatteryTemperature=battery_temperature,
            InverterTemperature=inverter_temperature,
        )
