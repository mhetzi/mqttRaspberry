"""
Push SignalStrength from ModemManager

Handling Stromgmode of Polkit in Debian
wget download.tuxfamily.org/gsf/patch/modem-manager-gui.pkla
sudo cp modem-manager-gui.pkla /var/lib/polkit-1/localauthority/10-vendor.d/

from pydbus import SystemBus
bus = SystemBus()
proxy = bus.get(".ModemManager1", "/org/freedesktop/ModemManager1/Modem/0")

signal_api = proxy["org.freedesktop.ModemManager1.Modem.Signal"]
signal_api.Setup(60) # Signalstatus alle 60 Sekunden aktualisieren
signal_api.Lte #etc für genaue 

simple_api = proxy["org.freedesktop.ModemManager1.Modem.Simple"]
simple_api.GetStatus() #SignalStregth in %

sms_api = proxy["org.freedesktop.ModemManager1.Modem.Messaging"]
from pydbus import Variant
sms_path = sms_api.Create( {"Number": Variant('s', "06606431450"), "Text": Variant('s', "Test")})
proxy_sms = bus.get(".ModemManager1", sms_path)
test_sms = proxy_sms["org.freedesktop.ModemManager1.Sms"]
test_sms.Send()
sms_api.Delete(sms_path)

"""

DEPENDENCIES_LOADED = True

try:
    from pydbus import SystemBus
except ImportError as ie:
    DEPENDENCIES_LOADED = False

