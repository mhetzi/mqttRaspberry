import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import logging
import json
from  Tools.PluginManager import PluginManager
import enum

class HVAC_MODE(enum.Enum): 
    AUTO      = "auto"
    OFF       = "off"
    COOL      = "cool"
    HEAT      = "heat"
    DRY       = "dry"
    FAN_ONLY  = "fan_only"
    HVAC_MODE_MAX = "EOE"

class HVAC_Callbacks:
    # Ein und Ausschalten des HVACs
    def call_set_power(self, on:bool):
        raise NotImplementedError()
    
    # current temperature (required) | None means device will receive updates as soon as new values are ready
    def call_get_CurrentTemperature(self) -> float:
        raise NotImplementedError()

    # target temperature / Die angepeilte Temperatur (required)
    def call_set_targetTemperature(self, deg:float):
        raise NotImplementedError()

    # get mode for initialize needs to be subset of [“auto”, “off”, “cool”, “heat”, “dry”, “fan_only”]
    def call_get_modes(self) -> list:
        raise NotImplementedError()

    # set mode
    def call_set_mode(self, mode:HVAC_MODE):
        raise NotImplementedError()

    # get action, when true using code can send one of [idle, cooling, heating, drying, off]
    def call_get_action(self) -> bool:
        return False
    
    # set high temperature
    def call_set_temperature_high(self, deg:float):
        raise NotImplementedError()

    # set low temperature
    def call_set_temperature_low(self, deg:float):
        raise NotImplementedError()

    # which precision? 0.1, 0.5, 1
    def call_get_precision(self) -> float:
        return 0.5

    # set which fanmode is active
    def call_set_fan_mode(self, mode:str):
        raise NotImplementedError()
    
    # get which fanmodes are supported
    def call_get_supported_fan_modes(self) -> list:
        return None # return has to be subset of [“auto”, “low”, “medium”, “high”]

class HvacDevice:
    
    def __init__(self, logger:logging.Logger, pman: PluginManager, callback: HVAC_Callbacks, name: str, ava_topic=None, device=None, unique_id=None, icon=None):
        if not callable(callback):
            raise AttributeError("callback not callable")
        self._log = logger.getChild("Switch")
        self._log.debug("Switch Object für {} mit custom uid {} erstellt.".format(name, unique_id))
        self._pm = pman
        self._callbacks = callback
        self._name = name
        self._ava_topic = ava_topic
        self._dev = device
        self._unique_id = unique_id
        self._icon = icon
        self._topics = pman.config.get_autodiscovery_topic(
            autodisc.Component.SWITCH,
            name,
            autodisc.DeviceClass()
            )
        self._mqtt_callbacks = []

    def register(self):
        bcp = self._topics.get_config_payload(self._name, "", asDict=True)
        
        # power Switch
        try:
            self._callbacks.call_set_power()
            self.__registerPower(bcp)
        except NotImplementedError:
            pass
        except:
            self._log.exception("HVAC power not setup")
        # current temperature
        try:
            self._callbacks.call_get_CurrentTemperature()
            self.__registerCurrentTemperature(bcp)
        except NotImplementedError as e:
            self._log.error("call_get_CurrentTemperature not implemented. Required!")
            raise e
        except Exception as e:
            self._log.exception("HVAC current temperature not setup, required, aborting...")
            raise e
        # setpoint or target temperature
        try:
            self._callbacks.call_set_targetTemperature(None)
            self.__registerTargetTemperature(bcp)
        except NotImplementedError as e:
            self._log.error("call_set_targetTemperature not implemented. Required!")
            raise e
        except Exception as e:
            self._log.exception("HVAC target temperature not setup, required, aborting...")
            raise e
        # mode support (off, auto, heat...)
        try:
            self._callbacks.call_get_modes( )
            self._callbacks.call_set_mode(HVAC_MODE.HVAC_MODE_MAX)
            self.__registerModes(bcp)
        except NotImplementedError:
            pass
        except:
            self._log.exception("HVAC Modes not setup")
        # Current action support
        try:
            if self._callbacks.call_get_action():
                self.__registerAction(bcp)
        except:
            self._log.exception("HVAC Action not setup")

    
    def __registerPower(self, bcp: dict):
        cmd = self._topics.command + "/pwr"
        bcp["power_command_topic"] = cmd
        self._pm._client.subscribe(cmd)
        self._pm._client.message_callback_add(cmd, 
            lambda client,userdata,message: self._callbacks.call_set_power(on=message.decode('utf-8') == "ON") )
        self._mqtt_callbacks.append(cmd)

    def __registerCurrentTemperature(self, bcp: dict):
        state = self._topics.state + "/temp_now"
        bcp["current_temperature_topic"] = state
        self.curTemp = lambda t: self._pm._client.publish(state, t)
    
    def __registerTargetTemperature(self, bcp: dict):
        state = self._topics.state + "/target"
        cmd = self._topics.command + "/target"
        bcp["temperature_state_topic"] = state
        bcp["temperature_command_topic"] = cmd

    
    def __registerModes(self, bcp: dict):
        pass

    def __registerAction(self, bcp: dict):
        pass
        
    def update_extra_attributes(self, d: dict):
        pass
    
    def curTemp(self, t: float):
        raise NotImplementedError("Maybe you forgot call_get_CurrentTemperature?")
    