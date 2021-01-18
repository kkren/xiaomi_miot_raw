""" 这个版本的 update 方法未继承父类，而是重写了整个方法，
    以此排查是否是继承上出了问题 """
import asyncio
import logging
from collections import defaultdict
from functools import partial
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_NAME, CONF_TOKEN
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import Entity

from miio.device import Device
from miio.exceptions import DeviceException
from miio.miot_device import MiotDevice 
from . import GenericMiotDevice

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Generic MIoT sensor"
DATA_KEY = "sensor.xiaomi_miot_raw"
DOMAIN = "xiaomi_miot_raw"

CONF_SENSOR_PROPERTY = "sensor_property"
CONF_SENSOR_UNIT = "sensor_unit"
CONF_DEFAULT_PROPERTIES = "default_properties"
CONF_MAPPING = 'mapping'
CONF_CONTROL_PARAMS = 'params'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_SENSOR_PROPERTY): cv.string,
        vol.Optional(CONF_SENSOR_UNIT): cv.string,
        vol.Required(CONF_MAPPING):vol.All(),
        vol.Optional(CONF_CONTROL_PARAMS):vol.All(),
    }
)

ATTR_MODEL = "model"
ATTR_FIRMWARE_VERSION = "firmware_version"
ATTR_HARDWARE_VERSION = "hardware_version"
ATTR_PROPERTIES = "properties"
ATTR_SENSOR_PROPERTY = "sensor_property"
ATTR_METHOD = "method"
ATTR_PARAMS = "params"

# pylint: disable=unused-argument
@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the sensor from config."""
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    host = config.get(CONF_HOST)
    token = config.get(CONF_TOKEN)
    mapping = config.get(CONF_MAPPING)

    _LOGGER.info("Initializing with host %s (token %s...)", host, token[:5])


    try:
        miio_device = MiotDevice(ip=host, token=token, mapping=mapping)
        device_info = miio_device.info()
        model = device_info.model
        _LOGGER.info(
            "%s %s %s detected",
            model,
            device_info.firmware_version,
            device_info.hardware_version,
        )

        device = MiotSensor(miio_device, config, device_info)
    except DeviceException as de:
        _LOGGER.warn(de)

        raise PlatformNotReady


    hass.data[DATA_KEY][host] = device
    async_add_devices([device], update_before_add=True)

class MiotSensor(GenericMiotDevice):
    def __init__(self, device, config, device_info):
        GenericMiotDevice.__init__(self, device, config, device_info)
        self._state = None
        self._skip_update = False
        self._sensor_property = config.get(CONF_SENSOR_PROPERTY)
        
    @property
    def state(self):
        """Return the state of the device."""
        return self._state
    
    async def async_update(self):
        # await super().async_update()
        if self._update_instant is False and self._skip_update:
            self._skip_update = False
            return

        try:
            _props = [k for k in self._mapping]
            response = await self.hass.async_add_job(
                    self._device.get_properties_for_mapping
                )
            self._available = True

            statedict={}
            count4004 = 0
            for r in response:
                if r['code'] == 0:
                    try:
                        f = self._ctrl_params[r['did']]['value_ratio']
                        statedict[r['did']] = round(r['value'] * f , 3)
                    except KeyError:
                        statedict[r['did']] = r['value']
                else:
                    _LOGGER.error("Failed getting property '%s', code: %s", r['did'], r['code'])
                    statedict[r['did']] = None
                    if r['code'] == -4004:
                        count4004 += 1
            if count4004 == len(response):
                self._assumed_state = True
                # _LOGGER.warn("设备不支持状态反馈")
                        

            self._state_attrs.update(statedict)


        except DeviceException as ex:
            self._available = False
            _LOGGER.error("Got exception while fetching the state: %s", ex)

        state = self._state_attrs
        if self._sensor_property is not None:
            self._state = state.get(self._sensor_property)
        else:
            try:
                self._state = state.get(self._mapping.keys()[0])
            except:
                self._state = None
