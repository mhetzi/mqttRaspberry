"""
from pydbus import SystemBus
bus = SystemBus()
proxy = bus.get(".login1", "/org/freedesktop/login1")

proxy.ListSessions()
=> [('c1', 42, 'gdm', 'seat0', '/org/freedesktop/login1/session/c1'),
    ('4', 1000, 'marcel', '', '/org/freedesktop/login1/session/_34'),
    ('2', 1000, 'marcel', 'seat0', '/org/freedesktop/login1/session/_32')]

import os
os.getuid()

import dbus
bus = dbus.SystemBus()
proxy = bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
login1 = dbus.Interface(proxy, 'org.freedesktop.login1.Manager')
fd = login1.Inhibit('handle-power-key', 'test_logind', 'test_logind handling power button', 'block').take()

"""
try:
    import dbus
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('dbus-python', throw=ie, ask=True)
    except err.RestartError:
        import dbus

import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import logging
import schedule
import json
import os

class logindDbus:
    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._bus    = None
        self._proxy  = None
        self._login1 = None
        
        self.inhibit_lock = None
    
    def _setup_dbus_interfaces(self):
        self._bus    = dbus.SystemBus()
        self._proxy  = bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
        self._login1 = dbus.Interface(proxy, 'org.freedesktop.login1.Manager')


    def set_pluginManager(self, pm):
        self._pluginManager = pm

    def register(self):
        pass

    def stop(self):
        pass
    
    def inhibit(self):
        self.inhibit_lock = self._login1.Inhibit('suspend:shutdown', 'mqttScript', 'Inhibation requested from Network', 'block').take()
    
    def findGraphicalSession(self) -> str:
        uid = os.getuid()
        arr = self._login1.ListSessions()
        for a in arr:
            if uid == a[1] and "seat" in a[4]:
                return str(a[0])
    
    def lockGraphicSession(self):
        session_id = self.findGraphicalSession()
        login1.LockSession(session_id)

    def unlockGraphicSession(self):
        session_id = self.findGraphicalSession()
        login1.UnlockSession(session_id)



class logindConfig:
    def __init__(self):
        pass

    def configure(self, conf: conf.BasicConfig, logger:logging.Logger):
        pass


class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "logind"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return logindDbus(client, opts, logger.getChild("logind"), device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        logindConfig().configure(conf, logger.getChild("logind"))