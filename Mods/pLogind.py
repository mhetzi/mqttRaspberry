"""
Könnte sein dass es nur als Benutzerservice (systemctl --user) funktioniert!
Could be that this Plugin only works when run as user service (systemctl --user)!
"""
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
#try:
#    import gi
#    gi.require_version('GLib', '2.0')
#    from gi.repository import GLib
#except Exception as e:
#    logging.exception(e)
#    pass


from time import sleep

POWER_SWITCHE_ONLINE_TOPIC = "online/{}/logindPower"
SLEEP_SWITCHE_ONLINE_TOPIC = "online/{}/logindSleep"

#from Mods.linux.dbus_common import GlibThread, init_dbus

class PluginLoader(PluginMan.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "logind"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        try:
            import dasbus
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('dasbus', throw=ie, ask=False)
        return logindDbus(client, opts, logger.getChild("logind"), device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        logindConfig().configure(conf, logger.getChild("logind"))

    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import dasbus
        except ImportError as ie:
            return ["dasbus"]
        return []

BUILD_PLGUIN = True


try:
    import dasbus

    from dasbus.connection import SystemMessageBus
    from dasbus.connection import SessionMessageBus

    import Mods.linux.dbus_common
except ImportError as ie:
    BUILD_PLGUIN = False

if BUILD_PLGUIN:
    class IdleMonitor:
        _idle_watch_id = None
        _register_delay_id = None
        _IdelingPolling = None
        _is_idle  = False
        __sheduler_fails = 0

        def __init__(self, interval:int, log:logging.Logger, pm: PluginMan.PluginManager, bus: SessionMessageBus, netName="E_NOTSET"):
            self._log  = log.getChild("Mutter.IdleMonitor")
            self._timeout = interval

            self._bsensor = BinarySensor(self._log, pm, "{} AFK".format(netName), autodisc.BinarySensorDeviceClasses.OCCUPANCY, "")

            self._bus      = bus
            self.proxy     = None
            self.idlemon   = None

            self._idle_watch_id   = None
            self._active_watch_id = None

        def stop(self):
            if self._IdelingPolling is not None:
                schedule.cancel_job(self._IdelingPolling)
            if self._register_delay_id is not None:
                schedule.cancel_job(self._register_delay_id)
            if self._idle_watch_id is not None:
                self.proxy.RemoveWatch(self._idle_watch_id)
            if self._active_watch_id is not None:
                self.proxy.RemoveWatch(self._active_watch_id)
            self._bsensor.turnOff()
        
        def _delayed_register(self):
            try:
                self.proxy     = self._bus.get_proxy('org.gnome.Mutter.IdleMonitor', '/org/gnome/Mutter/IdleMonitor/Core')

                self._idle_watch_id = self.proxy.AddIdleWatch(self._timeout)
                self._active_watch_id = self.proxy.AddUserActiveWatch()

                self.proxy.WatchFired.connect(lambda x: self.isIdle(x))   

                self._bsensor.register()
                idleing = self.proxy.GetIdletime()
                if idleing > self._timeout:
                    self._bsensor.turnOff()
                    self._is_idle = True
                else:
                    self._bsensor.turnOn()
                    self._is_idle = False
                if self._register_delay_id is not None:
                    schedule.cancel_job(self._register_delay_id)
                
                if self._IdelingPolling is not None:
                    schedule.cancel_job(self._IdelingPolling)
                self._IdelingPolling = schedule.every(2).minutes.do(self.isIdleDead)
            except Exception:
                self._log.exception("DBus Signale von Mutter verbinden fehlgeschlagen! Wird in 30 Sekunden erneut probiert,,,")
                pass

        def register(self):
            if self._register_delay_id is not None:
                schedule.cancel_job(self._register_delay_id)
            self._register_delay_id = schedule.every(30).seconds.do(self._delayed_register)
            self._register_delay_id.run()  

        def isIdle(self, id):
            self._log.debug("isIdle: ID: {}".format(id))
            try:
                if id == self._idle_watch_id:
                    self._bsensor.turnOff()
                    if self._active_watch_id is not None:
                        self.proxy.RemoveWatch(self._active_watch_id)
                    self._active_watch_id = self.proxy.AddUserActiveWatch()
                elif id == self._active_watch_id:
                    self._bsensor.turnOn()
                    if self._active_watch_id is not None:
                        self.proxy.RemoveWatch(self._active_watch_id)
                    self._active_watch_id = None
            except:
                self._log.exception("isIdle Exception!")

        def isIdleDead(self):
            try:
                idleing = self.proxy.GetIdletime()
                isIdle = idleing > self._timeout
                if isIdle != self._is_idle:
                    self._log.info("Polling Idle zeigt dass uns das Event nicht erreicht hat.")
                    from time import sleep
                    sleep(0.25)
                    isIdle = idleing > self._timeout
                    if isIdle != self._is_idle:
                        self._log.warning("Polling Idle zeigt dass uns das Event definitiv nicht erreicht hat. Signale werden neu eingerichte...")
                        self.stop()
                        self.register()
            except Exception:
                self._log.exception("isIdleDead():")
                from time import sleep
                sleep(2.5)
                self.__sheduler_fails += 1
                if self.__sheduler_fails > 5:
                    self.__sheduler_fails = 0
                    self.stop()
                    self.register()


    class Session:
        name = ""
        session = None
        isGUI = False
        _lock = None

        _glib_thr = None

        def __init__(self, log:logging.Logger, pm: PluginMan.PluginManager, bus_path:str, bus: SystemMessageBus):
            self._proxy     = bus.get_proxy('org.freedesktop.login1', bus_path)
            self._proxy_m     = bus.get_proxy('org.freedesktop.login1', bus_path)
            self.session    = bus.get_proxy('org.freedesktop.login1.Session', bus_path)
            #self.properties = dbus.Interface(self._proxy, 'org.freedesktop.DBus.Properties')
            self.isGUI      = "seat" in self._proxy.Get("org.freedesktop.login1.Session", "Seat")[0]
            self.name       = self._proxy.Get("org.freedesktop.login1.Session", "Id")
            self.isRemote   = self._proxy.Get("org.freedesktop.login1.Session", "Remote")
            self.uname      = self._proxy.Get("org.freedesktop.login1.Session", "Name")
            self.uID        = self._proxy.Get("org.freedesktop.login1.Session", "User")
            self.lockedHint = self._proxy.Get("org.freedesktop.login1.Session", "LockedHint")

            self._log = log.getChild("Session")
            self._pman = pm

            self._lock_notify   = None
            self._unlock_notify = None
            self._glib_thr      = Mods.linux.dbus_common.init_dbus(self._log)

        def _process_prop_changed(self, src, dic, arr):
            self.lockedHint = self._proxy.Get("org.freedesktop.login1.Session", "LockedHint")
            if self.lockedHint:
                self._lock.lock()
            else:
                self._lock.unlock()

        def register(self):
            if self.isGUI and self.uID[0] == os.getuid():
                self._lock = Lock(
                    self._log,
                    self._pman,
                    self.callback,
                    "GUI-Anmeldung {}".format(self.uname),
                    unique_id=f"lock.logind.{autodisc.Topics.get_std_devInf().name}.session.gui.{self.uname}.screenlock"
                )
                self._lock.register()

                self._lock_notify    = self._proxy.Lock.connect  ( lambda: self._lock.lock()  )
                self._unlock_notify  = self._proxy.Unlock.connect( lambda: self._lock.unlock() )
                self._proxy.PropertiesChanged.connect( self._process_prop_changed )
                self._process_prop_changed(None, None, None)
        
        def stop(self):
            if self._lock_notify is not None:
                self._lock_notify.remove()
            if self._unlock_notify is not None:
                self._unlock_notify.remove()

            if self._glib_thr is not None:
                Mods.linux.dbus_common.deinit_dbus(logger=self._log)
                self._glib_thr = None

        def terminate(self):
            self._proxy.Terminate()
        
        def lock(self):
            self._log.info("OK Locking session")
            try:
                self._proxy._handler._call_method("org.freedesktop.login1.Session", "Lock", None, None)
                #self._proxy_m.Lock()
            except:
                self._log.exception("Lock failed!")

        def unloock(self):
            self._log.info("OK Unlocking session")
            self._proxy._handler._call_method("org.freedesktop.login1.Session", "Unlock", None, None)
            #self._proxy_m.Unlock()
        
        def callback(self, state_requested=False, message=LockState.LOCK):
            if message == LockState.LOCK:
                self.lock()
            elif message == LockState.UNLOCK:
                self.unloock()
            else:
                self._log.warning("LockState Requested, but it´s invalid.")

    class logindDbus:
        _sleep_delay_lock: Union[int, None] = None

        def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
            self._bus    = None
            self._proxy  = None
            self._login1 = None
            self._logger = logger
            self._mainloop = None
            
            self.sleeping = False
            self.shutdown = False

            self.inhibit_lock = -1
            self._switches: dict[str, Switch] = {}
            self.sessions = {}
            self._config = conf.PluginConfig(opts, "logind")

            self._poff_notiy  = None
            self._sleep_notiy = None
            self._nsess_notiy = None
            self._rsess_notiy = None
            self._idle_monitor = None
        
        def _setup_dbus_interfaces(self):
            #init_dbus()

            self._bus    = SystemMessageBus()
            self._session_bus = SessionMessageBus()
            self._proxy  = self._bus.get_proxy('org.freedesktop.login1', '/org/freedesktop/login1')
            
            #self._login1 = dbus.Interface(self._proxy, 'org.freedesktop.login1.Manager')

            self._nsess_notiy = self._proxy.SessionNew.connect(     lambda sID, path: self._mod_session(add=True,  path=path) )
            self._rsess_notiy = self._proxy.SessionRemoved.connect( lambda sID, path: self._mod_session(add=False,  path=path) )

            #self._nsess_notiy = self._login1.connect_to_signal("SessionNew",     lambda sID, path: self._mod_session(add=True,  path=path) )
            #self._rsess_notiy = self._login1.connect_to_signal("SessionRemoved", lambda sID, path: self._mod_session(add=False, path=path) )
            
            for session in self._proxy.ListSessions():
                self._logger.info("Neue Benutzersession gefunden {} auf {} in Pfad {}.".format(session[2], session[3], session[4]))
                self._mod_session(add=True, path=session[4])
            
            if self._config.get("inactivity_ms", None) is not None: 
                self._idle_monitor = IdleMonitor(
                    self._config["inactivity_ms"],
                    self._logger,
                    self._pluginManager,
                    self._session_bus,
                    netName=autodisc.Topics.get_std_devInf().name if self._config.get("custom_name", None) is None else self._config.get("custom_name", None)
                )
            
        
        def _mod_session(self, add=True, path=str):
            if path in self.sessions.keys():
                self.sessions[path].stop()
                del self.sessions[path]
            if add:
                self.sessions[path] = Session(self._logger, self._pluginManager, path, self._bus)
                self.sessions[path].register()

        def set_pluginManager(self, pm:PluginMan.PluginManager):
            self._pluginManager = pm

        def register(self, wasConnected=False):
            if wasConnected:
                pass # self.stop()
            if not wasConnected:
                self._setup_dbus_interfaces()
                netName = autodisc.Topics.get_std_devInf().name if self._config.get("custom_name", None) is None else self._config.get("custom_name", None)
                # Kann ich ausschalten?

                if self._proxy.CanPowerOff() == "yes" and self._config.get("allow_power_off", True):
                    self._switches["isOn"] = Switch(
                        self._logger,
                        self._pluginManager,
                        lambda state_requested, message: self.sw_call(userdata="isOn",state_requested=state_requested, message=message),
                        name="Eingeschaltet",
                        ava_topic=POWER_SWITCHE_ONLINE_TOPIC.format(self._pluginManager._client_name)
                    )
                    self._proxy.PrepareForShutdown.connect(self.sendShutdown)
                # Kann ich suspend?

                if self._proxy.CanSuspend() == "yes" and self._config.get("allow_suspend", True):
                    self._switches["suspend"] = Switch(
                        self._logger,
                        self._pluginManager,
                        lambda state_requested, message: self.sw_call(userdata="suspend",state_requested=state_requested, message=message),
                        name="Schlafen", icon="mdi:sleep",
                        ava_topic=SLEEP_SWITCHE_ONLINE_TOPIC.format(self._pluginManager._client_name)
                    )
                    self._sleep_notiy = self._proxy.PrepareForSleep.connect(self.sendSuspend)
                # Kann ich neustarten?

                if self._proxy.CanReboot() == "yes" and self._config.get("allow_reboot", True):
                    self._switches["reboot"] = Switch(
                        self._logger,
                        self._pluginManager,
                        lambda state_requested, message: self.sw_call(userdata="reboot",state_requested=state_requested, message=message),
                        name="Neustarten", icon="mdi:restart"
                    )
                # Kann ich inhibit
                if self.inhibit( ) > 0 and self._config.get("allow_inhibit", True):
                    self.uninhibit( )
                    self._switches["inhibit"] = Switch(
                        self._logger,
                        self._pluginManager,
                        lambda state_requested, message: self.sw_call(userdata="inhibit",state_requested=state_requested, message=message),
                        name="Nicht schlafen", icon="mdi:sleep-off"
                    )

            for v in self._switches.values():
                v.register()

            self.inhibit_delay(True)

            if self._idle_monitor is not None:
                self._idle_monitor.register()


        def inhibit_delay(self, sleep=False):
            if sleep:
                if self._sleep_delay_lock is not None:
                    try:
                        self.inhibit_delay(False)
                    except:
                        pass
                delay_lock = self._proxy.Inhibit(
                    'sleep:shutdown',
                    'mqttScript',
                    'Publish Powerstatus (Standby) to Network',
                    'delay'
                    )
                self._sleep_delay_lock = delay_lock if delay_lock > -1 else None
                self._logger.debug("Sleep delayed" if delay_lock > -1 else "Sleep delay failed!")
            elif not sleep and self._sleep_delay_lock is not None:
                try:
                    os.close(self._sleep_delay_lock)
                except:
                    pass
                self._sleep_delay_lock = None
                self._logger.debug("Sleep lock destroyed")

        def stop(self):
            self._logger.info("[0/6] Setze Stromschalter")
            try:
                self._switches["isOn"].turnOff()
            except: pass
            try:
                self._switches["suspend"].turnOff()
                self._switches["suspend"].offline()
            except: pass

            self._logger.info("[1/6] Entferne Inhibitation block")
            self.uninhibit( )
            self._logger.info("[2/6] Entferne Inhibtitation delay")
            self.inhibit_delay(False)
            self._logger.info("[3/6] Signale werden entfernt")
            if self._poff_notiy is not None:
                self._poff_notiy.remove()
            if self._sleep_notiy is not None and not self.sleeping:
                self._sleep_notiy.remove()
            for k in self.sessions.keys():
                session= self.sessions[k]
                session.stop()
            if self._nsess_notiy is not None:
                self._nsess_notiy.remove()
            if self._rsess_notiy is not None:
                self._rsess_notiy.remove()
            if self._idle_monitor is not None:
                self._logger.info("[4/6] IdleMonitor entfernt Signale und Watches...")
                self._idle_monitor.stop()

        def inhibit(self):
            if self.inhibit_lock > 1:
                return self.inhibit_lock
            self.inhibit_lock = self._proxy.Inhibit(
                'sleep:shutdown',
                'mqttScript',
                'Inhibation requested from HomeAssistant',
                'block'
                )
            return self.inhibit_lock
        
        def uninhibit(self):
            if self.inhibit_lock > 1:
                os.close(self.inhibit_lock)
            self.inhibit_lock = -1

        def findGraphicalSession(self) -> str:
            uid = os.getuid()
            arr = self._proxy.ListSessions()
            for a in arr:
                if uid == a[1] and "seat" in a[4]:
                    return str(a[0])
        
        def lockGraphicSession(self):
            session_id = self.findGraphicalSession()
            self._proxy.LockSession(session_id)

        def unlockGraphicSession(self):
            session_id = self.findGraphicalSession()
            self._proxy.UnlockSession(session_id)

        def sendSuspend(self, sig):
            self._logger.debug(f"Suspend: {sig = }")
            if sig == True:
                if self._idle_monitor is not None:
                    try:
                        self._idle_monitor.stop()
                    except:
                        self._idle_monitor = None
                self.sleeping = True
                try:
                    self._switches["suspend"].turnOn().wait_for_publish(timeout=2)
                    #self._pluginManager.disconnect()
                except:
                    self._logger.exception("MQTT Stuff")
            else:
                self.sleeping = False
                #self._pluginManager.reconnect()
                try:
                    self._switches["suspend"].turnOff().wait_for_publish(timeout=2)
                except:
                    self._logger.exception("Probably not fully back from standby!")
                    
            self._logger.debug("Send done!")
            self.inhibit_delay(sleep=not sig)

        def sendShutdown(self, sig):
            self._logger.debug(f"Shutdown: {sig = }")
            if sig == True:
                self.shutdown = True
                self._switches["isOn"].turnOff().wait_for_publish(timeout=2)
                try:
                    self._idle_monitor.stop()
                except:
                    self._idle_monitor = None
            else:
                self.shutdown = False
                self._switches["isOn"].turnOn().wait_for_publish(timeout=2)
            self.inhibit_delay(sleep=not sig)

        def sw_call(self, userdata=None, state_requested=False, message=None):
            if state_requested:
                if userdata == "isOn":
                    if self.shutdown or self.sleeping:
                        self._switches["isOn"].turnOff()
                    else:
                        self._switches["isOn"].turnOn()
                elif userdata == "suspend":
                    if self.sleeping:
                        self._switches["suspend"].turnOn()
                    else:    
                        self._switches["suspend"].turnOff()
                elif userdata == "reboot":
                    self._switches["reboot"].turnOff()
                elif userdata == "inhibit":
                    if self.inhibit_lock > 0:
                        self._switches["inhibit"].turnOn()
                    else:
                        self._switches["inhibit"].turnOff()
                return
            msg = message.payload.decode('utf-8')
            if userdata == "isOn" and msg == "OFF":
                self._proxy.PowerOff(True)
                self._switches["isOn"].turnOff()
            elif userdata == "suspend" and msg == "ON":
                self.sleeping = True
                self._proxy.Suspend(True)
                self._switches["suspend"].turnOn()
                self._idle_monitor.stop()
            elif userdata == "reboot" and msg == "ON": 
                self._proxy.Reboot(True)
            elif userdata == "inhibit" and msg == "ON":
                if self.inhibit_lock < 1:
                    self.inhibit()
                if self.inhibit_lock > 0:
                    self._switches["inhibit"].turnOn()
            elif userdata == "inhibit" and msg == "OFF":
                if self.inhibit_lock > 0:
                    self.uninhibit()
                if self.inhibit_lock < 1:
                    self._switches["inhibit"].turnOff()
            

class logindConfig:
    def __init__(self):
        pass

    def configure(self, conff: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        con = conf.PluginConfig(conff, "logind")

        con["allow_power_off"] = ConsoleInputTools.get_bool_input("\nErlaube Ausschalten: ", True)
        con["allow_suspend"] = ConsoleInputTools.get_bool_input("\nErlaube Bereitschaftsmodus: ", True)
        con["allow_reboot"] = ConsoleInputTools.get_bool_input("\nErlaube Neustarten: ", True)
        con["allow_inhibit"] = ConsoleInputTools.get_bool_input("\nErlaube Blockieren von Schlafmodus: ", True)
        if ConsoleInputTools.get_bool_input("\nBenutze anderen Namen: ", True):
            con["custom_name"] = ConsoleInputTools.get_input("\nDen Namen Bitte: ", True)
        con["inactivity_ms"] = ConsoleInputTools.get_number_input("\nInaktivität nach x Millisekunden: ")
