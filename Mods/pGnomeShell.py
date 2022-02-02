"""
Könnte sein dass es nur als Benutzerservice (systemctl --user) funktioniert!
Could be that this Plugin only works when run as user service (systemctl --user)!
"""
try:
    import dbus
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('dbus-python', throw=ie, ask=True)
    except err.RestartError:
        import dbus

from typing import IO, Union
import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import Tools.PluginManager as PluginMan
from Tools.Devices.Lock import Switch, Lock, LockState
from Tools.Devices.BinarySensor import BinarySensor
import logging
import schedule
import json
import os
import threading
import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib

from time import sleep

import Mods.pLogind as logind

class GnomeShell:

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._bus    = None
        self._proxy  = None
        self._login1 = None
        self._logger = logger
        self._mainloop = None

    def configure(self, conff: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        conf = conff.PluginConfig(conff, PluginLoader.getConfigKey())

        conf["allow_power_off"] = ConsoleInputTools.get_bool_input("\nErlaube Ausschalten: ", True)
        conf["allow_suspend"] = ConsoleInputTools.get_bool_input("\nErlaube Bereitschaftsmodus: ", True)
        conf["allow_reboot"] = ConsoleInputTools.get_bool_input("\nErlaube Neustarten: ", True)
        conf["allow_inhibit"] = ConsoleInputTools.get_bool_input("\nErlaube Blockieren von Schlafmodus: ", True)
        if ConsoleInputTools.get_bool_input("\nBenutze anderen Namen: ", True):
            conf["custom_name"] = ConsoleInputTools.get_input("\nDen Namen Bitte: ", True)
        conf["inactivity_ms"] = ConsoleInputTools.get_number_input("\nInaktivität nach x Millisekunden: ")

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "gnome-shell"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return GnomeShell(client, opts, logger.getChild("logind"), device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        GnomeShellConfig().configure(conf, logger.getChild("logind"))