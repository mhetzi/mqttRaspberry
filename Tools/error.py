import sys

is_system_mode = False

class RestartError(Exception):
   _restart = True

class InSystemModeError(Exception):
   pass

def get_base_prefix_compat():
    """Get base/real prefix, or sys.prefix if there is none."""
    return getattr(sys, "base_prefix", None) or getattr(sys, "real_prefix", None) or sys.prefix

def is_venv():
   return get_base_prefix_compat() != sys.prefix

def try_install_package(package:str, throw=ImportError(), ask=True, retry=5):
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
      except EnvironmentError as e:
         print("Fehler in pip. Werde es noch {} mal versuchen.".format(retry+1))
         try_install_package(package=package, throw=e, ask=False, retry=retry-1)
      raise RestartError()

def set_system_mode(mode:bool):
   global is_system_mode
   is_system_mode = mode