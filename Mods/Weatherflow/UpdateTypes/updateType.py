# -*- coding: utf-8 -*-
import enum

class UpdateType(enum.Enum):
    DeviceStatus = 0
    HubStatus = 1
    LightningStrikeEvent = 2
    ObsSky = 3
    ObsAir = 4
    RainStart = 5
    RapidWind = 6