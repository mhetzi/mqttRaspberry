# mqttRaspberry
Mein Python Skript um verschiedene sensoren auf MQTT zu puschen

**Bereits vorhandene Plugins:**
 * DS1820 OneWire
 * WeatherFlow UDP Bridge
 * ShellSwitch HA Switch welcher Commands ausführt
 * MqttGpio   GPIO von Raspberry über MQTT steuerbar machen
 * JsonPipe   Erstelle eine named_pipe, andere programme/Skripte können so etwas auf MQTT pushen
 * DoorOpener Tür öffner (Wie bei Wohnungshäusern) Entsperren und öffnungsstatus via Taster bestimmen
 * BHL1750    Helligkeitssensor (Lux)


 **Dependencies:**
 python3-schedule python3-paho-mqtt
