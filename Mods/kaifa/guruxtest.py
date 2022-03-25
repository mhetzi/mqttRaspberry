from gurux_dlms import GXByteBuffer, GXReplyData
from gurux_dlms.enums import InterfaceType, Security
from gurux_dlms.secure import GXDLMSSecureClient
from gurux_common import GXCommon, IGXMediaListener, ReceiveEventArgs
from gurux_serial import GXSerial
from gurux_common import io
from gurux_dlms.GXDLMSTranslator import GXDLMSTranslator


stream_from_meter = "0F8006870E0C07E5091B01092F0F00FF88800223090C07E5091B01092F0F00FF888009060100010800FF060000328902020F00161E09060100020800FF060000000002020F00161E09060100010700FF060000000002020F00161B09060100020700FF060000000002020F00161B09060100200700FF12092102020FFF162309060100340700FF12000002020FFF162309060100480700FF12000002020FFF1623090601001F0700FF12000002020FFE162109060100330700FF12000002020FFE162109060100470700FF12000002020FFE1621090601000D0700FF1203E802020FFD16FF090C313831323230303030303039"
key_hex=""

class MediaListener(IGXMediaListener):

    def __init__(self) -> None:
        super().__init__()
        self.notify = GXReplyData()
        self.client = GXDLMSSecureClient()
        self.client.interfaceType = InterfaceType.PDU
        self.client.ciphering.security = Security.ENCRYPTION
        self.client.ciphering.blockCipherKey = GXCommon.hexToBytes(key_hex)
        self.translator = GXDLMSTranslator()
        self.reply = GXByteBuffer()


    def onError(self, sender, ex):
        """
        Represents the method that will handle the error event of a Gurux
        component.
        sender :  The source of the event.
        ex : An Exception object that contains the event data.
        """
        print("Error has occured. " + str(ex))

    def onMediaStateChange(self, sender, e):
        """Media component sends notification, when its state changes.
        sender : The source of the event.
        e : Event arguments.
        """
        print("Media state changed. " + str(e))

    def onTrace(self, sender, e):
        """Called when the Media is sending or receiving data.
        sender : The source of the event.
        e : Event arguments.
        """
        print("trace:" + str(e))

    def onPropertyChanged(self, sender, e):
        """
        Event is raised when a property is changed on a component.
        sender : The source of the event.
        e : Event arguments.
        """
        print("Property {!r} has hanged.".format(str(e)))

    def onReceived(self, sender, e: ReceiveEventArgs):
        self.reply.set(e.data)
        data = GXReplyData()
        try:
            if not self.client.getData(self.reply, data, self.notify):
                self.reply.clear()
                #If all data is received.
                if self.notify.complete:
                    if not self.notify.isMoreData():
                        #Show received data as XML.
                        xml = self.translator.dataToXml(self.notify.data)
                        print(xml)
                        #Print received data.
                        self.printData(self.notify.value, 0)

                        #Example is sending list of push messages in first parameter.
                        if isinstance(self.notify.value, list):
                            objects = self.client.parsePushObjects(self.notify.value[0])
                            #Remove first item because it's not needed anymore.
                            objects.pop(0)
                            Valueindex = 1
                            for obj, index in objects:
                                self.client.updateValue(obj, index, self.notify.value[Valueindex])
                                Valueindex += 1
                                #Print value
                                print(str(obj.objectType) + " " + obj.logicalName + " " + str(index) + ": " + str(obj.getValues()[index - 1]))
                        self.notify.clear()
                        self.reply.clear()
        except Exception as ex:
            print(ex)
            self.notify.clear()
            self.reply.clear()

    @classmethod
    def printData(cls, value, offset):
        sb = ' ' * 2 * offset
        if isinstance(value, list):
            print(sb + "{")
            offset = offset + 1
            #Print received data.
            for it in value:
                cls.printData(it, offset)
            print(sb + "}")
            offset = offset - 1
        elif isinstance(value, bytearray):
            #Print value.
            print(sb + GXCommon.toHex(value))
        else:
            #Print value.
            print(sb + str(value))

serial = GXSerial("/dev/ttyUSB0", io.BaudRate.BAUD_RATE_2400, 8, io.Parity.NONE, io.StopBits.ONE)
ml = MediaListener()
serial.addListener(ml)

try:
    print("Press any key to close the application.")
    #Open the connection.
    serial.open()
    #Wait input.
    input()
    print("Closing")
except (KeyboardInterrupt, SystemExit, Exception) as ex:
    print(ex)
serial.close()
serial.removeListener(ml)