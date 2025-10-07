# -*- coding: utf-8 -*-

CONFIG_NAME = "VE.Direct"

PIDs = {
    "0x203": "BMV-700",
    "0x204": "BMV-702",
    "0x205": "BMV-700H",
    
    "0xA04C": "BlueSolar MPPT 75/10",
    "0x300" : "BlueSolar MPPT 70/15 (deprecated)",
    "0xA042": "BlueSolar MPPT 75/15",
    "0xA043": "BlueSolar MPPT 100/15",
    "0xA044": "BlueSolar MPPT 100/30 rev1 (deprecated)",
    "0xA04A": "BlueSolar MPPT 100/30 rev2",
    "0xA041": "BlueSolar MPPT 150/35 rev1 (deprecated)",
    "0xA04B": "BlueSolar MPPT 150/35 rev2",
    "0xA04D": "BlueSolar MPPT 150/45",
    "0xA040": "BlueSolar MPPT 75/50 (deprecated)",
    "0xA045": "BlueSolar MPPT 100/50 rev1 (deprecated)",
    "0xA049": "BlueSolar MPPT 100/50 rev2",
    "0xA04E": "BlueSolar MPPT 150/60",
    "0xA046": "BlueSolar MPPT 150/70",
    "0xA04F": "BlueSolar MPPT 150/85",
    "0xA047": "BlueSolar MPPT 150/100",

    "0xA051": "SmartSolar MPPT 150/100",
    "0xA050": "SmartSolar MPPT 250/100",

    "0xA201": "Phoenix Inverter 12V 250VA 230V",
    "0xA202": "Phoenix Inverter 24V 250VA 230V",
    "0xA204": "Phoenix Inverter 48V 250VA 230V",
    "0xA211": "Phoenix Inverter 12V 375VA 230V",
    "0xA212": "Phoenix Inverter 24V 375VA 230V",
    "0xA214": "Phoenix Inverter 48V 375VA 230V",
    "0xA221": "Phoenix Inverter 12V 500VA 230V",
    "0xA222": "Phoenix Inverter 24V 500VA 230V",
    "0xA224": "Phoenix Inverter 48V 500VA 230V",

    "SmartSolar MPPT 250|100"       : "0xA050",
    "SmartSolar MPPT 150|100"       : "0xA051",
    "SmartSolar MPPT 150|85"        : "0xA052",
    "SmartSolar MPPT 75|15"         : "0xA053",
    "SmartSolar MPPT 75|10"         : "0xA054",
    "SmartSolar MPPT 100|15"        : "0xA055",
    "SmartSolar MPPT 100|30"        : "0xA056",
    "SmartSolar MPPT 100|50"        : "0xA057",
    "SmartSolar MPPT 150|35"        : "0xA058",
    "SmartSolar MPPT 150|100 rev2"  : "0xA059",
    "SmartSolar MPPT 150|85 rev2"   : "0xA05A",
    "SmartSolar MPPT 250|70"        : "0xA05B",
    "SmartSolar MPPT 250|85"        : "0xA05C",
    "SmartSolar MPPT 250|60"        : "0xA05D",
    "SmartSolar MPPT 250|45"        : "0xA05E",
    "SmartSolar MPPT 100|20"        : "0xA05F",
    "SmartSolar MPPT 100|20 48V"    : "0xA060",
    "SmartSolar MPPT 150|45"        : "0xA061",
    "SmartSolar MPPT 150|60"        : "0xA062",
    "SmartSolar MPPT 150|70"        : "0xA063",
    "SmartSolar MPPT 250|85 rev2"   : "0xA064",
    "SmartSolar MPPT 250|100 rev2"  : "0xA065",
    "BlueSolar MPPT 100|20"         : "0xA066",
    "BlueSolar MPPT 100|20 48V"     : "0xA067",
    "SmartSolar MPPT 250|60 rev2"   : "0xA068",
    "SmartSolar MPPT 250|70 rev2"   : "0xA069",
    "SmartSolar MPPT 150|45 rev2"   : "0xA06A",
    "SmartSolar MPPT 150|60 rev2"   : "0xA06B",
    "SmartSolar MPPT 150|70 rev2"   : "0xA06C",
    "SmartSolar MPPT 150|85 rev3"   : "0xA06D",
    "SmartSolar MPPT 150|100 rev3"  : "0xA06E",
    "BlueSolar MPPT 150|45 rev2"    : "0xA06F",
    "BlueSolar MPPT 150|60 rev2"    : "0xA070",
    "BlueSolar MPPT 150|70 rev2"    : "0xA071"
}

CS = {
    0: "Off",
    1: "Low Power",
    2: "Fault",
    3: "Bulk",
    4: "Absorption",
    5: "Float",
    9: "Inverting"
}

ERR = {
    0: "No Error",
    2: "Battery Voltage too high",
    17: "Charger temperature too high",
    18: "Charger over current",
    19: "Charger current reversed",
    20: "Bulk time limit exceeded",
    21: "Current sensor issue",
    26: "Terminals overheated",
    33: "In Voltage too high (solar panel)",
    34: "In current too high (solar panel)",
    38: "Input shutdown (excessive battery voltage)",
    116: "Factory calibration data lost",
    117: "Invalid / incompatible firmware",
    119: "User settings invalid"
}

class VEDirectDevice:

    def register_entities(self):
        pass

    def resend_entities(self):
        pass