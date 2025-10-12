# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
from Tools import Config, Autodiscovery, ConsoleInputTools, PluginManager
import logging
import time
import schedule
import threading
from Mods.pRaspberryCpuTemp import RaspberryPiCpuTemp
import json

class PluginLoader(PluginManager.PluginLoader):
    @staticmethod
    def getConfigKey():
        return "SerialFan"

    @staticmethod
    def getPlugin(opts: Config.BasicConfig, logger: logging.Logger):
        try:
            import serial
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('pyserial', throw=ie, ask=False)
        return SerialFan(opts, logger)

    @staticmethod
    def runConfig(conf: Config.BasicConfig, logger:logging.Logger):
        c = Config.PluginConfig(conf, PluginLoader.getConfigKey())
        c["dev"]= ConsoleInputTools.get_input("Serial Device Pfad: ", require_val=True, std_val="/dev/ttyACM0")
        c["tp"] = [ [0,0], [50, 30], [60, 50], [75, 75], [80, 100] ]
        c["provider"] = "rpiCPUtemp"
        
    @staticmethod
    def getNeededPipModules() -> list[str]:
        l = []
        try:
            from Tools import Pin
        except ImportError as ie:
            l.append("gpiozero")
        try:
            import serial
        except ImportError as ie:
            l.append("pyserial")
        return []

from Tools.error import InSystemModeError

