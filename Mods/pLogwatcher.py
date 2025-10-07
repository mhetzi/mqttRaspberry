"""
Könnte sein dass es nur als Benutzerservice (systemctl --user) funktioniert!
Could be that this Plugin only works when run as user service (systemctl --user)!
"""

import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
from Tools import PluginManager

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "logwatcher"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return LogWatcher(opts, logger.getChild(PluginLoader.getConfigKey()), device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        LogConfig().configure(conf, logger.getChild(PluginLoader.getConfigKey()))
    
    @staticmethod
    def getNeededPipModules() -> list[str]:
        return []

from Tools.Devices.BinarySensor import BinarySensor, BinarySensorDeviceClasses
from Tools.Devices.Sensor import Sensor, SensorDeviceClasses
import schedule
import json
import os
import threading

import watchdog.observers
import watchdog.events
import subprocess
import shlex

try:
    from time import sleep

    class FileLog(watchdog.events.FileSystemEventHandler):
        _path = ""

        def on_modified(self, event: watchdog.events.FileModifiedEvent):
            
            pass
        
        def on_moved(self, event: watchdog.events.FileMovedEvent):
            pass
        
        def on_closed(self, event: watchdog.events.FileClosedEvent):
            pass

        def __init__(self, config:dict, observer:watchdog.observers.Observer, logger: logging.Logger) -> None:
            self._logger = logger
            self._path = None
            observer.schedule(self, self._path, False)            

        def register(self, plugin_manager: PluginManager.PluginManager):
            pass
        
        def resend(self):
            pass

        def stop(self):
            pass
    
    class ShellLog(threading.Thread):

        def __init__(self, name:str, config:conf.AbstractConfig, logger:logging.Logger) -> None:
            super().__init__()
            cmd:    str = config["cmd"]
            args:   list[str] = shlex.split(cmd)

            self.binary:    bool      = config["binary"]
            self.filter:    str       = config["grep"]
            self.filtered:  list[str] = self.filter.split("|")
            self.name    = name
            self._logger = logger
            
            self.proc = subprocess.Popen(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self._shutdown = False

            self.bsens: BinarySensor | None = None
            self.sens: Sensor | None = None
            self.start()


        def run(self) -> None:
            while not self._shutdown:
                line = self.proc.stdout.readline()
                if not line:
                    return
                if self.bsens:
                    found = False
                    for filter in self.filtered:
                        if filter in line:
                            found = True
                            #self._logger.debug(f"{filter} in {line}")
                    self.bsens.turnOnOffOnce(found)
                if self.sens:
                    self.sens.state(line)

        def register(self, plugin_manager: PluginManager.PluginManager):
            if self.binary:
                self.bsens = BinarySensor(logger=self._logger, pman=plugin_manager, name=self.name, binary_sensor_type=BinarySensorDeviceClasses.PROBLEM)
                self.bsens.register()
                
            else:
                self.sens = Sensor(self._logger, pman=plugin_manager, name=self.name, sensor_type=SensorDeviceClasses.GENERIC_SENSOR)
                self.sens.register()

        def resend(self):
            if self.bsens:
                self.bsens.resend()
            if self.sens:
                self.sens.resend()
        
        def stop(self):
            self.proc.terminate()


    class LogWatcher(PluginManager.PluginInterface):

        def __init__(self, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
            self._logger = logger
            self._watchdog = watchdog.observers.Observer()
            self._watchdog.name = "Logwatcher"
            self._config = conf.PluginConfig(opts, PluginLoader.getConfigKey())
            self.logs: list[ShellLog | FileLog] = []

        def set_pluginManager(self, pm:PluginManager.PluginManager):
            self._pluginManager = pm

        def register(self, wasConnected=False):
            if not wasConnected:
                logs = self._config["logs"]
                for name, d in logs.items():
                    log = ShellLog(name=name,
                                   config=conf.PluginConfig(self._config,
                                   f"logs/{name}"), logger=self._logger
                                   )
                    log.register(self._pluginManager)
            if wasConnected:
                self.sendStates()

        def stop(self):
            pass
        
        def sendStates(self):
            pass
        
        def disconnected(self):
            return super().disconnected()

except ImportError as ie:
    pass

class LogConfig:
    def __init__(self):
        pass

    def configure(self, conff: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        con = conf.PluginConfig(conff, PluginLoader.getConfigKey())
        if con.get("logs", None) is None:
            con["logs"] = {}
        while True:
            action = ConsoleInputTools.get_number_input("Was möchtest du tun? 0. Nichts 1. Log hinzufügen 2. Log löschen", 0)
            if action == 1:
                name = ConsoleInputTools.get_input("Log name?: ")
                args = ConsoleInputTools.get_input("Command to execute?: ")
                binary = ConsoleInputTools.get_bool_input("Binärsensor erstellen?", True)
                filter = ""
                if binary:
                    filter = ConsoleInputTools.get_input("Suchen nach String (mehrere getrennt durch |): ")
                con["logs"][name] = {
                    "cmd": args,
                    "binary": binary,
                    "grep": filter
                }
            elif action == 2:
                print("  0: Nichts löschen\n")
                for i in range(0, len(con["units"])):
                    print(f"  {i+1}: {con['units'][i]}\n")
                rem: int = ConsoleInputTools.get_number_input("Was soll entfernt werden?", 0)
                if rem == 0:
                    continue
                units: list[str] = con["logs"]
                del units[rem-1]
            else:
                break

