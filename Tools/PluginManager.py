# -*- coding: utf-8 -*-
import logging
from pathlib import Path

import threading
import time
import weakref
from typing import Any, Callable, NoReturn, Union
import Tools.error as err

try:
    from paho.mqtt.client import Client as MqttClient
    from paho.mqtt.client import MQTTMessageInfo
    import paho.mqtt.client as mclient
    import paho.mqtt.enums as mqttEnums
except (ImportError, ModuleNotFoundError) as ie:
    try:
        err.try_install_package('paho.mqtt', throw=ie, ask=False)
    except err.RestartError:
        from paho.mqtt.client import Client as MqttClient
try:
    import schedule
except ImportError as ie:
    try:
        err.try_install_package('schedule', throw=ie, ask=False)
    except err.RestartError:
        import schedule

import Tools.Config as tc
from Tools import PropagetingThread

import dataclasses
from abc import ABC, abstractmethod

@dataclasses.dataclass(slots=True)
class PluginInterface(ABC):
    _config: tc.BasicConfig | tc.PluginConfig
    _logger: logging.Logger
    _device_id: str
    _pluginManager: "PluginManager | None" = None
    
    # Do necessary registrations, this gets called on (re)connect with the mqtt broker 
    @abstractmethod
    def register(self, wasConnected: bool = False) -> None: pass

    # Shutdown plugin
    @abstractmethod
    def stop(self) -> None: pass

    # Resend states, this can get invoked over MQTT via sending anything to "broadcast/updateAll"
    # Gets called when homeassistant/status becomes "online"
    @abstractmethod
    def sendStates(self) -> None: pass

    # Give the PluginManager instance to the Plugin
    def set_pluginManager(self, pm: "PluginManager") -> None:
        self._pluginManager = pm

    #Inform Plugin about disconnect
    @abstractmethod
    def disconnected(self) -> None: pass


@dataclasses.dataclass(slots=True)
class PluginLoader(ABC):
    @staticmethod
    @abstractmethod 
    def getConfigKey() -> str: raise NotImplementedError()

    @staticmethod
    @abstractmethod 
    def getPlugin(opts: tc.BasicConfig, logger: logging.Logger) -> PluginInterface: raise NotImplementedError()

    @staticmethod
    @abstractmethod 
    def runConfig(conf: tc.BasicConfig, logger: logging.Logger) -> None: raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def getNeededPipModules() -> list[str]: raise NotImplementedError()

@dataclasses.dataclass(slots=True)
class SchemaEntry:
    cls: type
    name: str
    description: str
    default: object | None

@dataclasses.dataclass(slots=True)
class ConfiguratorInterface(ABC):
    @staticmethod
    @abstractmethod
    def getConfigSchema() -> dict[str, SchemaEntry]: raise NotImplementedError()
    
    @staticmethod
    @abstractmethod
    def getCurrentConfig(conf: tc.BasicConfig) -> tc.PluginConfig: raise NotImplementedError()