try:
    import serial
    from Tools import Pin

    class SerialFan(PluginManager.PluginInterface):
        def __init__(self, opts: Config.BasicConfig, logger: logging.Logger):
            self.__logger = logger.getChild("SerialFan")
            self._config = Config.PluginConfig(opts, "SerialFan")
            self._registered_callback_topics = []
            self._pm = None
            self.temperature = 0
            self._serial = serial.Serial(port=self._config["dev"], dsrdtr=True, rtscts=True)
            self._serial_thr = None
            self._shutdown = False
            self._rpm = 0
            self._pct = 0
            self._err = None
            self._last_rpm = 0
            self._last_pct = 0
            self._last_err = "BOOTED"
            self._speed_topics = None
            self._rpm_topics = None
            self._err_topics = None
        
        def disconnected(self):
            pass

        def set_pluginManager(self, pm: PluginManager.PluginManager):
            self._pm = pm

        def register(self, wasConnected: bool):
            
            if self._speed_topics is not None:
                fan_speed = self._config.get_autodiscovery_topic(
                    Autodiscovery.Component.LIGHT,
                    "SerialFan",
                    Autodiscovery.DeviceClass
                )
                fan_speed.register_light(
                    self._pluginManager._client,
                    "SerialFan Speed",
                    brightness_scale=100,
                    unique_id="fan.speed.pct.{}".format(self._config._main.get_client_config().id)
                )
                self._speed_topics = fan_speed

            if self._rpm_topics is not None:
                rpm = self._config.get_autodiscovery_topic(
                    Autodiscovery.Component.SENSOR,
                    "SerialFan RPM",
                    Autodiscovery.SensorDeviceClasses.GENERIC_SENSOR
                )
                rpm.register(
                    self._pluginManager._client,
                    "SerialFan RPM",
                    "RPM",
                    None,
                    unique_id="fan.speed.rpm.{}".format(self._config._main.get_client_config().id),
                    icon="mdi:fan"
                )
                self._rpm_topics = rpm

            if self._err_topics is not None:
                self._err_topics = self._config.get_autodiscovery_topic(
                    Autodiscovery.Component.BINARY_SENROR,
                    "SerialFan Error",
                    Autodiscovery.BinarySensorDeviceClasses.PROBLEM
                )
                self._err_topics.register(
                    self._pluginManager._client,
                    "SerialFan Error",
                    "",
                    value_template="{{value_json.err}}",
                    json_attributes=True,
                    unique_id="fan.speed.error.{}".format(self._config._main.get_client_config().id)
                )

            if not wasConnected:
                cpu = self._pm.get_plguins_by_config_id(self._config["provider"])
                cpu.add_temperature_call( self.new_temp )
                schedule.every(15).minutes.do(SerialFan.send_updates, self)
                try:
                    self._serial.open()
                except serial.SerialException:
                    self.__logger.warning("Serieller Port konnte nicht geöffnet werden!")
                self._serial_thr = threading.Thread(target=self.serial_read, name="SerialFanRead")
                self._serial_thr.start()

            self._pluginManager._client.subscribe(self._speed_topics.command)
            self._pluginManager._client.message_callback_add(self._speed_topics.command, self.on_message)
            self._registered_callback_topics.append(self._speed_topics.command)

            self._pluginManager._client.subscribe(self._speed_topics.brightness_cmd)
            self._pluginManager._client.message_callback_add(self._speed_topics.brightness_cmd, self.on_message)
            self._registered_callback_topics.append(self._speed_topics.brightness_cmd)
            js = json.dumps({
                        "err":  0,
                        "Grund": "OK"
            })
            self._pluginManager._client.publish(self._err_topics.state, js)
            self._last_err = self._err

            self.sendStates()
            
        def new_temp(self, temp):
            pct = 0
            for tp in self._config["tp"]:
                if temp > tp[0]:
                    pct = tp[1]
            self.send_pct(pct)
        
        def send_pct(self, pcr):
            self._serial.write("set_pct{};".format(pcr).encode("utf-8"))

        def on_message(self, client, userdata, message: mclient.MQTTMessage):
            msg = message.payload.decode("utf-8")
            if msg == "ON":
                self._serial.write("on;".encode("utf-8"))
            elif msg == "OFF":
                self._serial.write("off;".encode("utf-8"))
            else:
                pct = float(msg)
                self.send_pct(pct)

        def serial_read(self):
            while not self._shutdown:
                try:
                    s = self._serial.read_until(expected=b';')
                except TypeError:
                    s = self._serial.read_until(terminator=b';')
                s = s.decode("utf-8")
                if s == "":
                    continue
                s = s.replace(";","").replace("\r","").replace("\n","").split(":")
                if s[0] == "RPM":
                    #self.__logger.debug("Found RPM")
                    try:
                        self._rpm = float(s[1])
                        if self._rpm > 0:
                            self._err = None
                        self.send_updates()
                    except ValueError:
                        pass
                elif s[0] == "ERR":
                    #self.__logger.debug("Found ERR")
                    self._err = s[1]
                    self.send_updates()
                elif s[0] == "DCP":
                    try:
                        #self.__logger.debug("Found DutyCycle Percent")
                        self._pct = float(s[1])
                        self.err = None
                        self.send_updates()
                    except ValueError:
                        pass
                else:
                    self.__logger.info('Nachricht von Controller: "{}"'.format(s))

        def sendStates(self):
            self.send_updates()

        def stop(self):
            self._shutdown = True
            self._serial.close()
            self._serial_thr.join()
            for reg in self._registered_callback_topics:
                self._pluginManager._client.message_callback_remove(reg)

        @staticmethod
        def convert_input_to_string(to_convert: int) -> str:
            if to_convert == 0:
                return "OFF"
            elif to_convert == 1:
                return "ON"

        def send_updates(self):
            if self._last_pct != self._pct:
                self._last_pct = self._pct
                #self.__logger.debug("Sende Pct")
                self._pluginManager._client.publish(
                    self._speed_topics.state,
                    "ON" if self._pct > 10 else "OFF"
                )
                self._pluginManager._client.publish(
                    self._speed_topics.brightness_state,
                    self._pct
                )
            if self._last_rpm != self._rpm:
                self._last_rpm = self._rpm
                #self.__logger.debug("Sende RPM")
                self._pluginManager._client.publish(
                    self._rpm_topics.state,
                    self._rpm
                )
            if self._last_err != self._err:
                js = json.dumps({
                        "err":  0 if self._err is None else 1,
                        "Grund": "OK" if self._err is None else self._err
                })
                self.__logger.debug("Sende Error: {}".format(js))
                self._pluginManager._client.publish(self._err_topics.state, js)
                self._last_err = self._err

except ImportError as ie:
    pass
except InSystemModeError as ie:
    pass