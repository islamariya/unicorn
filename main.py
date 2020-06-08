import asyncio
import argparse

from abstact_class import AbstactBankAccont
from settings import DEBUG_MODE_ON_COMMANDS as on_commands,\
                     DEBUG_MODE_OFF_COMMANDS as off_commands


class BankRateHandler(AbstactBankAccont):

    def print_data(self):
        return None


def create_args_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", action="store", dest="period", type=int, required=True)
    parser.add_argument("--rub", action="store", dest="rub", type=int, required=True)
    parser.add_argument("--usd", action="store", dest="usd", type=int, required=True)
    parser.add_argument("--eur", action="store", dest="eur", type=int, required=True)
    parser.add_argument("--cny",  action="store", dest="cny", type=int)
    # при необходимости расширить список валют
    parser.add_argument("--debug", action="store", dest="debug_mode", choices=on_commands+off_commands)
    return parser


if __name__ == "__main__":
    parser = create_args_parser()
    args = parser.parse_args()
    app = BankRateHandler(vars(args))
    asyncio.run(app.start_server())