import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import logging
import schedule
import json
from Tools import PluginManager

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "ModemManager"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        try:
            from pydbus import SystemBus
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('pydbus', throw=ie, ask=False)
        return ModemManagerClient(opts, logger.getChild("ModemManager"), device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        ModemManagerClientConfig().configure(conf, logger.getChild("ModemManager"))

    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            from pydbus import SystemBus
        except ImportError as ie:
            return ["pydbus"]
        return []


if DEPENDENCIES_LOADED:

    class ModemManagerDbus:

        def on_removed(self, id: str):
            pass

        def on_added(self, id: str, proxy):
            pass

        def new_signal(self, id: str, signal: dict, signal_raw: dict, state: dict):
            pass

        def __init__(self, logger: logging.Logger):
            self.__proxys = {}
            self.__paths = {}
            self.__signal_schedules = {}
            self.signal_refresh_seconds = None
        
        def startDbus(self):
            self.bus = SystemBus()
            self.manager = self.bus.get("org.freedesktop.ModemManager1")
            for s in self.getAllModems():
                self.buildModem(s)
            self.manager.InterfacesAdded.connect( lambda path, x: self.buildModem(path) )
            self.manager.InterfacesRemoved.connect( lambda path, x: self.removeModem(path) )
        
        def stopDbus(self):
            paths = self.__paths.values()
            for path in paths:
                self.removeModem(path)

        def getAllModems(self) -> []:
            objects = self.manager.GetManagedObjects()
            return objects.keys()
        
        def buildModem(self, path:str):
            proxy = self.bus.get(".ModemManager1", path)

            signal_api = proxy["org.freedesktop.ModemManager1.Modem.Signal"]
            signal_api.Setup(60) # Signalstatus alle 60 Sekunden aktualisieren

            id = proxy.DeviceIdentifier
            self.__proxys[id] = proxy
            self.__paths[id]  = path
            self.on_added(id, proxy)

            self.__signal_schedules[id] = schedule.every(self.signal_refresh_seconds).seconds.do(lambda: self.updateSignal(id))
            
        
        def removeModem(self, path: str):
            id = None
            for key in self.__paths:
                if self.__paths[key] == path:
                    id = key
                    break
            self.on_removed(id)
            del self.__paths[id]
            del self.__proxys[id]
            schedule.cancel_job(self.__signal_schedules[id])
            del self.__signal_schedules[id]
        
        def _getIndexFrom(self, tech: str, type: str, dBm: int):
            if (tech == "LTE"):
                if type == "RSRP":
                    if dBm >= -80: return "Excellent"
                    elif -80 > dBm > -90: return "Good"
                    elif -90 > dBm > -100: return "Meh"
                    else: return "No Connection"
                elif type == "RSRQ":
                    if dBm >= -10: return "Excellent"
                    elif -10 > dBm > -15: return "Good"
                    elif -15 > dBm > -20: return "Meh"
                    else: return "No Connection"
                elif type == "SINR":
                    if dBm >= 20: return "Excellent"
                    elif 13 < dBm < 20: return "Good"
                    elif 0 < dBm < 13: return "Meh"
                    else: return "No Connection"
                elif type == "RSSI":
                    if dBm >= -65: return "Excellent"
                    elif -65 > dBm > -75: return "Good"
                    elif -75 > dBm > -85: return "Naja"
                    elif -85 > dBm > -95: return "Meh :("
                    else: return "No Connection"
            elif tech == "GSM" or (tech == "3G" and type == "RSSI"):
                if dBm >= -70: return "Excellent"
                elif -70 > dBm > -85: return "Good"
                elif -86 > dBm > -100: return "Naja"
                elif -100 > dBm > -110: return "Meh :("
                else: return "No Connection"
            elif tech == "3G":
                if type == "ECIO":
                    if dBm >= 6: return "Excellent"
                    elif -7 > dBm > -10: return "Good"
                    elif -11 > dBm > -20: return "Meh"
                if type == "RCSP":
                    if dBm >= -60: return "Excellent"
                    elif -60 > dBm > -75: return "Good"
                    elif -75 > dBm > -85: return "Naja"
                    elif -85 > dBm > -95: return "Meh :("
                    elif -95 > dBm > -124: return "Richtig schlecht"
                    else: return "No Connection"
            return "NotImplemented"

        def updateSignal(self, id):
            signal_stat = {}
            signal_raw = {}
            signal_raw = {"Refreshrate": self.signal_refresh_seconds}
            proxy = self.__proxys[id]
            simple_api = proxy["org.freedesktop.ModemManager1.Modem.Simple"]
            signal_api = proxy["org.freedesktop.ModemManager1.Modem.Signal"]
            if signal_api.Lte != {}:
                lte = signal_api.Lte
                signal_stat["Art"] = "LTE (4G)"
                signal_raw["Art"] = "LTE (4G)"
                signal_stat["RSRP"] = self._getIndexFrom("LTE", "RSRP", lte["rsrp"])
                signal_stat["RSRQ"] = self._getIndexFrom("LTE", "RSRQ", lte["rsrq"])
                signal_stat["SINR"] = self._getIndexFrom("LTE", "SINR", lte["snr"])
                signal_stat["RSSI"] = self._getIndexFrom("LTE", "RSSI", lte["rssi"])

                signal_raw["RSRP"] = lte["rsrp"]
                signal_raw["RSRQ"] = lte["rsrq"]
                signal_raw["SINR"] = lte["snr"]
                signal_raw["RSSI"] = lte["rssi"]
            elif signal_api.Gsm != {}:
                gsm = signal_api.Gsm
                signal_stat["Art"] = "GSM (2G)" 
                signal_stat["RSSI"] = self._getIndexFrom("GSM", "RSSI", gsm["rssi"])

                signal_raw["Art"] = "GSM (2G)"
                signal_raw["RSSI"] = gsm["rssi"]
            elif signal_api.Umts != {}:
                umts = signal_api.Umts
                signal_stat["Art"]  = "UMTS (3G)"
                signal_stat["RSSI"] = self._getIndexFrom("3G", "RSSI", umts["rssi"])
                try:
                    signal_stat["RSCP"] = self._getIndexFrom("3G", "RSCP", umts["rscp"])
                except: pass
                try:
                    signal_stat["ECIO"] = self._getIndexFrom("3G", "ECIO", umts["ecio"])
                except: pass

                signal_raw["Art"]  = "UMTS (3G)"
                signal_raw["RSSI"] = umts["rssi"]
                try:
                    signal_raw["RSCP"] = umts["rscp"]
                except: pass
                try:
                    signal_raw["ECIO"] = umts["ecio"]
                except: pass
            elif signal_api.Cdma != {}:
                signal_stat["Art"]  = "CDMA (2G)"
            elif signal_api.Evdo != {}:
                signal_stat["Art"]  = "EVDO (3G)"
            self.new_signal(id, signal_stat, signal_raw, simple_api.GetStatus())

        def sendSms(self, id:str, nummer: str, message: str):
            proxy = self.__proxys[id]
            sms_api = proxy["org.freedesktop.ModemManager1.Modem.Messaging"]
            from pydbus import Variant
            sms_path = sms_api.Create( {"Number": Variant('s', nummer), "Text": Variant('s', message)})
            proxy_sms = self.bus.get(".ModemManager1", sms_path)
            test_sms = proxy_sms["org.freedesktop.ModemManager1.Sms"]
            test_sms.Send()
            sms_api.Delete(sms_path)

    class ModemManagerClient(PluginManager.PluginInterface):
        
        def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
            self.__dbus = ModemManagerDbus(logger.getChild("DBUS"))
            self.__dbus.on_removed = self.on_removed
            self.__dbus.on_added   = self.on_added
            self.__dbus.new_signal = self.new_signal
            self.__dbus.signal_refresh_seconds = opts["ModemManager/SigSecs"]
            
            self._config = opts
            self.__logger = logger

            self._raw_last = ""
            self._named_last = ""
            self._state_last = ""
            self.first_id = None

        def on_removed(self, id: str):
            pass

        def on_added(self, id: str, proxy):
            self.register_raw(id)
            self.register_quality(id)
            self.register_named(id)
            if self.first_id is None:
                self.first_id = id
                if self._config.get("ModemManager/SMS/notify_reboot", False):
                    self.__dbus.sendSms(id, self._config.get("ModemManager/SMS/nummer", None), "Raspberry wurde neugestartet")
        
        def register_raw(self, id):
            # Registriere Modem Raw
            unique_id = "sensor.modemmanager-{}.{}.raw".format(
                id,
                self._config.get("ModemManager/name", "ModemManager")
            )
            self._raw_topic = self._config.get_autodiscovery_topic(
                autodisc.Component.SENSOR,
                "{}r".format(self._config.get("ModemManager/name", "ModemManager")),
                autodisc.SensorDeviceClasses.GENERIC_SENSOR
            )
            if self._raw_topic.config is not None:
                self.__logger.info("Werde AutodiscoveryTopic senden mit der Payload: {}".format(
                    self._raw_topic.get_config_payload("{}r".format(self._config.get("ModemManager/name", "ModemManager")), "dBm", unique_id=unique_id, value_template="{{ value_json.RSSI }}", json_attributes=True))
                    )
                self._pluginManager._client.publish(
                    self._raw_topic.config,
                    self._raw_topic.get_config_payload(
                        "{}r".format(self._config.get("ModemManager/name", "ModemManager")),
                        "dBm",
                        unique_id=unique_id, value_template="{{ value_json.RSSI }}", json_attributes=True),
                    retain=True
                )
        
        def register_named(self, id):
            # Registriere Modem Raw
            unique_id = "sensor.modemmanager-{}.{}.named".format(
                id,
                self._config.get("ModemManager/name", "ModemManager")
            )
            self._named_topic = self._config.get_autodiscovery_topic(
                autodisc.Component.SENSOR,
                "{}n".format(self._config.get("ModemManager/name", "ModemManager")),
                autodisc.SensorDeviceClasses.GENERIC_SENSOR
            )
            if self._named_topic.config is not None:
                self.__logger.info("Werde AutodiscoveryTopic senden mit der Payload: {}".format(
                    self._named_topic.get_config_payload("{}n".format(self._config.get("ModemManager/name", "ModemManager")), "", unique_id=unique_id, value_template="{{ value_json.RSSI }}", json_attributes=True))
                    )
                self._pluginManager._client.publish(
                    self._named_topic.config,
                    self._named_topic.get_config_payload(
                        "{}n".format(self._config.get("ModemManager/name", "ModemManager")),
                        "",
                        unique_id=unique_id, value_template="{{ value_json.RSSI }}", json_attributes=True),
                    retain=True
                )
        
        def register_quality(self, id):
            # Registriere Modem Raw
            unique_id = "sensor.modemmanager-{}.{}.q".format(
                id,
                self._config.get("ModemManager/name", "ModemManager")
            )
            self._quality_topic = self._config.get_autodiscovery_topic(
                autodisc.Component.SENSOR,
                "{}q".format(self._config.get("ModemManager/name", "ModemManager")),
                autodisc.SensorDeviceClasses.GENERIC_SENSOR
            )
            if self._quality_topic.config is not None:
                self.__logger.info("Werde AutodiscoveryTopic senden mit der Payload: {}".format(
                    self._quality_topic.get_config_payload("{}q".format(self._config.get("ModemManager/name", "ModemManager")), "%", unique_id=unique_id, value_template="{{ value_json.precentage }}", json_attributes=True))
                    )
                self._pluginManager._client.publish(
                    self._quality_topic.config,
                    self._quality_topic.get_config_payload(
                        "{}q".format(self._config.get("ModemManager/name", "ModemManager")),
                        "%",
                        unique_id=unique_id, value_template="{{ value_json.precentage }}", json_attributes=True),
                    retain=True
                )

        def new_signal(self, id: str, signal: dict, signal_raw: dict, state: dict):
            signal_quality = {
                "precentage": state["signal-quality"][0],
                "Technologie": signal_raw["Art"]
            }
            new_quality = json.dumps(signal_quality)
            new_named = json.dumps(signal)
            raw_new = json.dumps(signal_raw)

            if new_quality != self._state_last:
                self._pluginManager._client.publish(self._quality_topic.state, new_quality)
            if new_named != self._named_last:
                self._pluginManager._client.publish(self._named_topic.state, new_named)
            if raw_new != self._raw_last:
                self._pluginManager._client.publish(self._raw_topic.state, raw_new)

            self._state_last = new_quality
            self._named_last = new_named
            self._raw_last = raw_new

        def set_pluginManager(self, pm):
            self._pluginManager = pm

        def register(self):
            self.__dbus.startDbus()

        def stop(self):
            self.__dbus.stopDbus()


class ModemManagerClientConfig:
    def __init__(self):
        pass

    def configure(self, conf: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools as cit
        conf["ModemManager/SigSecs"] = cit.get_number_input("Aktualisierung alle Sekunden? ", 60)
        conf["ModemManager/SMS/nummer"] = cit.get_input("SMS Empfänger Nummer", require_val=False)
        conf["ModemManager/SMS/notify_reboot"] = cit.get_bool_input("Bei Neustart SMS Senden", True)
