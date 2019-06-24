# -*- coding: utf-8 -*-
# Um das skript ohne sudo verwenden zu können:
# sudo setcap 'cap_net_raw,cap_net_admin+eip' '/usr/local/lib/python3.6/site-packages/bluepy/bluepy-helper'

import bluepy.btle as ble


class ScanDelegate(ble.DefaultDelegate):
    def __init__(self):
        ble.DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev: ble.ScanEntry, isNewDev, isNewData):
        if isNewDev:
            print("== BEGIN DEVICE == ")
            print ("Discovered device", dev.addr, dev.rssi, dev.getValue(ble.ScanEntry.COMPLETE_LOCAL_NAME), dev.TX_POWER, "public_addr" if dev.addrType == ble.ScanEntry.PUBLIC_TARGET_ADDRESS else "random_addr" )
            for tup in dev.getScanData():
                print ("{}: {} [{}]".format(tup[0], tup[2], tup[1]))
            print("=== END DEVICE ===")
        elif isNewData:
            print("== BEGIN DEVICE == ")
            print ("Received new data from", dev.addr, dev.rssi, dev.getValue(ble.ScanEntry.COMPLETE_LOCAL_NAME), dev.TX_POWER, dev.dataTags)
            for (adtype, desc, value) in dev.getScanData():
                print ("  %s = %s" % (desc, value))
            print("=== END DEVICE === ")

    def handleNotification(self, cHandle, data):
        print ("== NOTIFICATION BEGIN ==")
        print (cHandle)
        print (data)
        print ("=== NOTIFICATION END ===")
        


def test():
    scanner = ble.Scanner(0).withDelegate(ScanDelegate())
    """devices = scanner.scan(10.0)

    for dev in devices:
        print("Device %s (%s), RSSI=%d dB" % (dev.addr, dev.addrType, dev.rssi))
        for (adtype, desc, value) in dev.getScanData():
            print("  %s = %s" % (desc, value))

    scanner.clear()"""
    print("Continous scanning...")
    try:
        scanner.start()
        while True:
            scanner.process(10)
        scanner.stop()
    except KeyboardInterrupt:
        scanner.stop()


if __name__ == "__main__":
    test()