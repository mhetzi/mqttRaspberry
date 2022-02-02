#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import getopt
import sys
import logging
import threading
import time
import Tools.PluginManager as pman
import Tools.Config as tc
import signal
import ctypes
import datetime
from pathlib import Path
import faulthandler

LIB = 'libcap.so.2'
try:
    libcap = ctypes.CDLL(LIB)
except OSError:
    print(
        'Library {} not found. Unable to set thread name.'.format(LIB)
    )
else:
    def _name_hack(self):
        # PR_SET_NAME = 15
        libcap.prctl(15, self.name.encode())
        threading.Thread._bootstrap_original(self)

    threading.Thread._bootstrap_original = threading.Thread._bootstrap
    threading.Thread._bootstrap = _name_hack


try:
    import setproctitle
except ImportError as ie:
    from Tools import error as err
    try:
        err.try_install_package('setproctitle', throw=ie, ask=False)
    except err.RestartError:
        try:
            import setproctitle
        except:
            pass
    except:
        pass

class Launcher:

    pm = None
    reload_event = threading.Event()
    reload = True
    reconnect_time = 0.1
    mqtt_client = None
    faultFile = None
    _logFile = None
    

    def __init__(self):
        log = logging.getLogger("Launch")
        log.setLevel(logging.DEBUG)
        # fh = logging.FileHandler('spam.log')
        # fh.setLevel(logging.DEBUG)
        # create console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        # create formatter and add it to the handlers
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)8s - %(message)s')
        # fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        # add the handlers to the logger
        # logger.addHandler(fh)
        log.addHandler(ch)
        self._ch = ch
        self._log = log
        self.config = None
        self.abrt_file = None
        signal.signal(signal.SIGTERM, self.exit)

        try:
            import setproctitle
            setproctitle.setproctitle("mqttScripts")
        except:
            log.exception("Process Name change failed!")

    def pm_reload(self):
        self.reload = True
        self.reload_event.set()

    def relaunch(self):
        if self.pm is not None:
            self.pm.shutdown()

        self.pm = pman.PluginManager(self._log, self.config)
        self.config.pre_reload = self.pm.shutdown
        self.config.post_reload = self.pm_reload
        self.mqtt_client = None

        threading.current_thread().name = "Main/MQTT"

        try:
            try:
                if self.config.get("ptvsd/enabled", False):
                    import ptvsd
                    ptvsd.enable_attach(address=("0.0.0.0", 3000)) 
            except:
                self._log.info("Remote Debugging (ptvsd) nicht verfügbar")
            self.pm.needed_plugins()
            self.mqtt_client, deviceID = self.pm.start_mqtt_client()
            self.pm.enable_mods()
            while True:
                try:
                    self.mqtt_client.loop_forever(timeout=30, retry_first_connection=True)
                    break
                except ConnectionRefusedError:
                    self.pm.start_mqtt_client()
                except Exception as e:
                    raise e
            return True
        except ConnectionRefusedError:
            self._log.info("Server hat die Verbindung nicht angenommen. Läuft die Server Anwendung?")
            self.reload_event.set()
            self._log.info("Warte {} Sekunden und werde dann versuchen neu zu verbinden.".format(self.reconnect_time))
            time.sleep(self.reconnect_time)
            self.reconnect_time = self.reconnect_time * 2 if self.reconnect_time < 100 else 150
            self.reload = True
        except ConnectionResetError:
            self._log.warning("Server hat die Verbindung zurückgesetzt. Alles richtig konfiguriert?")
        except KeyboardInterrupt:
            self._log.info("Habe verstanden. Werde mich beenden. Aufräumen...")
            self.exit(0,0)
        except tc.NoClientConfigured:
            self._log.error("Es wurde kein Server konfiguriert. Bitte die einstellungen unter CLIENT abändern.")
            self.reload_event.set()
            self.pm.shutdown()
        except Exception:
            self._log.exception("MQTT Hauptthread gestorben")
            self.reload_event.set()
            self.pm.shutdown()
        return False

    def launch(self):
        prog_args = sys.argv[1:]
        t_args = prog_args.copy()

        configPath = "~/.config/mqttra.config"
        auto_reload_config = True

        logPath = None

        door_hall_calib_mode = False
        conf_all_mods = False
        systemd = False
        debug = False

        while True:
            try:
                opts, args = getopt.gnu_getopt(t_args, "h?sdc:l:",
                                               ["help", "config=", "systemd", "no-reload", "door-hall-calibnoise", "configure-all-plugins", "log=", "debug"])
                break
            except getopt.error as e:
                opt = e.msg.replace("option ", "").replace(" not recognized", "")
                t_args.remove(opt)

        for opt, arg in opts:
            if opt == "-c" or opt == "--config":
                configPath = arg
            elif opt == "-s" or opt == "--systemd":
                systemd = True
                self._log.info("OK Systemflag gefunden. Bin ein Service.")
            elif opt == "--no-reload":
                auto_reload_config = False
            elif opt == "-?" or opt == "-h" or opt == "help":
                self._log.info("""
                                        ============ HILFE ============
                    -c --config             Konfigurations Datei angeben (Standartpfad ~/.config/mqttra.config)
                    -s --systemd            Verändert die logger Formatierung damit sie zu systemd passt, verhindert Fragen über installieren von pip Packeten
                    --no-reload             Neuladen des Server bei externen änderungen der Konfigurationsdatei ausschalten
                    -? -h --help            Diese Nachricht anzeigen
                    --door-hall-calibnoise  Noise Level von dem Halleffekt Sensor von Raspberry Tor ermitteln
                    --configure-all-plugins Alle Plugins Konfigureieren, wird eines Konfiguriert wird es
                                            beim nächsten Start automatisch geladen.
                    --log                   Log in Datei speichern und nicht in der Konsole ausgeben
                    --debug                 Zeit im log anzeigen, überschreibt systemd logger format
                """)
                return
            elif opt == "--door-hall-calibnoise":
                door_hall_calib_mode = True
            elif opt == "--configure-all-plugins":
                conf_all_mods = True
            elif opt == "--log":
                try:
                    if arg is not None:
                        p = Path(arg)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        self._logFile = p.open(mode="wt", buffering=4096, encoding="utf-8")
                        self._log.info("Logger wird jetzt auf Logfile umgestellt...")
                        if self._ch.setStream(self._logFile) is None:
                            self._log.warning("Umstellen Fehlgeschlagen!")
                except Exception as e:
                    print("Kann logfile nicht erstellen! {}".format(e))
            elif opt == "-d" or opt == "--debug":
                debug = True
                pass

        self.config = tc.config_factory(configPath, logger=self._log, do_load=True, filesystem_listen=auto_reload_config)
        from Tools import _std_dev_info
        import Tools.Autodiscovery as ad
        devInfo = _std_dev_info.DevInfoFactory.build_std_device_info(self._log.getChild("std_dev"))
        ad.Topics.set_standard_deviceinfo(devInfo)

        try:
            import Tools.error as err
            err.set_system_mode(systemd)
        except:
            pass
        
        if door_hall_calib_mode:
            self._log.info("Ermittle noise für Halleffekt Sensor (Raspberry Tor)...")
            import Mods.DoorOpener.calibrate as calib
            calib.Calibrate.run_calibration(conf=self.config, logger=self._log)
            self._log.info("Noise ermittelt. Beende anwendung.")
            return

        elif conf_all_mods:
            pm = pman.PluginManager(self._log, self.config)
            pm.run_configurator()
            self.config.save()
            i = input("Beenden= [N/y]")
            if i == "y" or i == "Y":
                return

        

        configFolder = Path(configPath).parent
        failFile = configFolder.joinpath("fails")
        failFile.mkdir(exist_ok=True)
        failFile = failFile.joinpath(
            "{}.log".format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        self.faultFile = failFile.open('w')
        faulthandler.enable(file=self.faultFile, all_threads=True)

        formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        if debug or not systemd:
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)8s - %(message)s')

        self._ch.setFormatter(formatter)

        self.relaunch()

    def exit(self, signum, frame):
        self.reload_event.set()
        self.reload = False
        self._log.info("Zeit zum Begraben gehn...\n PluginManager wird heruntergefahren...")
        self.pm.shutdown()
        self._log.info("MQTT Thread wird gestoppt...")
        self.mqtt_client.loop_stop()
        self._log.info("Config wird entladen...")
        self.config.save()
        self.config.stop()
        self._log.info("Beende mich...")
        if faulthandler.is_enabled():
            faulthandler.disable()
        if self.faultFile is not None and not self.faultFile.closed:
            self.faultFile.close()
        exit(0)


if __name__ == "__main__":
    l = Launcher()
    l.launch()
