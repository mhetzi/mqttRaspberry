# -*- coding: utf-8 -*-
import Adafruit_ADS1x15
import Tools.Config
import logging
import time


class Calibrate:

    def __init__(self, config_file: Tools.Config.BasicConfig, logger: logging.Logger):
        self._config = config_file
        self._recorded_data = []
        self._analyzed_data = {}
        self._channels = config_file.get("rpiDoor/Hall/Channels_Position", [0,40,80,100])
        self._logger = logger.getChild("Kalibrierung")
        self.__adc = Adafruit_ADS1x15.ADS1115(address=config_file.get("rpiDoor/Hall/ADC_ADDR", 0x49))
        self._GAIN = config_file.get("rpiDoor/Hall/GAIN", 1)

    def record_noise(self, data_points=10000, spacing_secs=0.15):
        i = 0
        while i <= data_points:
            i += 1 
            new_data = []
            if self._channels[0] > -1:
                new_data.append(self.__adc.read_adc(channel=0, gain=self._GAIN))
            if self._channels[1] > -1:
                new_data.append(self.__adc.read_adc(channel=1, gain=self._GAIN))
            if self._channels[2] > -1:
                new_data.append(self.__adc.read_adc(channel=2, gain=self._GAIN))
            if self._channels[3] > -1:
                new_data.append(self.__adc.read_adc(channel=3, gain=self._GAIN))
            self._recorded_data.append(new_data)
            self._logger.info("{} von {}".format(i-1, data_points))
            if spacing_secs != None:
                time.sleep(spacing_secs)

    def analyze_noise(self):
        used_channels = len(self._recorded_data[0])
        middle_point_datas = []

        self._logger.info("Ermittle Mittelwerte...")
        for i in range(0, used_channels):
            base_val = 0
            for o in range(0, len(self._recorded_data)):
                base_val += self._recorded_data[o][i]
            middle_point_datas.append(base_val / len(self._recorded_data))

        jitter = []
        pos_diff = [0 for j in range(0, used_channels)]
        neg_diff = [0 for j in range(0, used_channels)]

        self._logger.info("Ermittle maximal Werte...")
        for rec in self._recorded_data:
            diff = []
            for i in range(0, len(rec)):
                d = rec[i] - middle_point_datas[i]
                diff.append(d)
                if d > 0 and d > pos_diff[i]:
                    pos_diff[i] = d
                elif d < 0 and d < neg_diff[i]:
                    neg_diff[i] = d

            jitter.append(diff)
        #compress 1st stage
        self._logger.info("Berechne auf / ab")
        jitter_counter = [{} for j in range(0, len(jitter[0]))]
        for current_jitter in jitter:
            for channel_num_jitter in range(0, len(current_jitter)):
                channel_vals = jitter_counter[ channel_num_jitter ]
                channel_jitter = current_jitter[channel_num_jitter]
                if channel_vals.get(channel_jitter, None) is None:
                    channel_vals[channel_jitter] = 0
                channel_vals[channel_jitter] += 1

        self._logger.info("Sortiere auf / ab")
        sorted_jit_count = []
        for ji in jitter_counter:
            s = ["{}x {}".format(ji[k], k) for k in sorted(ji, key=ji.__getitem__, reverse=False)]
            sorted_jit_count.append(s)

        format_sequenz = ""
        for i in range (0, len(sorted_jit_count)):
            format_sequenz += "| {" + str(i) + ":>25} "
        format_sequenz += "|"

        max_items = 0
        for i in range(0, len(sorted_jit_count)):
            if len(sorted_jit_count[i]) > max_items:
                max_items = len(sorted_jit_count[i])

        for i in range(0, len(sorted_jit_count)):
            while len(sorted_jit_count[i]) < max_items:
                sorted_jit_count[i].insert(0, "---")

        for i in range(0, len(sorted_jit_count[0])):
            tup = []
            for ii in range(0, len(sorted_jit_count)):
                tup.append(sorted_jit_count[ii][i])
            tup = tuple(tup)
            self._logger.info(format_sequenz.format(*tup))
        self._logger.info(format_sequenz.format("", "Gemessene Werte im ", " überblick.", ""))
        self._logger.info("Höchste Positive änderung:")
        self._logger.info(format_sequenz.format(*tuple(pos_diff)))
        self._logger.info("Höchste Negative änderung:")
        self._logger.info(format_sequenz.format(*tuple(neg_diff)))
        self._logger.info("Änderungen werden von 0 berrechnet und 0 ist in dem Fall:")
        self._logger.info(format_sequenz.format(*tuple(middle_point_datas)))

        self._config["rpiDoor/Hall/Kalib/zeroPoints"] = middle_point_datas
        self._config["rpiDoor/Hall/Kalib/posMaxPoints"] = pos_diff
        self._config["rpiDoor/Hall/Kalib/minMaxPoints"] = neg_diff
        self._config.save()

    def print_calibrtion_state(self):
        pass

    @staticmethod
    def run_calibration(conf: Tools.Config.BasicConfig, logger: logging.Logger):
        from Tools import ConsoleInputTools
        dp = ConsoleInputTools.get_number_input("Wie viele Datenpunkte sollen analysiert werden?", 10000)
        gap = ConsoleInputTools.get_number_input("Wie viele Millis sollen zwischen den DPs liegen?", 250)

        c = Calibrate(conf, logger)
        c.record_noise(data_points=dp, spacing_secs=gap / 1000)
        c.analyze_noise()

if __name__ == '__main__':
    import pathlib

    log = logging.getLogger("Launch")
    log.setLevel(logging.DEBUG)
    # fh = logging.FileHandler('spam.log')
    # fh.setLevel(logging.DEBUG)
    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)8s - %(message)s')
    # fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # add the handlers to the logger
    # logger.addHandler(fh)
    log.addHandler(ch)

    c = Tools.Config.BasicConfig(pathlib.Path("/tmp/test.conf"), log)
    c.load()

    cal = Calibrate(c, log)
    rec = c["rpiDoor/TEST/REC"]
    cal._recorded_data = rec
    cal.analyze_noise()
