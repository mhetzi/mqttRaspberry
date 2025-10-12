# -*- coding: utf-8 -*-

import logging
import enum
import json

import paho.mqtt.client as mclient
import schedule

from Tools.Config import BasicConfig, PluginConfig 
from Tools.Devices.HVAC import HvacDevice, HVAC_Callbacks, HVAC_MODE
from Tools import RangeTools, PluginManager

DEPENDENCIES_LOADED=True

try:
    import gpiozero
    from Tools.Pin import *
except ImportError as ie:
    DEPENDENCIES_LOADED = False

try:
    from simple_pid import PID
except ImportError as ie:
    DEPENDENCIES_LOADED = False


class PluginLoader(PluginManager.PluginLoader):
    @staticmethod
    def getNeededPipModules() -> list[str]:
        l = []
        try:
            import gpiozero
        except ImportError as ie:
            l.append("gpiozero")
        try:
            from simple_pid import PID
        except ImportError as ie:
            l.append("simple-pid")
        return l

    @staticmethod
    def getConfigKey():
        return "PID"

    @staticmethod
    def getPlugin(opts: BasicConfig, logger: logging.Logger):
        try:
            import gpiozero
            from Tools import Pin
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('gpiozero', throw=ie, ask=False)

        try:
            from simple_pid import PID
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('simple-pid', throw=ie, ask=False)
        return PID_Plugin(opts, logger)

    @staticmethod
    def runConfig(conf: BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        print("Pins standartmäßig nach BCM schema (gpiozero angaben gestattet)")

if DEPENDENCIES_LOADED:

    class Valve:
        def __init__(self, log: logging.Logger, config: PluginConfig, _MAX_VALUE = 255):
            self._config = PluginConfig(config, "valve")
            self.hotter = Pin(self._config["hotter"], PinDirection.OUT, init=0)
            self.colder = Pin(self._config["colder"], PinDirection.OUT, init=0)
            self._old_val = 0
            self._MAX_VALUE = _MAX_VALUE
        
        def home(self):
            self.colder.pulse(self._config["time_end_to_end"])
            self._old_val = 0
        
        def apply_value(self, v: int):
            max_time = self._config["time_end_to_end"]
            mapped_time = RangeTools.map(v, 0, 255, 0, max_time)
            old_time = RangeTools.map(self._old_val, 0, 255, 0, max_time)
            work_time = old_time - mapped_time
            if work_time > 0:
                self.hotter.pulse(work_time)
            else:
                self.colder.pulse(work_time *-1)
                

    class PID_Controller(HVAC_Callbacks):
        #OVerrides of superclass
        def call_get_CurrentTemperature(self) -> float:
            return None
        
        def call_set_targetTemperature(self, deg:float):
            self._config["target"] = deg
            self._pid.setpoint = deg
        
        def call_get_modes(self) -> list:
            return [HVAC_MODE.OFF, HVAC_MODE.HEAT, HVAC_MODE.AUTO]
        
        def call_set_mode(self, mode: HVAC_MODE):
            self._config["mode"] = mode.value
            if mode is HVAC_MODE.OFF:
                self.set_output(0)
                self._pid.set_auto_mode(False, self._last_output)
            elif mode is HVAC_MODE.HEAT:
                self.set_output(255)
                self._pid.set_auto_mode(False, self._last_output)
            elif mode is HVAC_MODE.AUTO:
                self._pid.set_auto_mode(True, self._last_output)

        def call_get_action(self) -> bool:
            return True

        def call_get_precision(self) -> float:
            return 0.1

        # sensor allows 1w://uuid for onewire or mqtt://topic for mqtt sensor
        def __init__(self, config: PluginConfig, log: logging.Logger):
            self._hvac = None
            self._config = config
            self._shedule_task = None
            self._last_output = 0
            self._pid = PID(
                Kp=self._config.get("Kp", 1.0),
                Ki=self._config.get("Ki", 0.0),
                Kd=self._config.get("Kd", 0.0),
                setpoint=self._config.get("target", 20),
                sample_time=self._config.get("pid_frequenzy", 0.1),
                output_limits=(0, 255)
            )
            self._valve = Valve(log, config)
            self._logger = log
        
        def initialize(self, device: HvacDevice):
            self._hvac = device
            self._shedule_task = schedule.every(self._config.get("check_secs", 5.0)).seconds
            self._shedule_task.do(self.task)
            self.call_set_mode(HVAC_MODE(self._config.get("mode", HVAC_MODE.AUTO.value)))

        def task(self):
            sensUri = self._config.get("sensor_uri", "")
            if sensUri.startswith("1w://"):
                from Mods import pOneWireTemp
                t = pOneWireTemp.OneWireTemp.get_temperature_from_id(sensUri.replace("1w://"))
                self.set_output(self._pid(t))
                self._hvac.curTemp(t)
            Kp, Ki, Kd = self._pid.tunings
            d = {
                "valve": self._last_output,
                "Kp": Kp,
                "Ki": Ki,
                "Kd": Kd
            }
            self._hvac.update_extra_attributes(d)

        def register(self):
            self._hvac.register()

        def stop(self):
            if self._shedule_task is not None:
                schedule.cancel_job(self._shedule_task)
        
        def set_output(self, valve: int):
            self._last_output = valve
            self._valve.apply_value(valve)

        def sendUpdate(self):
            pass


    class PID_Plugin(PluginManager.PluginInterface):

        def __init__(self, opts: BasicConfig, logger: logging.Logger):
            self.__logger = logger.getChild("PID")
            self._config = PluginConfig(opts, "PID")
            self._hvac_call = PID_Controller(self._config, logger)
            self._device = None

        def set_pluginManager(self, pm):
            self._pluginManager = pm
            self._device = HvacDevice(self.__logger.getChild("dev"), pm, self._hvac_call, self._config.get("name"))

        def register(self, wasConnected: bool):
            if not wasConnected:
                self._hvac_call.initialize(self._device)
            self._hvac_call.register()

        def sendStates(self):
            self.sendUpdate()

        def sendUpdate(self, fromHandler=False):
            pass

        def on_message(self, client, userdata, message: mclient.MQTTMessage):
            pass

        def stop(self):
            if self._hvac_call is not None:
                self._hvac_call.stop()