class PluginManager:
    # MQTT Topics und Konstanten
    MQTT_BROADCAST_TOPIC = "broadcast/updateAll"
    MQTT_HASS_STATUS_TOPIC = "homeassistant/status"
    MQTT_OFFLINE_MESSAGE = "offline"
    MQTT_ONLINE_MESSAGE = "online"
    SCHEDULER_THREAD_NAME = "scheduler"
    MQTT_THREAD_NAME = "mqttConnected"
    
    def run_scheduler_continuously(self, interval: int = 1) -> tuple[threading.Event, threading.Thread]:
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
        self.logger = logger.getChild("PM")
        self.logger.setLevel(logging.NOTSET)
        self.config = config
        # Klassenvariablen als Instanzvariablen initialisieren
        self.needed_list: list[PluginLoader] = []
        self.configured_list: dict[str, PluginInterface] = {}
        self.is_connected = False
        self.scheduler_event = None
        self._connected_callback_thread: PropagetingThread.PropagatingThread | None = None
        self._client: MqttClient | None = None
        self._client_name = None
        self._wasConnected = False
        self.shed_thread = None
        self._discovery_topics = self.config.getIndependendFile("discovery_topics", no_watchdog=True, do_load=True)[0]
        self.discovery_topics = tc.PluginConfig(self._discovery_topics, "Registry")
        self._offline_handlers: list[weakref.WeakMethod[Callable[[], None | MQTTMessageInfo]]] = []
        self._offline_handlers_lock = threading.Lock()
        self._mqttEvent = threading.Event()
        self._mqttShutdown = threading.Event()

    def addOfflineHandler(self, func: Callable[[], MQTTMessageInfo | None]) -> None:
        with self._offline_handlers_lock:
            self.logger.debug(f"Adding {func=} to offlineHandlers...")
            self._offline_handlers.append(weakref.WeakMethod(func))

    def get_pip_list(self) -> None:
        pip_list: list[str] = []
        mep = list(self.config.get_all_plugin_names())
        for i, key in enumerate(mep, 1):
            self.logger.debug("[{}/{}] Teste Pip {}.".format(i, len(mep), key))
            for x in self.needed_list:
                try:
                    pip_list = pip_list + x.getNeededPipModules()
                except NotImplementedError:
                    pass
                except Exception as e:
                    self.logger.exception("Exception while preparing pip list!")
        if len(pip_list) > 0:
            from Tools.error import RestartError
            try:
                from Tools.error import try_install_packages
                try_install_packages(pip_list, ask=False)
            except RestartError:
                pass
            except:
                self.logger.exception("Installing required Packages failed!")


    def enable_mods(self) -> None:
        if self.scheduler_event is None:
            self.scheduler_event, self.shed_thread = self.run_scheduler_continuously()
        self.configured_list = {}
        mep = list(self.config.get_all_plugin_names())
        for i, key in enumerate(mep, 1):
            self.logger.debug("[{}/{}] Lade Plugin {}.".format(i, len(mep), key))
            plugin = None
            for x in self.needed_list:
                if x.getConfigKey() == key:
                    try:
                        self.logger.info("Konfiguriere Plugin...")
                        plugin = x.getPlugin(opts=self.config, logger=self.logger)
                        self.logger.info("Plugin konfiguriert")
                        break
                    except:
                        self.logger.exception("Konfigurieren Fehlgeschlagen!")

            if plugin is None:
                self.logger.warning("Plugin {} nicht vorhanden.".format(key))
                continue
            self.configured_list[key] = plugin

    def needed_plugins(self, get_config=False) -> list[PluginLoader]:
        import Mods
        import importlib.util
        self.needed_list = []

        p = Path(Mods.__path__[0])
        paths = list(p.glob('*/*.py')) + list(p.glob('*.py')) 
        lp = [str(x) for x in paths if str(x.name).startswith("p", 0) or x.name == "__init__.py"]
        plugin_names = self.config.get_all_plugin_names()

        for i, x in enumerate(lp, 1):
            self.logger.info("[{}/{}] Überprüfe Plugindatei: {}".format(i, len(lp), x))
            try:
                spec = importlib.util.spec_from_file_location("module.name", x)
                if spec is None:
                    self.logger.error(f"Loading {x}: spec is None")
                    continue
                mod = importlib.util.module_from_spec(spec)
                if mod is None:
                    self.logger.error(f"Loading {x}: Module is None")
                    continue
                if spec.loader is None:
                    self.logger.error(f"Loading {x}: spec.loader is None")
                    continue
                spec.loader.exec_module(mod)
                pInfo: PluginLoader = mod.PluginLoader()

                if pInfo.getConfigKey() in plugin_names or get_config:
                    self.needed_list.append(pInfo)
                    self.logger.debug("Plugin wird gebraucht.")
                else:
                    self.logger.info("Modul {} wird von der Konfig nicht spezifiziert, werde es wieder entladen...".format(str(mod)))
            except ImportError as x:
                self.logger.exception("Kann Modul {} nicht laden!".format(x))
            except AttributeError:
                pass
                # self.logger.warning("Modul hat nur attribute: {}. PluginLoader ist nicht dabei!".format(mod.__dict__))
            except RuntimeError as x:
                self.logger.exception("Modul %s hat RuntimeError verursacht. Die Nachricht war: %s ", mod, x.args)
            except err.InSystemModeError:
                self.logger.exception("Kann Modul nicht installieren. In Systemd Modus!")
            except Exception as ex:
                self.logger.exception("Modul %s hat eine Exception verursacht. NICHT laden.", x)
        return self.needed_list

    def register_mods(self) -> None:
        self.logger.info("Regestriere Plugins in MQTT")

        clen = len(self.configured_list)
        i: int = 1

        for pname, pobject in self.configured_list.items():
            self.logger.info(f"[{i}/{clen}] Tell Plugin about MQTT {pname}.")
            i += 1
            try:
                pobject.set_pluginManager(self)
            except AttributeError:
                self.logger.debug(f"Plugin {pname} hat keine set_pluginManager Methode")
            
            try:
                pobject.register(wasConnected=self._wasConnected)
            except TypeError:
                try:
                    pobject.register()
                except Exception as e:
                    self.logger.exception(f"Fehler beim Registrieren des Plugins {pname}: {e=} ")

    def send_disconnected_to_mods(self) -> None:
        self.logger.info("Verbindung getrennt!")
        clen = len(self.configured_list)
        i: int = 1

        for pname, pobject in self.configured_list.items():
            self.logger.info(f"[{i}/{clen}] Informiere Plugin {pname}.")
            i += 1
            try:
                pobject.disconnected()
            except (AttributeError, Exception) as e:
                self.logger.debug(f"Fehler beim Informieren des Plugins {pname}: {e}")

    def get_plguins_by_config_id(self, id: str) -> PluginInterface:
        return self.configured_list[id]

    def disable_mods(self) -> None:
        for x in self.configured_list.keys():
            try:
                self.logger.info("Schalte {} aus".format(x))
                p = self.configured_list[x]
                p.stop()
            except AttributeError:
                pass
            except Exception as x:
                self.logger.exception(x)

    def get_configs(self) -> list[PluginLoader]:
        self.needed_plugins(True)
        return self.needed_list

    def run_configurator(self, name: str | None = None) -> None:
        self.needed_plugins(True)
        for n in self.needed_list:
            if name and n.getConfigKey() != name:
                continue
            i = input("\nPlugin {} Konfigurieren? [N/y]".format(n.getConfigKey()))
            if i == "y" or i == "Y":
                try:
                    n.runConfig(self.config, self.logger)
                except KeyboardInterrupt:
                    self.logger.warning("Konfiguration von Plugin abgebrochen.")
        self.config.save()

    def start_mqtt_client(self) -> tuple[MqttClient, str]:
        self.logger.debug("Erstelle MQTT Client...")
        cc = self.config.get_client_config()
        
        try:
            client = MqttClient(client_id=cc.client_id, clean_session=cc.clean_session)
        except TypeError:
            # Fallback für ältere paho-mqtt Versionen
            client = MqttClient(client_id=cc.client_id, clean_session=cc.clean_session, callback_api_version=mqttEnums.CallbackAPIVersion.VERSION1)
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

    def reSendStates(self, client: MqttClient | None = None, userdata: Any | None = None, message: MQTTMessageInfo | None = None) -> None:
        self.logger.info("Resend Topic empfangen. alles neu senden...")
        for x in self.configured_list.keys():
            try:
                p = self.configured_list[x]
                p.sendStates()
            except AttributeError:
                self.logger.debug(f"Plugin {x} hat keine sendStates() Methode")
            except Exception as e:
                self.logger.exception(f"Fehler beim Senden von States für Plugin {x}: {e}")

    def disconnect(self, skip_callbacks: bool = False, reconnect: float = 0) -> mqttEnums.MQTTErrorCode:
        if reconnect < 0.5:
            self._mqttEvent.set()
        err: mqttEnums.MQTTErrorCode = mqttEnums.MQTTErrorCode.MQTT_ERR_UNKNOWN
        if self._client is not None:
            self._client.reconnect_delay_set(min_delay=5, max_delay=300)
            err = self._client.disconnect()
            if skip_callbacks:
                self.disconnect_callback(self._client, self, err)
            self.logger.debug("Waiting for MQTT Client to exit")
            self._client.loop_stop()
        if reconnect > 0.5:
            import time
            time.sleep(reconnect)
            self.reconnect()
        return err

    def reconnect(self) -> None:
        self._mqttEvent.set()

    def disconnect_callback(self, client: MqttClient, userdata: Any, rc: mqttEnums.MQTTErrorCode) -> None:
        self.is_connected = False
        self.logger.info(f"Verbindung getrennt {rc=}")
        self._wasConnected = self.is_connected or self._wasConnected
        self.is_connected = False
        with self._offline_handlers_lock:
            # self.logger.debug(f"self._offline_handlers.len = {len(self._offline_handlers)}")
            self._offline_handlers = [rm for rm in self._offline_handlers if rm() is not None]
            self.logger.debug(f"self._offline_handlers.len = {len(self._offline_handlers)}")
            for f in self._offline_handlers:
                try:
                    # self.logger.debug(f"Call disconnect_callback {f=}")
                    real_func = f()
                    if real_func is not None:
                        real_func()
                    else:
                        self.logger.warning(f"Callable is dead!")
                except Exception as e:
                    self.logger.exception(f"Fehler beim Aufrufen des Offline-Handlers: {e}")
        self.logger.info(f"Verbindung getrennt, alles aufgeräumt! {client=}")
        try:
            if rc == mqttEnums.MQTTErrorCode.MQTT_ERR_KEEPALIVE:
                self.logger.info("KeepAlive Error. Disconnect!")
                client.disconnect()
                client.loop_stop()
        except Exception as e:
            self.logger.exception("Fehler beim Trennen der Verbindung!")
        
        try:
            self.send_disconnected_to_mods()
        except Exception as e:
            self.logger.exception(f"Fehler beim Benachrichtigen der Module: {e}")

    def connect_callback(self, client: MqttClient, userdata: Any, flags: int, rc: int) -> None:
        self.logger.info(f"Verbunden ({client}), regestriere Plugins...")
        if self._connected_callback_thread is None or not self._connected_callback_thread.is_alive():
            self._connected_callback_thread = PropagetingThread.PropagatingThread(name="mqttConnected", target=lambda: self._connect_callback(client,userdata,flags,rc))
            self._connected_callback_thread.start()
        else:
            self.logger.error("on_connect callback already running!")
            try:
                self.shutdown()
            except Exception as e:
                self.logger.debug(f"Fehler beim Trennen des Clients: {e}")
            self.disconnect(reconnect=30)


    def hass_online_call(self, client: MqttClient, userdata: Any, message: Any) -> None:
        msg = message.payload.decode('utf-8')
        if msg == "online":
            self.logger.info("HomeAssistant ist online. Alle sensoren neu senden!")
            self.reSendStates()


    def _connect_callback(self, client: MqttClient, userdata: Any, flags: int, rc: int) -> None:
        if self.is_connected:
            self.logger.error(f"Bin Verbunden ({client=}). Trenne verbindung...")
            self.disconnect(reconnect=15)
            return
        self._client = client
        
        self._client.subscribe(self.MQTT_HASS_STATUS_TOPIC)
        self._client.message_callback_add(self.MQTT_HASS_STATUS_TOPIC, self.hass_online_call)
        try:
            if rc == 0:
                self.is_connected = True
                self.logger.info(f"Verbunden ({client}), regestriere Plugins...")
                self.register_mods()

                self.logger.info("Setze onlinestatus {} auf online".format(self.config.get_client_config().isOnlineTopic))
                self._client.publish(self.config.get_client_config().isOnlineTopic, self.MQTT_ONLINE_MESSAGE, 0, True).wait_for_publish(30)
                self._client.subscribe(self.MQTT_BROADCAST_TOPIC)
                self._client.message_callback_add(self.MQTT_BROADCAST_TOPIC, self.reSendStates)
                self.reSendStates()
                self._wasConnected = True

            else:
                self.logger.warning("Nicht verbunden, Plugins werden nicht regestriert. rc: {}, flags: {}".format(rc, flags))
        except Exception as e:
            self.logger.exception("Fehler in on_connect")
            self.is_connected = False
        
        if not self.is_connected:
            self.logger.debug("Connection Lost while setup")
            self.shutdown()
            return
        self.logger.info("Verbunden. Alles OK!")

    def _shutdown(self) -> None:
        pass
    
    def _shutdownFromExit(self) -> None:
        self.logger.info("Plugins werden deaktiviert")
        self.disable_mods()
        self.logger.info("MQTT wird getrennt")
        self._mqttEvent.set()
        self._mqttShutdown.set()
        if self._client is not None:
            try:
                self._client.publish(self.config.get_client_config().isOnlineTopic, self.MQTT_OFFLINE_MESSAGE, 0, True).wait_for_publish(30)
            except Exception as e:
                self.logger.debug(f"Fehler beim Offline Publish: {e}")
            self._client.disconnect()
        self.logger.info("Beende Scheduler")
        schedule.clear()
        if self.scheduler_event is not None:
            self.scheduler_event.set()
        if self.shed_thread is not None:
            self.shed_thread.join()

    def shutdown(self) -> NoReturn:
        self._shutdownFromExit()
        exit(0)
    
    def mqtt_loopforever(self) -> None:
        from Tools.PropagetingThread import PropagatingThread
        from Tools.Config import NoClientConfigured
        from time import sleep
        self._mqttShutdown.clear()
        try:
            while not self._mqttShutdown.is_set():
                self._mqttEvent.clear()
                mqtt_client, deviceID = self.start_mqtt_client()
                self.logger.info("Running MQTT Main Loop")
                mqtt_client.loop_start()
                thread: PropagatingThread = mqtt_client._thread
                ret, exc = thread.joinNoRaise()
                self.logger.warning(f"MQTT PropagatingThread has {ret=} with {exc=}", exc_info=exc)
                if isinstance(exc, (ConnectionRefusedError, KeyboardInterrupt, NoClientConfigured)):
                    raise exc
                if not self._mqttEvent.wait(120):
                    self.logger.error("Stuck in Reconnect wait!")
                    self.shutdown()
        except:
            self.logger.exception("MQTT Exception")

