"""
Könnte sein dass es nur als Benutzerservice (systemctl --user) funktioniert!
Could be that this Plugin only works when run as user service (systemctl --user)!
"""
from typing import IO, Union
import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
from Tools import PluginManager
from Tools.Devices.Switch import Switch
import logging
import schedule
from Tools import ResettableTimer

from time import sleep

try:
    import dasbus

    from dasbus.connection import SystemMessageBus
    from dasbus.connection import SessionMessageBus

    import Mods.linux.dbus_common

    class gnomeScreensaver(PluginManager.PluginInterface):
        _sleep_delay_lock: Union[IO, None] = None

        def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
            self._session_bus    = None
            self._proxy  = None
            self._upower = None
            self._logger = logger
            self._mainloop = None
            #self.thread_gml = GlibThread.getThread()
            self._glib_thread = None
            self._config = conf.PluginConfig(opts, PluginLoader.getConfigKey())
            self._sw = None

            self._timer = ResettableTimer.ResettableTimer(10, lambda n: self._timercall(), autorun=False)
            self._last = None

        
        def _setup_dbus_interfaces(self):
            self._glib_thread = Mods.linux.dbus_common.init_dbus()

            self._logger.debug("Getting dbus bus...")
            self._session_bus = SessionMessageBus()
            self._proxy  = self._session_bus.get_proxy('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver')

            self._logger.debug("Subscribing to dbus notifications...")
            self._nsess_notiy = self._proxy.ActiveChanged( lambda b: self.activeChanged(b) )

        def _timercall(self):
            now: bool = self._proxy.GetActive()
            if self._last != now:
                self._logger.warning(f"Screensaver value now: {now} != last: {self._last}")
                self.register(wasConnected=True)

            return self.sendStates()

        def activeChanged(self, active:bool):
            if self._sw is not None:
                self._sw.turn(state=active)
        
        def sw_call(self, message, state_requested:bool):
            if self._proxy is None or self._sw is None:
                return
            if message:
                self._proxy.SetActive(bool(message))
            self._timer.reset()

        def set_pluginManager(self, pm:PluginManager.PluginManager):
            self._pluginManager = pm

        def register(self, wasConnected=False):
            if self._sw is None:
                self._sw = Switch(
                name="Screensaver",
                logger=self._logger,
                pman=self._pluginManager,
                callback=self.sw_call,
                icon="mdi:monitor"
            )
                
            if wasConnected:
                self._logger.debug("Reconnected! Resetting Stuff...")
                self.stop()

            self._logger.debug("Register dbus interface...")
            self._setup_dbus_interfaces()

            self._sw.register()
            self.sendStates()

        def sendStates(self):
            self._timer.reset()
            if self._sw is not None and self._proxy is not None:
                self._last = self._proxy.GetActive()
                return self._sw.turn(state=self._last)
            return super().sendStates()

        def stop(self):
            self._logger.info("[1/2] Signale werden entfernt")
            if self._nsess_notiy is not None:
                self._nsess_notiy.remove()

            self._logger.info("[2/2] GLib MainThread stop")
            if self._glib_thread is not None:
                Mods.linux.dbus_common.deinit_dbus()

except ImportError as ie:
    pass            


class gnomeScreensaverConfig:
    def __init__(self):
        pass

    def configure(self, bc: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        c = conf.PluginConfig(bc, "gnome-shell-screensaver")
        c["_"] = "" 


class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "gnome-shell-screensaver"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return gnomeScreensaver(client, opts, logger.getChild(PluginLoader.getConfigKey()), device_id)

    @staticmethod
    def runConfig(bc: conf.BasicConfig, logger:logging.Logger):
        gnomeScreensaverConfig().configure(bc, logger.getChild("logind"))
    
    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import dasbus
        except ImportError as ie:
            return ["dasbus"]
        return []