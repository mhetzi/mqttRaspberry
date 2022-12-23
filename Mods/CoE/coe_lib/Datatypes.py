import enum

class MeasureType(enum.IntEnum):
    NONE = 0
    TEMPERATURE = 1
    WATTQUADRMETER = 2
    literhour = 3
    SECONDS  =4
    MINUTES = 5
    LITERIMPULS = 6
    KELVIN = 7
    PERCENT = 8
    UNKNOWN9 = 9
    KILOWATT = 10
    KILOWATTHOURS = 11
    MEGAWATTHOURS = 12
    VOLT = 13
    MILLIAMPERE = 14
    HOURS = 15
    DAYS = 16
    IMPULSE = 17
    KILOOHM = 18
    LITER = 19
    KMH = 20
    Hz = 21
    LITERMIN = 22
    BAR = 23
    KILLOMETER = 25
    METER = 26
    MILLIMETER = 27
    KUBIKMETER = 28
    LITERDAY = 35
    METERSECOND = 36
    KUBIKMETER_MIN = 37
    KUBIKMETER_HOUR = 38
    KUBIKMETER_DAY = 39
    MILLIMETER_MIN = 40
    MILLIMETER_HOUR = 41
    MILLIMETER_DAY = 42
    ON_OFF = 43
    NO_YES = 44
    CELSIUS = 46
    EUR = 50
    USD = 51


    def getScaleFactor(self):
        __scaling = {
            MeasureType.TEMPERATURE: 10,
            MeasureType.KILOWATT: 100,
            MeasureType.KILOWATTHOURS: 10,
            MeasureType.PERCENT: 10
        }
        return __scaling.get(self, 1)
    
    def doScale(self, val: float):
        return val / self.getScaleFactor()

    def getUnit(self):
        match self:
            case MeasureType.TEMPERATURE:
                return "°C"
            case MeasureType.WATTQUADRMETER:
                return "w/m²"
            case MeasureType.PERCENT:
                return "%"
            case MeasureType.literhour:
                return "l/h"
            case MeasureType.SECONDS:
                return "seconds";
            case MeasureType.MINUTES:
                return "minutes"
            case MeasureType.HOURS:
                return "hours"
            case MeasureType.DAYS:
                return "days"
            case MeasureType.LITERIMPULS:
                return "i/l"
            case MeasureType.KELVIN:
                return "K"
            case MeasureType.KILOWATT:
                return "kW"
            case MeasureType.KILOWATTHOURS:
                return "kWh"
            case MeasureType.MEGAWATTHOURS:
                return "MWh"
            case MeasureType.VOLT:
                return "V"
            case MeasureType.MILLIAMPERE:
                return "mA"
            case MeasureType.IMPULSE:
                return "imp"
            case MeasureType.KILOOHM:
                return "kOhm"
            case MeasureType.LITER:
                return "l"
            case MeasureType.KMH:
                return "km/h"
            case MeasureType.Hz:
                return "Hz"
            case MeasureType.LITERMIN:
                return "liter/min"
            case MeasureType.BAR:
                return "bar"
            case MeasureType.KILLOMETER:
                return "km"
            case MeasureType.METER:
                return "m"
            case MeasureType.MILLIMETER:
                return "mm"
            case MeasureType.KUBIKMETER:
                return "m³"
            case MeasureType.LITERDAY:
                return "l/day"
            case MeasureType.METERSECOND:
                return "m/s"
            case MeasureType.CELSIUS:
                return "°C"
            case MeasureType.EUR:
                return "EUR"
            case MeasureType.USD:
                return "USD"
            case _:
                return ""