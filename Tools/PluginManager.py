# -*- coding: utf-8 -*-
import logging
from pathlib import Path
import paho.mqtt.client as mclient
import Tools.Config as tc
import threading
import schedule
import time

class PluginManager:

    needed_list = []
    configured_list = {}
    is_connected = False
    scheduler_event = None

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
                            self.logger.info("Der nächste SchedulerThread Job läuft um {}".format(newNextRun))
                            nextRun = newNextRun
                        schedule.run_pending()
                        time.sleep(interval)
                    except:
                        self.logger.exception("Fehler im SchedulerThread")
                self.logger.debug("ScheduleThread exit()")
                schedule.clear()

        continuous_thread = ScheduleThread()
        continuous_thread.start()
        self.logger.debug("ScheduleThread gestartet...")
        return cease_continuous_run

    def __init__(self, logger: logging.Logger, config: tc.BasicConfig):
        self.logger = logger.getChild("PluginManager")
        self.config = config
        self._client = None
        self._client_name = None

    def enable_mods(self):
        self.scheduler_event = self.run_scheduler_continuously()
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
                    self.logger.info("Konfiguriere Plugin...")
                    plugin = x.getPlugin(client=self._client, opts=self.config, logger=self.logger.parent,
                                       device_id=self._client_name)
                    self.logger.info("Plugin konfiguriert")
                    break

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
            #except Exception as x:
            #    self.logger.exception("Modul {} hat ieine Exception verursacht. NICHT laden.".format(foo), x)
            i += 1

    def register_mods(self):
        self.logger.info("Regestriere Plugins in MQTT")
        for x in self.configured_list.values():
            try:
                x.set_pluginManager(self)
            except:
                pass
            try:
                x.register()
            except:
                self.logger.exception("Fehler beim Regestireren des Plugins")

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

        client.enable_logger(self.logger.getChild("mqtt"))
        client.on_connect = self.connect_callback
        client.connect(cc.host, port=cc.port)
        self._client = client
        self._client_name = my_name
        return client, my_name

    def reSendStates(self, client, userdata, message: mclient.MQTTMessage):
        self.logger.info("Resend Topic empfangen. alles neu senden...")
        for x in self.configured_list.keys():
            try:
                p = self.configured_list[x]
                p.sendStates()
            except AttributeError:
                pass
            except Exception as x:
                self.logger.exception("Modul unterstützt sendStates() nicht!")

    def connect_callback(self, client, userdata, flags, rc):
        if rc == 0 and not self.is_connected:
            self.is_connected = True
            self.logger.info("Verbunden, regestriere Plugins...")
            self.register_mods()
            self._client.subscribe("broadcast/updateAll")
            self._client.message_callback_add("broadcast/updateAll", self.reSendStates)
        else:
            self.logger.warning("Nicht verbunden, Plugins werden nicht regestriert.")

    def _shutdown(self):
        pass

    def shutdown(self):
        self.disable_mods()
        if self._client is not None:
            self._client.disconnect()
        self.scheduler_event.set()
        self.config.save()

