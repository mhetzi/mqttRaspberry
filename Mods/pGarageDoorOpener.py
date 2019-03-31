# -*- coding: utf-8 -*-

import paho.mqtt.client as mclient
import Tools.Config as conf
import logging

# Platine Belegung
# Taster Pin_22 GPIO_25
#
# Reed_1 Pin_16 GPIO_23
# Reed_2 Pin_18 GPIO_24
# Reed_3 Pin_15 GPIO_22

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "PiGarage"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        import Mods.DoorOpener.plugin as dp
        return dp.DoorOpener(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools

        rpin = ConsoleInputTools.get_number_input("Pin Nummer des Taster Relais ", 22)
        delay = ConsoleInputTools.get_number_input("Wie viele ms soll das Relais gehalten werden?", 250)

        apin = ConsoleInputTools.get_number_input("Pin Nummer des ALERT Signals", 33)
        addr = ConsoleInputTools.get_number_input("Addresse des ADC", 0x49)
        gain = ConsoleInputTools.get_number_input("GAIN für ADC", 1)
        readings = ConsoleInputTools.get_number_input("Wie oft soll ADC gelesen werden, bevor aktion durchgeführt wird?", 2)

        print("Jetzt kommt die Positions abfrage. \nWenn Kanal nicht bnutzt nur enter drücken.\n")
        pos0 = ConsoleInputTools.get_number_input("Position für 1 Kanal", -1)
        pos1 = ConsoleInputTools.get_number_input("Position für 2 Kanal", -1)
        pos2 = ConsoleInputTools.get_number_input("Position für 3 Kanal", -1)
        pos3 = ConsoleInputTools.get_number_input("Position für 4 Kanal", -1)

        door_open_time = ConsoleInputTools.get_number_input("Wie lange braucht das Tor von zu bis auf oder umgekehrt maximal?\n>", 15)
        door_open_retry = ConsoleInputTools.get_number_input("Wie oft soll versucht werden das Tor in die Position zu bringen?\n>", 3)
        name = ConsoleInputTools.get_input("Wie heißt das Tor?", require_val=True)

        conf["PiGarage/relayPin"] = rpin
        conf["PiGarage/relayPulseLength"] = delay
        conf["PiGarage/Hall/ALERT_PIN"] = apin
        conf["PiGarage/Hall/ADC_ADDR"] = addr
        conf["PiGarage/Hall/GAIN"] = gain
        conf["PiGarage/Hall/adc_readings"] = readings
        conf["PiGarage/Hall/Channels_Position"] = [pos0, pos1, pos2, pos3]
        conf["PiGarage/Hall/max_move_time"] = door_open_time
        conf["PiGarage/Hall/max_move_retrys"] = door_open_retry
        conf["PiGarage/name"] = name

        do_calib = ConsoleInputTools.get_bool_input("Kalibration jetzt starten?", True)
        if do_calib:
            PluginLoader.runCalibrationProcess(conf, logger)

    @staticmethod
    def runCalibrationProcess(conf: conf.BasicConfig, logger:logging.Logger):
        from Mods.DoorOpener.calibrate import Calibrate
        Calibrate.run_calibration(conf, logger)
