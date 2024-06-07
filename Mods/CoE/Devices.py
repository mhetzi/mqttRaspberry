from Tools.Devices.Switch import Switch
from Tools.Devices.Number import Number
from Tools.Devices.Sensor import SensorDeviceClasses
from logging import Logger
from Tools.PluginManager import PluginManager
from Tools.Autodiscovery import DeviceInfo
from Mods.CoE.coe_lib.ChannelRegestry import DigitalChannels, MeasureType
from Mods.CoE.coe_lib.ChannelRegestry import AnalogChannels
from Mods.CoE.udp_sender import UDP_Sender
from Mods.CoE import get_sensor_class_from_mt
import json

class CoeOutSwitch(Switch):

    def __init__(self, logger: Logger, pman: PluginManager, name: str, node: int, channel: int, device: DeviceInfo, udp_sender: UDP_Sender):
        super().__init__(
            logger=logger, 
            pman=pman, 
            callback=None, 
            name=name, 
            measurement_unit="", 
            ava_topic=None, 
            value_template="{{ value_json.value }}", 
            json_attributes=True, 
            device=device, 
            unique_id=f"CoE_SW_OUT_{udp_sender._addr}_{node}_{channel+1}",
        )
        self._channel = channel
        self._node = node
        self._udp = udp_sender
    
    def _callback(self, message, state_requested=False):
        if message is None:
            return
        msg = message.payload.decode('utf-8')
        data = None
        if msg == "OFF":
            data = self._udp._channels.setChannel(self._node, self._channel, False)
            self.turnOff()
        elif msg == "ON":
            data = self._udp._channels.setChannel(self._node, self._channel, True)
            self.turnOn()
        if data is None:
            raise Exception("Outgoind Data Packet is None")
        self._udp.sendBytes(data)
    
    def turnOn(self, qos=0):
        self._call_is_on_off(True)
        return super().turnOff( {
            "value": "ON",
            "node":  self._node,
            "chan":  self._channel+1,
            "attribution": "TA RT GmbH, Amaliendorf"
        }, qos=qos )

    def turnOff(self, qos=0):
        self._call_is_on_off(False)
        return super().turnOn( {
            "value": "OFF",
            "node":  self._node,
            "chan":  self._channel+1,
            "attribution": "TA RT GmbH, Amaliendorf"
        },qos=qos )

    def _call_is_on_off(self, b: bool):
        pass
    



class CoeOutNumber(Number):

    def __init__(self, logger: Logger, pman: PluginManager, name: str, node: int, channel: int, device: DeviceInfo, udp_sender: UDP_Sender, measure_type=MeasureType.NONE):
        super().__init__(
            logger=logger, 
            pman=pman, 
            callback=None, 
            name=name, 
            measurement_unit="", 
            ava_topic=None, 
            value_template="{{ value_json.value }}", 
            json_attributes=True, 
            device=device, 
            unique_id=f"CoE_NUMBER_OUT_{udp_sender._addr}_{node}_{channel+1}",
            device_class=get_sensor_class_from_mt(measure_type)
        )
        self._channel = channel
        self._node = node
        self._udp = udp_sender
        self._mt = measure_type
    
    def _callback(self, message, state_requested=False):
        if message is None:
            return
        msg = message.payload.decode('utf-8')
        f = float(msg)
        channel: AnalogChannels = self._udp._channels
        data = channel.setChannel(node=self._node, channel=self._channel, val=f, type=self._mt)
        if data is None:
            raise Exception("Outgoind Data Packet is None")
        self._udp.sendBytes(data)
        self.state(f)
    
    def state(self, state: float, qos=0):
        if isinstance(state, float) or isinstance(state, int):
            self._call_is_number(state)
            return super().state( {
                "value": state,
                "node":  self._node,
                "chan":  self._channel+1,
                "attribution": "TA RT GmbH, Amaliendorf"
            }, qos=qos )
        return super().state(state=state, qos=qos)
        

    def __call__(self, state: float, qos=0):
        return self.state(state, qos=qos)

    def _call_is_number(self, n: float):
        pass