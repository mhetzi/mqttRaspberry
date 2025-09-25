"""Global constants"""
VERSION_NUM = '0.2.1'
VIA_INTERFACE_NUM = 1
RAW_HID_BUFFER_SIZE = 32

"""VIA commands"""
GET_PROTOCOL_VERSION = 1
GET_KEYBOARD_VALUES = 2
CUSTOM_SET_VALUE = 7
CUSTOM_GET_VALUE = 8
CUSTOM_SAVE = 9

""" KEYBOARD_VALUE_ID """
id_uptime              = 1
id_layout_options      = 2
id_switch_matrix_state = 3
id_firmware_version    = 4
id_device_indication   = 5

"""VIA channels"""
CHANNEL_RGB_MATRIX = 3

"""VIA rgb matrix entries"""
RGB_MATRIX_VALUE_BRIGHTNESS = 1
RGB_MATRIX_VALUE_EFFECT = 2
RGB_MATRIX_VALUE_EFFECT_SPEED = 3
RGB_MATRIX_VALUE_COLOR = 4