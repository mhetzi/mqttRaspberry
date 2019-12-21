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

