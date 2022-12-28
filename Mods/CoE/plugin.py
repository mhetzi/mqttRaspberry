# -*- coding: utf-8 -*-
import datetime
import json
import logging
import threading
import time
import math
from typing import Union

import paho.mqtt.client as mclient
import schedule

import Tools.Autodiscovery as autodisc
import Tools.PluginManager
import Tools.ResettableTimer as rTimer
from Tools.Config import BasicConfig, PluginConfig
from Tools.Devices import Sensor, BinarySensor

try:
    import bitstring
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('bitstring', throw=ie, ask=False)
    except err.RestartError:
        import bitstring

from Mods.CoE.coe_lib.ChannelRegestry import CanNodeReg, AnalogChannels, DigitalChannels, ANALOG_CHANNEL_TYPE, DIGITAL_CHANNEL_TYPE
from Mods.CoE.coe_lib.PacketReader import PacketReader
from Mods.CoE.coe_lib import Datatypes
from Mods.CoE.coe_lib import Message
from Mods.CoE import getConfigKey
from Mods.CoE.Devices import CoeOutSwitch, CoeOutNumber
from Mods.CoE.udp_sender import UDP_Sender
from Mods.CoE import get_sensor_class_from_mt

class TaCoePlugin(Tools.PluginManager.PluginInterface):
    __slots__ = ("_udp", "_timer", "_from_cmi_analog", "_from_cmi_digital", "sensors", "_via_devices", "_switches", "_to_cmi_digital", "_to_cmi_analog", "_upd_senders", "_last_online")

    _udp: PacketReader | None
    _timer: schedule.Job
    _via_devices: dict[str, autodisc.DeviceInfo]
    _switches: dict[str, CoeOutSwitch]
    _upd_senders: dict[str, UDP_Sender]
    _last_online: dict[str, datetime.datetime]

    @staticmethod
    def get_device_online_topic(addr: str):
        return f"device_online/TA_CMI_{addr}/online"


    def __init__(self, client: mclient.Client, opts: BasicConfig, logger: logging.Logger, device_id: str):
        self._client = client
        self._config = PluginConfig(opts, getConfigKey())
        self._logger = logger.getChild(getConfigKey())
        self._device_id = device_id
        self._timer = schedule.every(5).minutes.do(self.check_online_status)
        self._udp = None
        self._upd_senders = {}
        self._last_online = {}

        self._from_cmi_digital: dict[int, DigitalChannels] = {}
        self._from_cmi_analog: dict[int, AnalogChannels] = {}
        self._to_cmi_digital: dict[str, DigitalChannels] = {}
        self._to_cmi_analog: dict[str, AnalogChannels] = {}

        self._switches = {}
        self.sensors: dict[str, Sensor.Sensor | BinarySensor.BinarySensor] = {}            

    def set_pluginManager(self, pm: Tools.PluginManager.PluginManager):
        self._pluginManager = pm

    def sendStates(self):
        for sensor in self.sensors.values():
            sensor.resend()

    def register_switches(self, cdata: dict, cmi: str, dev: autodisc.DeviceInfo):
        for idx in range(0, len(cdata["switches"])):
            s = cdata["switches"][idx]
            sw = CoeOutSwitch(
                logger=self._logger,
                pman=self._pluginManager,
                name=s["name"],
                node=s["node"],
                channel= s["channel"],
                device=dev,
                udp_sender=self._upd_senders[f"{cmi}_D"]
            )

            def update_last_state(b:bool):
                self._config["CMIs"][cmi]["switches"][idx]["last"] = b
                
            sw._call_is_on_off = update_last_state

            if s.get("last", False):
                sw.turnOn()
            else:
                sw.turnOff()
            sw.register()

    def register_analog_outs(self, cdata: dict, cmi: str, dev: autodisc.DeviceInfo):
        for idx in range(0, len(cdata["analog"])):
            s = cdata["analog"][idx]
            sw = CoeOutNumber(
                logger=self._logger,
                pman=self._pluginManager,
                name=s["name"],
                node=s["node"],
                channel= s["channel"],
                device=dev,
                udp_sender=self._upd_senders[f"{cmi}_A"],
                measure_type=Datatypes.MeasureType(s["mt"])
            )
            sw.max = 110
            sw.min = -50
            sw.step = 0.5

            def update_last_state(n: float):
                self._config["CMIs"][cmi]["analog"][idx]["last"] = n
                
            sw._call_is_number = update_last_state

            sw.state(self._config["CMIs"][cmi]["analog"][idx]["last"])
            sw.register()


    def register(self, wasConnected=False):
        if self._udp is None:
            self._udp = PacketReader(listen_addr="0.0.0.0", listen_port=5441, logger=self._logger, looper=None)
            self._udp.on_message = self.on_coe_message
            self._udp.start()

            if self._config.get("CMIs", None) is None:
                self._config["CMIs"] = {}
            cmis: dict[str, dict] = self._config["CMIs"]
            self._via_devices = {}

            for cmi, cdata in cmis.items():
                reg = CanNodeReg()
                self._to_cmi_digital[cmi] = DigitalChannels(reg)
                self._to_cmi_analog[cmi] = AnalogChannels(reg)
                self._upd_senders[f"{cmi}_D"] = UDP_Sender(self._to_cmi_digital[cmi], cmi, 5441, self._logger)
                self._upd_senders[f"{cmi}_A"] = UDP_Sender(self._to_cmi_analog[cmi],  cmi, 5441, self._logger)

                dev = autodisc.DeviceInfo()
                dev.IDs.append(f"TACMIIP: {cmi}")
                dev.mfr = "Technische Alternative RT GmbH, Amaliendorf"
                dev.model = "CMI"
                dev.name = f"CMI: {cmi}"
                dev.via_device = autodisc.Topics.get_std_devInf().IDs[0]
                self._via_devices[cmi] = dev
                if not isinstance(cdata.get("switches", None), list):
                    cdata["switches"] = []
                self.register_switches(cdata, cmi, dev)
                if not isinstance(cdata.get("analog", None), list):
                    cdata["analog"] = []
                self.register_analog_outs(cdata, cmi, dev)
                

        if self._config.get(f"{getConfigKey()}/deregister", False):
            pass
    
    def stop(self):
        if self._udp is not None:
            self._udp.stop()
        for sender in self._upd_senders.values():
            sender.stop()

    def new_binary_sensor(self, addr: str, channel: DIGITAL_CHANNEL_TYPE) -> BinarySensor.BinarySensor:
        dev = autodisc.DeviceInfo()
        dev.IDs = [f"D_{addr}_{channel[0]}"]
        dev.via_device = self._via_devices[addr].IDs[0]
        dev.name = f"DNode: {channel[0]}"
        dev.mfr = "TA"
        dev.sw_version = "1.0"
        dev.model = "CoE Digital"

        bs = BinarySensor.BinarySensor(
            logger=self._logger,
            pman=self._pluginManager,
            name=f"DInput: {channel[0]}_{channel[1]}",
            binary_sensor_type=BinarySensor.BinarySensorDeviceClasses.GENERIC_SENSOR,
            device=dev,
            unique_id=f"{dev.IDs[0]}_{channel[0]}_{channel[1]}",
            ava_topic=TaCoePlugin.get_device_online_topic(addr),
            value_template="{{ value_json.value }}",
            json_attributes=True
        )
        return bs

    def new_analog_sensor(self, addr: str, channel: ANALOG_CHANNEL_TYPE) -> Sensor.Sensor:
        dev = autodisc.DeviceInfo()
        dev.IDs = [f"S_{addr}_{channel[0]}"]
        dev.via_device = self._via_devices[addr].IDs[0]
        dev.name = f"ANode: {channel[0]}"
        dev.mfr = "TA"
        dev.sw_version = "1.0"
        dev.model = "CoE Analog"

        st = get_sensor_class_from_mt(channel[3])

        bs = Sensor.Sensor(
            log=self._logger,
            pman=self._pluginManager,
            name=f"AInput: {channel[0]}_{channel[1]}",
            device=dev,
            unique_id=f"{dev.IDs[0]}_{channel[0]}_{channel[1]}",
            sensor_type=st,
            ava_topic=TaCoePlugin.get_device_online_topic(addr),
            value_template="{{ value_json.value }}",
            json_attributes=True,
            measurement_unit=channel[3].getUnit()
        )
        return bs

    def _on_coe_analog_change_submitted(self, addr: str, channel: ANALOG_CHANNEL_TYPE):
        sens_id = f"{addr}:A_{channel[0]}_{channel[1]}"
        sens = self.sensors.get(sens_id, None)
        if sens is None or not isinstance(sens, Sensor.Sensor):
            sens = self.new_analog_sensor(addr, channel)
            self.sensors[sens_id] = sens
            sens.register()
        sens.state( {
                "value": channel[2],
                "node": channel[0],
                "chan": channel[1]+1,
                "attribution": "TA RT GmbH, Amaliendorf"
            } )

    def _on_coe_digital_change_submitted(self, addr: str, channel: DIGITAL_CHANNEL_TYPE):
        sens_id = f"{addr}:D_{channel[0]}_{channel[1]}"
        sens = self.sensors.get(sens_id, None)
        if sens is None or not isinstance(sens, BinarySensor.BinarySensor):
            sens = self.new_binary_sensor(addr, channel)
            self.sensors[sens_id] = sens
            sens.register()
        sens.turn( {
                "value": 1 if channel[2] else 0,
                "node": channel[0],
                "chan": channel[1]+1,
                "attribution": "TA RT GmbH, Amaliendorf"
            } )

    def on_coe_message(self, msg: Message.AnalogMessage | Message.DigitalMessage):
        self._last_online[msg.ip] = datetime.datetime.now()

        if isinstance(msg, Message.AnalogMessage):
            channel = self._from_cmi_analog.get(msg.canNode, None)
            if channel is None:
                channel = AnalogChannels(None)
                channel.on_changed_value = self._on_coe_analog_change_submitted
                self._from_cmi_analog[msg.canNode] = channel
            channel.submitMessage(msg)
            return
        if isinstance(msg, Message.DigitalMessage):
            channel = self._from_cmi_digital.get(msg.canNode, None)
            if channel is None:
                channel = DigitalChannels(None)
                channel.on_changed_value = self._on_coe_digital_change_submitted
                self._from_cmi_digital[msg.canNode] = channel
            channel.submitMessage(msg)
            return
        

    def check_online_status(self):
        # !!!!!!!!
        #TODO CAN Timeout implementieren
        # !!!!!!!!!
        for addr, tim in self._last_online.items():
            online = "offline"
            if tim is None or tim < (datetime.datetime.now() - datetime.timedelta(minutes=10)):
                online = "online"
            topic = TaCoePlugin.get_device_online_topic(addr)
            self._client.publish(topic, payload=online, retain=True)

