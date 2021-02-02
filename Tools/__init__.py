# -*- coding: utf-8 -*-

class RangeTools:
    @staticmethod
    def is_in_range(min: float, max: float, value: float) -> bool:
        return min <= value <= max

    @staticmethod
    def is_plus_minus(plusMinus: float, oldVal: float, newVal: float) -> bool:
        return RangeTools.is_in_range(oldVal - plusMinus, oldVal + plusMinus, newVal)
    
    @staticmethod
    def map(x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

class ConsoleInputTools:

    @staticmethod
    def get_input(prompt: str, require_val=True, std_val=None) -> str:
        while True:
            try:
                prompt = prompt if std_val is None else prompt + " [{}] ".format(std_val)
                i = input(prompt)
                if i == "" and std_val is not None:
                    return std_val
                elif i == "" and require_val:
                    print("Bitte antwort eingeben!")
                    continue
                return i
            except ValueError:
                print("Bitte antwort eingeben!")

    @staticmethod
    def get_number_input(prompt: str, map_no_input_to=None) -> int:
        while True:
            try:
                prompt = prompt if map_no_input_to is None else prompt + " [{}] ".format(map_no_input_to)
                i = input(prompt)
                if i == "" and map_no_input_to is not None:
                    return int(map_no_input_to)
                number = int(i)
                return number
            except ValueError:
                print("Antwort ist keine Zahl!")


    @staticmethod
    def get_bool_input(prompt: str, standart_value=None) -> bool:
        if standart_value is not None and standart_value:
            i = input(prompt + " [Y/n] ")
            if i == "n" or i == "N":
                return False
            return True
        elif standart_value is not None and not standart_value:
            i = input(prompt + " [y/N] ")
            if i == "y" or i == "y":
                return True
            return False
        else:
            while True:
                i = input(prompt + " [y/n] ")
                if i == "y" or i == "y":
                    return True
                elif i == "n" or i == "N":
                    return False
                else:
                    print("Eingabe ist ungültig.")