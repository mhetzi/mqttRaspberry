from logging import Logger, getLogger
from Mods.Weatherflow.UpdateTypes import DeviceStatus, HubStatus, LightningStrikeEvent, Obs_Sky, ObsAir, RainStart, RapidWind, updateType, ObsTempest

allUpdateTypes = [DeviceStatus.DeviceStatus, HubStatus.HubStatus, LightningStrikeEvent.LightningStrikeEvent,
                  Obs_Sky.ObsSky, ObsAir.ObsAir, RainStart.RainStartEvent, RapidWind.RapidWind, ObsTempest.ObsTempest]


def parse_json_to_update(json: dict, log=getLogger("Launch")):
    log = log.getChild("parseUpdate")
    for a in allUpdateTypes:
        try:
            if a.json_is_update_type(json):
                return a(json)
        except KeyError:
            log.exception("Parsing of update failed")
            pass
    return None

