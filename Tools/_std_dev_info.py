import sys
import subprocess
import Tools.Autodiscovery as ad
import re
import platform
import logging

class DevInfoFactory:

    @staticmethod
    def _read_app_version(log: logging.Logger, devInf:ad.DeviceInfo):
        gitVer = ""
        osRelease = ""
        try:
            gitVerProc = subprocess.run(["git", "rev-parse", "--short", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            gitVer = gitVerProc.stdout.decode('utf-8').replace("\n","")
        except:
            log.exception("Kein Git gefunden")
        try:
            osReleaseFile = open("/etc/os-release", "r")
            osReleaseBuffer = osReleaseFile.read()
            osRelease = re.findall('PRETTY_NAME=\".*?\"', osReleaseBuffer)[0].replace("PRETTY_NAME=", "")
        except:
            log.exception("os-release")
        devInf.sw_version = "{}|APP:{}".format(osRelease, gitVer)

    @staticmethod
    def read_pi_model(MACs:list, devInf:ad.DeviceInfo, log:logging.Logger):
        rpi_model = open("/sys/firmware/devicetree/base/model", "r").read().replace("\n","")
        devInf.model = rpi_model
        devInf.mfr = "Raspberry"
        try:
            serial = open("/proc/cpuinfo", "r").read()
            serial = re.findall("Serial.*?$", serial)[0].replace(" ", "").replace("Serial:", "").replace("\t", "")
            MACs.append(serial)
        except:
            log.exception("Kann Seriennummer nicht ermitteln")
            serial = "Unknown"
        devInf.pi_serial = serial

    @staticmethod
    def read_computer_model(MACs:list, devInf:ad.DeviceInfo):
        devInf.model = open("/sys/devices/virtual/dmi/id/board_name").readline().replace("\n","")
        devInf.mfr = open("/sys/devices/virtual/dmi/id/board_vendor").readline().replace("\n","")
        MACs.append(open("/sys/devices/virtual/dmi/id/modalias").readline().replace("\n",""))

    @staticmethod
    def build_std_device_info(log: logging.Logger) -> ad.DeviceInfo:
        devInf = ad.DeviceInfo()
        devInf.name = platform.node()
        if sys.platform == "linux":
            MACs = []
            try:
                DevInfoFactory.read_pi_model(MACs, devInf, log)
            except:
                log.exception("Kein Raspberry Pi Model")
                try:
                    DevInfoFactory.read_computer_model(MACs, devInf)
                except:
                    log.exception("Kein Computer Model")
            try:
                ip_link_proc = subprocess.run(["ip", "link"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for MAC in re.findall("..:..:..:..:..:..", ip_link_proc.stdout.decode('utf-8')):
                    if MAC != "ff:ff:ff:ff:ff:ff" and MAC != "00:00:00:00:00:00":
                        MACs.append(MAC)
                        log.info("Füge MAC {} hinzu".format(MAC))
            except:
                log.exception("IDs")
        elif sys.platform == "win32":
            import uuid
            MACs = [hex(uuid.getnode())]

        devInf.IDs = MACs
        log.debug(devInf)
        return devInf