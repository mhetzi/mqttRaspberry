# -*- coding: utf-8 -*-
import logging
from pathlib import Path

import threading
import time
import pkgutil
import sys
from typing import Callable, NoReturn, Union
import Tools.error as err

try:
    import paho.mqtt.client as mclient
except (ImportError, ModuleNotFoundError) as ie:
    try:
        err.try_install_package('paho.mqtt', throw=ie, ask=False)
    except err.RestartError:
        import paho.mqtt.client as mclient
try:
    import schedule
except ImportError as ie:
    try:
        err.try_install_package('schedule', throw=ie, ask=False)
    except err.RestartError:
        import schedule

import Tools.Config as tc

from abc import ABC, abstractmethod

class PluginInterface(ABC):
    
    # Do necessary registrations, this gets called on (re)connect with the mqtt broker 
    @abstractmethod
    def register(self, wasConnected=False): pass

    # Shutdown plugin
    @abstractmethod
    def stop(self): pass

    # Resend states, this can get invoked over MQTT via sending anything to "broadcast/updateAll"
    @abstractmethod
    def sendStates(self): pass

    # Give the PluginManager instance to the Plugin
    @abstractmethod
    def set_pluginManager(self, pm): pass

class PluginManager:

    needed_list = []
    configured_list = {}
    is_connected = False
    scheduler_event = None
    _client: Union[mclient.Client, None]

    def run_scheduler_continuously(self, interval=1):
        """Continuously run, while executing pending jobs at each elapsed
        time interval.
        @return cease_continuous_run: threading.Event which can be set to
        cease continuous run.
        Please note that it is *intended behavior that run_continuously()
        does not run missed jobs*. For example, if you've registered a job
        that should run every minute and you set a continuous run interval
        of one hour then your job won't be run 60 times at each interval but
        only once.
        """
        cease_continuous_run = threading.Event()

        class ScheduleThread(threading.Thread):
            @classmethod
            def run(cls):
                self.logger.debug("ScheduleThread run()")
                nextRun = None
                while not cease_continuous_run.is_set():
                    try:
                        newNextRun = schedule.next_run()
                        if newNextRun != nextRun:
                            #self.logger.info("Der nächste SchedulerThread Job läuft um {}".format(newNextRun))
                            nextRun = newNextRun
                        schedule.run_pending()
                        time.sleep(interval)
                    except:
                        self.logger.exception("Fehler im SchedulerThread")
                self.logger.debug("ScheduleThread exit()")
                schedule.clear()

        continuous_thread = ScheduleThread()
        continuous_thread.name = "scheduler"
        continuous_thread.start()
        self.logger.debug("ScheduleThread gestartet...")
        return (cease_continuous_run, continuous_thread)

    def __init__(self, logger: logging.Logger, config: tc.BasicConfig):
        self.logger = logger.getChild("PluginManager")
        self.config = config
        self._client = None
        self._client_name = None
        self._wasConnected = False
        self.shed_thread = None
        self._discovery_topics = self.config.getIndependendFile("discovery_topics", no_watchdog=True, do_load=True)[0]
        self.discovery_topics = tc.PluginConfig(self._discovery_topics, "Registry")

    def enable_mods(self):
        self.scheduler_event, self.shed_thread = self.run_scheduler_continuously()
        self.configured_list = {}
        mep = list(self.config.get_all_plugin_names())
        i = 0
        while i < len(mep):
            key = mep[i]
            self.logger.debug("[{}/{}] Lade Plugin {}.".format(1+i, len(mep), key))
            i += 1
            plugin = None
            for x in self.needed_list:
                if x.getConfigKey() == key:
                    try:
                        self.logger.info("Konfiguriere Plugin...")
                        plugin = x.getPlugin(client=self._client, opts=self.config, logger=self.logger.parent,
                                        device_id=self._client_name)
                        self.logger.info("Plugin konfiguriert")
                        break
                    except:
                        self.logger.exception("Konfigurieren Fehlgeschlagen!")

            if plugin is None:
                self.logger.warning("Plugin {} nicht vorhanden.".format(key))
                continue
            self.configured_list[key] = plugin

    def needed_plugins(self, get_config=False):
        import Mods
        import importlib.util
        self.needed_list = []

        p = Path(Mods.__path__[0])
        lp = [str(x) for x in list(p.glob('*.py')) if str(x.name).startswith("p", 0)]
        plugin_names = self.config.get_all_plugin_names()

        i = 0

        while i < len(lp):
            x = lp[i]
            self.logger.info("[{}/{}] Überprüfe Plugindatei: {}".format(i+1, len(lp), x))
            try:
                spec = importlib.util.spec_from_file_location("module.name", x)
                foo = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(foo)
                pInfo = foo.PluginLoader()

                if pInfo.getConfigKey() in plugin_names or get_config:
                    self.needed_list.append(pInfo)
                    self.logger.debug("Plugin wird gebraucht.")
                else:
                    self.logger.info("Modul {} wird von der Konfig nicht spezifiziert, werde es wieder entladen...".format(str(foo)))
            except ImportError as x:
                self.logger.exception("Kann Modul {} nicht laden!".format(foo))
            except AttributeError:
                self.logger.warning("Modul hat nur attribute: {}. PluginLoader ist nicht dabei!".format(foo.__dict__))
            except RuntimeError as x:
                self.logger.exception("Modul %s hat RuntimeError verursacht. Die Nachricht war: %s ", foo, x.args)
            except err.InSystemModeError:
                self.logger.error("Kann Modul nicht installieren. In Systemd Modus!")
            except Exception as x:
                self.logger.exception("Modul {} hat eine Exception verursacht. NICHT laden.".format(foo), x)
            i += 1

    def register_mods(self):
        self.logger.info("Regestriere Plugins in MQTT")

        i=0
        sett = list(self.configured_list.items())

        while i < len(sett):
            key = sett[i][0]
            self.logger.info("[{}/{}] Regestriere Plugin {}.".format(1+i, len(sett), key))
            x = sett[i][1]
            i += 1
            try:
                x.set_pluginManager(self)
            except:
                pass
            try:
                x.register(self._wasConnected)
            except:
                try:
                    x.register()
                except:
                    self.logger.exception("Fehler beim Regestrieren des Plugins")

    def send_disconnected_to_mods(self):
        self.logger.info("Verbindung getrennt!")

        i=0
        sett = list(self.configured_list.items())

        while i < len(sett):
            key = sett[i][0]
            self.logger.info("[{}/{}] Informiere Plugin {}.".format(1+i, len(sett), key))
            x = sett[i][1]
            i += 1
            try:
                x.disconnected()
            except:
                self.logger.debug("Fehler beim Informieren des Plugins")

    def get_plguins_by_config_id(self, id:str):
        return self.configured_list[id]

    def disable_mods(self):
        for x in self.configured_list.keys():
            try:
                self.logger.info("Schalte {} aus".format(x))
                p = self.configured_list[x]
                p.stop()
            except AttributeError:
                pass
            except Exception as x:
                self.logger.exception(x)

    def run_configurator(self):
        self.needed_plugins(True)
        for n in self.needed_list:
            i = input("\nPlugin {} Konfigurieren? [N/y]".format(n.getConfigKey()))
            if i == "y" or i == "Y":
                try:
                    n.runConfig(self.config, self.logger)
                except KeyboardInterrupt:
                    self.logger.warning("Konfiguration von Plugin abgebrochen.")
        self.config.save()

    def start_mqtt_client(self):
        self.logger.debug("Erstelle MQTT Client...")
        cc = self.config.get_client_config()
        client = mclient.Client(client_id=cc.client_id, clean_session=cc.clean_session)
        self.logger.debug("Client erstellt.")

        if cc.is_secure():
            self.logger.info("SSL Optionen werden gesetzt...")
            import ssl
        
            client.tls_set(ca_certs=cc.ca, certfile=cc.cert, keyfile=cc.key, tls_version=ssl.PROTOCOL_TLS)
            self.logger.debug("SSL Kontext gesetzt")
        elif cc.broken_security():
            self.logger.warning("Nicht alle Optionen für SSL wurden gesetzt.")

        if cc.has_user():
            self.logger.info("Benutzername und Passwort wird gesetzt...")
            client.username_pw_set(cc.username, cc.password)

        my_name = cc.client_id
        if my_name is None:
            my_name = cc.username
            if my_name is None:
                my_name = "UNSET_DEVICE_NAME"

        client_log = self.logger.getChild("mqtt")
        client_log.setLevel(logging.INFO)
        client.enable_logger(logger=client_log)
        client.on_connect = self.connect_callback
        client.connect_async(cc.host, port=cc.port)
        client.on_disconnect = self.disconnect_callback
        self._client = client
        self._client_name = my_name
        client.will_set(cc.isOnlineTopic, "offline", 0, True)
        return client, my_name

    def reSendStates(self, client=None, userdata=None, message: mclient.MQTTMessage=None):
        self.logger.info("Resend Topic empfangen. alles neu senden...")
        for x in self.configured_list.keys():
            try:
                p = self.configured_list[x]
                p.sendStates()
            except AttributeError:
                pass
            except Exception as x:
                self.logger.exception("Modul unterstützt sendStates() nicht!")

    def disconnect_callback(self, client, userdata, rc):
        self.logger.info("Verbindung getrennt")
        self._wasConnected = self.is_connected or self._wasConnected
        self.is_connected = False

    def connect_callback(self, client, userdata, flags, rc):
        try:
            if rc == 0:
                self.is_connected = True
                self._wasConnected = False
                self.logger.info("Verbunden, regestriere Plugins...")
                self.register_mods()
                self.logger.info("Setze onlinestatus {} auf online".format(self.config.get_client_config().isOnlineTopic))
                self._client.publish(self.config.get_client_config().isOnlineTopic, "online", 0, True)
                self._client.subscribe("broadcast/updateAll")
                self._client.message_callback_add("broadcast/updateAll", self.reSendStates)
                time.sleep(1.0)
                self.reSendStates()

            else:
                self.logger.warning("Nicht verbunden, Plugins werden nicht regestriert. rc: {}, flags: {}".format(rc, flags))
        except:
            self.logger.exception("Fehler in on_connect")

    def _shutdown(self):
        pass
    
    def shutdown(self) -> NoReturn:
        self.logger.info("Plugins werden deaktiviert")
        self.disable_mods()
        self.logger.info("MQTT wird getrennt")
        if self._client is not None:
            self._client.disconnect()
        self.logger.info("Beende Scheduler")
        schedule.clear()
        self.scheduler_event.set()
        self.shed_thread.join()
        exit(0)

