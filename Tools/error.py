import sys

is_system_mode = False

class RestartError(Exception):
   _restart = True

class InSystemModeError(Exception):
   pass

def is_venv():
   return (hasattr(sys, 'real_prefix') or
         (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))

def try_install_package(package:str, throw=ImportError(), ask=True):
   if not is_venv():
      raise throw
   if ask and is_system_mode:
      raise InSystemModeError()
   if ask:
      from Tools import ConsoleInputTools as cit
      if cit.get_bool_input("Plugin abhängigkeit fehlt! soll {} installiert werden?".format(package), False):
         ask = False
      else:
         raise throw
   if not ask:
      from pip._internal import main as pipm
      try:
         pipm(['install', package])
      except TypeError:
         pipm.main(['install', package])
      raise RestartError()

def set_system_mode(mode:bool):
   global is_system_mode
   is_system_mode = mode