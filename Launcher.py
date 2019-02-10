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

class Launcher:

    pm = None
    reload_event = threading.Event()
    reload = True
    reconnect_time = 0.1
    mqtt_client = None

    def build_std_device_info(self):
        import sys
        import subprocess
        import Tools.Autodiscovery as ad
        import re
        import platform
        devInf = ad.DeviceInfo()
        devInf.name = platform.node()
        if sys.platform == "linux":
            gitVer = ""
            osRelease = ""
            try:
                gitVerProc = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True)
                gitVer = gitVerProc.stdout
            except:
                self._log.exception("Git ver")
            try:
                osReleaseFile = open("/etc/os-release", "r")
                osReleaseBuffer = osReleaseFile.read()
                osRelease = re.findall('PRETTY_NAME=\".*?\"', osReleaseBuffer)[0]
            except:
                self._log.exception("os-release")

            devInf.sw_version = "OS; {}, APP: {}".format(osRelease, gitVer)

            try:
                rpi_model = open("/sys/firmware/devicetree/base/model", "r").read()
                devInf.model = rpi_model
                devInf.mfr = "Raspberry"
            except:
                self._log.exception("rpiModel")

            try:
                ip_link_proc = subprocess.run(["ip", "link"], capture_output=True)
                for MAC in re.findall("..:..:..:..:..:..", ip_link_proc.stdout):
                    if MAC != "ff:ff:ff:ff:ff:ff" and MAC != "00:00:00:00:00:00":
                        devInf.IDs.append(MAC)
            except:
                self._log.exception("IDs")
        ad.Topics.set_standard_deviceinfo(devInf)


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
        signal.signal(signal.SIGTERM, self.exit)

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

        try:
            self.pm.needed_plugins()
            self.mqtt_client, deviceID = self.pm.start_mqtt_client()
            self.pm.enable_mods()
            self.mqtt_client.loop_start()
            self.mqtt_client._thread.join()
        except ConnectionRefusedError:
            self._log.info("Server hat die Verbindung nicht angenommen. Läuft die Server Anwendung?")
            self.reload_event.set()
            self.pm.shutdown()
            if self.reconnect_time < 100:
                self._log.info("Warte {} Sekunden und werde dann versuchen neu zu verbinden.".format(self.reconnect_time))
                time.sleep(self.reconnect_time)
                self.reconnect_time *= 2
                self.reload = True
            else:
                self._log.warning("Verbindung zu oft Fehlgeschlagen!. Gehe mich begraben...")
        except ConnectionResetError:
            self._log.warning("Server hat die Verbindung zurückgesetzt. Alles richtig konfiguriert?")
        except KeyboardInterrupt:
            self._log.info("Habe verstanden. Werde mich beenden. Aufräumen...")
            self.exit(0,0)
        except tc.NoClientConfigured:
            self._log.error("Es wurde kein Server konfiguriert. Bitte die einstellungen unter CLIENT abändern.")
            self.reload_event.set()
            self.pm.shutdown()
        except Exception as x:
            self._log.exception("MQTT Hauptthread gestorben")
            self.reload_event.set()
            self.pm.shutdown()

    def launch(self):
        prog_args = sys.argv[1:]
        t_args = prog_args.copy()

        configPath = "~/.config/mqttra.config"
        auto_reload_config = True

        door_hall_calib_mode = False
        conf_all_mods = False

        while True:
            try:
                opts, args = getopt.gnu_getopt(t_args, "h?sc:",
                                               ["help", "config=", "systemd", "no-reload", "door-hall-calibnoise", "configure-all-plugins"])
                break
            except getopt.error as e:
                opt = e.msg.replace("option ", "").replace(" not recognized", "")
                t_args.remove(opt)

        for opt, arg in opts:
            if opt == "-c" or opt == "--config":
                configPath = arg
            elif opt == "-s" or opt == "--system":
                self._ch.setFormatter(logging.Formatter('%%(name)s - %(levelname)s - %(message)s'))
            elif opt == "--no-reload":
                auto_reload_config = False
            elif opt == "-?" or opt == "-h" or opt == "help":
                self._log.info("""
                                        ============ HILFE ============
                    -c --config             Konfigurations Datei angeben (Standartpfad ~/.config/mqttra.config)
                    -s --system             Verändert die logger Formatierung damit sie zu systemd passt
                    --no-reload             Neuladen des Server bei externen änderungen der Konfigurationsdatei ausschalten
                    -? -h --help            Diese Nachricht anzeigen
                    --door-hall-calibnoise  Noise Level von dem Halleffekt Sensor von Raspberry Tor ermitteln
                    --configure-all-plugins Alle Plugins Konfigureieren, wird eines Konfiguriert wird es
                                            beim nächsten Start automatisch geladen.
                """)
                return
            elif opt == "--door-hall-calibnoise":
                door_hall_calib_mode = True
            elif opt == "--configure-all-plugins":
                conf_all_mods = True

        self.config = tc.config_factory(configPath, logger=self._log, do_load=True, filesystem_listen=auto_reload_config)
        self.build_std_device_info()

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

        self.reload_event.set()

        while self.reload_event.wait(30):
            self.reload_event.clear()
            if self.reload:
                self.reload = False
                self.relaunch()
            else:
                return

    def exit(self, signum, frame):
        self._log.info("Zeit zum Begraben gehn...\n PluginManager wird heruntergefahren...")
        self.pm.shutdown()
        self._log.info("MQTT Thread wird gestoppt...")
        self.mqtt_client.loop_stop()
        self._log.info("Beende mich...")
        exit(0)


if __name__ == "__main__":
    l = Launcher()
    l.launch()
