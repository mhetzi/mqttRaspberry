import win32con
import win32api
import win32gui
import win32gui_struct
struct = win32gui_struct.struct
pywintypes = win32gui_struct.pywintypes
import time
import ctypes
from ctypes import POINTER, windll, Structure, cast, CFUNCTYPE, c_int, c_uint, c_void_p, c_bool, wintypes
from comtypes import GUID
from ctypes.wintypes import HANDLE, DWORD, BOOL
import wmi



PBT_POWERSETTINGCHANGE = 0x8013
GUID_CONSOLE_DISPLAY_STATE = '{6FE69556-704A-47A0-8F24-C28D936FDA47}'
GUID_ACDC_POWER_SOURCE = '{5D3E9A59-E9D5-4B00-A6BD-FF34FF516548}'
GUID_BATTERY_PERCENTAGE_REMAINING = '{A7AD8041-B45A-4CAE-87A3-EECBB468A9E1}'
GUID_MONITOR_POWER_ON = '{02731015-4510-4526-99E6-E5A17EBD1AEA}'
GUID_SYSTEM_AWAYMODE = '{98A7F580-01F7-48AA-9C0F-44352C29E5C0}'
GUID_SESSION_USER_PRESENCE = '{3C0F4548-C03F-4C4D-B9F2-237EDE686376}'

class POWERBROADCAST_SETTING(Structure):
    _fields_ = [("PowerSetting", GUID),
                ("DataLength", DWORD),
                ("Data", DWORD)]


def wndproc(hwnd, msg, wparam, lparam):
    try:
        if msg == win32con.WM_POWERBROADCAST:
            if wparam == win32con.PBT_APMPOWERSTATUSCHANGE:
                print('Power status has changed')
            if wparam == win32con.PBT_APMRESUMEAUTOMATIC:
                print('System resume')
            if wparam == win32con.PBT_APMRESUMESUSPEND:
                print('System resume by user input')
            if wparam == win32con.PBT_APMSUSPEND:
                print('System suspend')
            if wparam == PBT_POWERSETTINGCHANGE:
                print('Power setting changed...')
                settings = cast(lparam, POINTER(POWERBROADCAST_SETTING)).contents
                power_setting = str(settings.PowerSetting)
                data_length = settings.DataLength
                data = settings.Data
                if power_setting == GUID_CONSOLE_DISPLAY_STATE:
                    if data == 0: print('  Display off')
                    if data == 1: print('  Display on')
                    if data == 2: print('  Display dimmed')
                elif power_setting == GUID_ACDC_POWER_SOURCE:
                    if data == 0: print('  AC power')
                    if data == 1: print('  Battery power')
                    if data == 2: print('  Short term power')
                elif power_setting == GUID_BATTERY_PERCENTAGE_REMAINING:
                    print('  battery remaining: %s' % data)
                elif power_setting == GUID_MONITOR_POWER_ON:
                    if data == 0: print('  Monitor off')
                    if data == 1: print('  Monitor on')
                elif power_setting == GUID_SYSTEM_AWAYMODE:
                    if data == 0: print('  Exiting away mode')
                    if data == 1: print('  Entering away mode')
                elif power_setting == GUID_SESSION_USER_PRESENCE:
                    if data == 0: print('  User present')
                    if data == 2: print('  User not present')

                else:
                    print('unknown GUID ({}, {})'.format(power_setting, GUID_SESSION_USER_PRESENCE))
            return True

        return False
    except:
        print("EXCEPTION")

if __name__ == "__main__":
    print("*** STARTING ***")
    hinst = win32api.GetModuleHandle(None)
    wndclass = win32gui.WNDCLASS()
    wndclass.hInstance = hinst
    wndclass.lpszClassName = "testWindowClass"
    CMPFUNC = CFUNCTYPE(c_bool, c_int, c_uint, c_uint, c_void_p)
    wndproc_pointer = CMPFUNC(wndproc)
    wndclass.lpfnWndProc = {win32con.WM_POWERBROADCAST : wndproc_pointer}
    try:
        myWindowClass = win32gui.RegisterClass(wndclass)
        hwnd = win32gui.CreateWindowEx(win32con.WS_EX_LEFT,
                                     myWindowClass, 
                                     "mqttScriptPowereventWindow", 
                                     0, 
                                     0, 
                                     0, 
                                     win32con.CW_USEDEFAULT, 
                                     win32con.CW_USEDEFAULT, 
                                     win32con.HWND_MESSAGE, 
                                     0, 
                                     hinst, 
                                     None)
    except Exception as e:
        print("Exception: %s" % str(e))

    if hwnd is None:
        print("hwnd is none!")
    else:
        print("hwnd: %s" % hwnd)

    guids_info = {
                    'GUID_MONITOR_POWER_ON' : GUID_MONITOR_POWER_ON,
                    'GUID_SYSTEM_AWAYMODE' : GUID_SYSTEM_AWAYMODE,
                    'GUID_CONSOLE_DISPLAY_STATE' : GUID_CONSOLE_DISPLAY_STATE,
                    'GUID_ACDC_POWER_SOURCE' : GUID_ACDC_POWER_SOURCE,
                    'GUID_BATTERY_PERCENTAGE_REMAINING' : GUID_BATTERY_PERCENTAGE_REMAINING,
                    'GUID_SESSION_USER_PRESENCE': GUID_SESSION_USER_PRESENCE
                 }
    for name, guid_info in guids_info.items():
        result = windll.user32.RegisterPowerSettingNotification(HANDLE(hwnd), GUID(guid_info), DWORD(0))
        print('registering', name)
        print('result:', hex(result))
        print('lastError:', win32api.GetLastError())
        print()
    
    # Get All PnP Devices
    obj = wmi.WMI().Win32_PnPEntity()
    #Filter for Monitors
    pnp_dict = {}
    services=[]
    for x in obj:
        pnp_entry = {}
        for props in x.properties.keys():
            property = x.wmi_property(props)
            pnp_entry[property.name] = property.value
        pnp_dict[x.id] = pnp_entry
        if pnp_entry["Service"] not in services:
            services.append(pnp_entry["Service"])

        print("Diese Services wurden gefunden: {}".format(services))

    ######################## In eigenen Thread ###################
    shutdown = False
    #                        __InstanceDeletionEvent for removed devices
    raw_wql = "SELECT * FROM __InstanceCreationEvent WITHIN 2 WHERE TargetInstance ISA \'Win32_PnPEntity\'" # for added devices
    c = wmi.WMI ()
    watcher = c.watch_for(raw_wql=raw_wql)
    while not shutdown:
        try:
            pnp = watcher(2500)
            print(pnp)
        except wmi.x_wmi_timed_out:
            pass
    ##############################################################

    print('\nEntering loop')
    try:
        while True:
            win32gui.PumpWaitingMessages()
            time.sleep(1)
        # https://winaero.com/run-a-program-hidden-in-windows-10/
    
    except:
        ##### CLEAN UP
        windll.user32.UnregisterPowerSettingNotification(result)
    