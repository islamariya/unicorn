from abc import ABC, abstractmethod
import asyncio
import json
import time

from aiohttp import web, ClientSession, ClientConnectionError

from logs import logging
from settings import DEBUG_MODE_ON_COMMANDS as ON_COMMANDS, RATES_BASE_URL, SERVER_PORT, INFORM_PERIODICITY


class AbstactBankAccont(ABC):

    @abstractmethod
    def print_data(self):
        return None

    def __init__(self, args):
        self.is_debug_mode = self.debug_mode_evaluate(args)
        self.rate_update_periodicity = args["period"]
        self.database = self.database_creation(args)
        self.foreign_currency_names = self.get_foreign_currency()
        self.message_queue = asyncio.Queue()

    # init part
    def debug_mode_evaluate(self, command_text):
        """This method checks if debug_mode was activated in console (not None) and whether it is turning it on,
         if command text is in on_command ("1", "true", "True", "y", "Y")
         params: command_text: dict
         :return bool
         """
        self.is_debug_mode = True if command_text["debug_mode"] is not None and \
                                     command_text["debug_mode"] in ON_COMMANDS \
            else False
        return self.is_debug_mode

    def database_creation(self, args):
        """This method extracts currency' names given in launch-params
        and fills database dict with it's start value. If
        :param args: dict
        :return: dict {currency_name: {"balance": int)
        """
        self.database = {}
        for currency in args:
            if currency not in ("period", "debug_mode") and args[currency] is not None:
                self.database[currency] = {"balance": int(args[currency])}
        return self.database

    def get_foreign_currency(self):
        """This method extract foreign currencies from given in command-line
        :return tuple
        """
        foreign_currency_tuple = tuple(item for item in self.database if item != "rub")
        return foreign_currency_tuple

    # business_logic part
    async def get_currency_rates(self, data):
        """This method selects rates for particular currencies and updates data in DB.
        It also detects if rate has been changed and if so put message type in self.message_queue
        :param data: dict with all currency from responce
        :return: update database's dict
        """
        is_rate_changed = False
        message_type = 1
        for currency in self.foreign_currency_names:
            try:
                if "rate" in self.database[currency] and \
                        self.database[currency]["rate"] != float(data[currency.upper()]["Value"]):
                    is_rate_changed = True
                self.database[currency]["rate"] = float(data[currency.upper()]["Value"])
            except (KeyError, TypeError):
                logging.ERROR("ключ не найден")
        if is_rate_changed:
            await self.message_queue.put(message_type)
        return self.database

    async def get_total_amount_message(self):
        """This method calculates total amount of money in all used currencies and creates a message text"""
        rub_total = self.database["rub"]["balance"]
        for currency in self.foreign_currency_names:
            rub_total += self.database[currency]["rate"] * self.database[currency]["balance"]
        message = f"\n sum {rub_total:.2f} rub /"
        for currency in self.foreign_currency_names:
            message += f" {rub_total / self.database[currency]['rate']:.2f} {currency} /"
        return message

    async def create_balance_message(self):
        """This method creates message about current balance"""
        message = ""
        for currency in self.database:
            message += f"{currency}: {self.database[currency]['balance']} \n"
        return message

    async def get_currency_ratio(self, currency_1, currency_2):
        """This method calculates a foreign currency ratio between each other (usd-eur, etc)
        and create a message"""
        rate_1 = self.database[currency_1]["rate"]
        rate_2 = self.database[currency_2]["rate"]
        is_rate_1_max = True if rate_1 > rate_2 else False
        ratio = rate_1 / rate_2 if is_rate_1_max else rate_2 / rate_1
        if is_rate_1_max:
            message = f"\n {currency_2}-{currency_1}: {ratio:.2f} \n"
        else:
            message = f"\n{currency_1}-{currency_2}: {ratio:.2f} \n"
        return message

    async def create_rate_message(self):
        """This method creates a messages about current rates """
        currency_1, currency_2 = self.foreign_currency_names
        message = await self.get_currency_ratio(currency_1, currency_2)
        for currency in self.foreign_currency_names:
            message += f"rub-{currency}: {self.database[currency]['rate']:.1f} \n"
        return message

    async def create_message(self):
        """This method combines final message for total amount handler"""
        balance_message = await self.create_balance_message()
        total_amount_message = await self.get_total_amount_message()
        ratio_message = await self.create_rate_message()
        total_message = balance_message + ratio_message + total_amount_message
        return total_message

    # views
    async def currency_balance_handler(self, request):
        """This method handles curency balance request
        Currency name is taken from response"""
        try:
            currency = request.match_info["currency_name"]
            print(currency)
            current_balance = self.database[currency]["balance"]
            message = f"{currency}: {current_balance}"
        except KeyError:
            message = f"{currency} не используется в системе"
        if self.is_debug_mode:
            print(request)
        return web.Response(text=message, content_type="text/plain")

    async def total_amount_handler(self, request):
        """This method informs about:
        - total amount of money in rub and each foreign currency, calculated on current
        rate,
        - current balance and rate of every currency"""
        message = await self.create_message()
        if not self.is_debug_mode:
            print(message)
        else:
            print(request)
        return web.Response(text=message, content_type="text/plain")

    async def set_amount_handler(self, request):
        """This method handles set request"""
        message_type = 2
        is_balance_has_changed = False
        request_body = await request.json()
        try:
            for currency in request_body:
                if self.database[currency]["balance"] != float(request_body[currency]):
                    is_balance_has_changed = True
                self.database[currency]["balance"] = float(request_body[currency])
            if is_balance_has_changed:
                await self.message_queue.put(message_type)
            message = "Данные успешно обновлены"
        except KeyError:
            message = f"{currency} не поддерживается системой"
        if self.is_debug_mode:
            print(request)
        return web.Response(text=message, content_type="text/plain")

    async def modify_handler(self, request):
        """This method handles modify request"""
        message_type = 3
        try:
            request_body = await request.json()
            for currency in request_body:
                self.database[currency]["balance"] += float(request_body[currency])
            await self.message_queue.put(message_type)
            message = "Данные успешно обновлены"
        except KeyError:
            message = f"{currency} не поддерживается системой"
        if self.is_debug_mode:
            print(request)
        return web.Response(text=message, content_type="text/plain")

    # app part
    def create_server(self):
        """This method creates instance of web server application and binds routes
        :return: app instance
        """
        app = web.Application()
        self.setup_routes(app)
        return app

    def setup_routes(self, app):
        """This method defines endpoints and binds them with handlers"""
        app.add_routes([web.get("/amount/get", self.total_amount_handler),
                        web.get(r"/{currency_name}/get", self.currency_balance_handler),
                        web.post("/amount/set", self.set_amount_handler),
                        web.post("/amount/modify", self.modify_handler)
                        ])

    async def create_tasks(self, app):
        """This methods launch server runner and 2 endless background task:
        - currency's rate update task
        - send messages about changes of rate or balance every 60 seconds
        """
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host='127.0.0.1', port=SERVER_PORT)
        await site.start()
        if not self.is_debug_mode:
            print("Приложение успешно запущено")
            logging.debug("Приложение успешно запущено")
        changes_informer = asyncio.create_task(self.changes_informer())
        data_request = asyncio.create_task(self.rate_update())
        await asyncio.gather(changes_informer, data_request)

    async def changes_informer(self):
        """This method checks if there are any changing, creates message and send one of them every 60
        seconds"""
        while True:
            if not self.message_queue.empty():
                await self.message_queue.get()
                message = await self.create_message()
                print(message)
            await asyncio.sleep(INFORM_PERIODICITY)

    async def rate_update(self):
        """This method is a periodic task to update currencies rate and write it to database."""
        while True:
            session = ClientSession()
            currency_rates = await self.make_request(session)
            if currency_rates is not None:
                self.database = await self.get_currency_rates(currency_rates)
                print("Курсы валют успешно получены")
            await asyncio.sleep(self.rate_update_periodicity)

    async def make_request(self, session):
        """This method loads json data about all currencies"""
        try:
            async with session.get(RATES_BASE_URL) as response:
                if response.status == 200:
                    responce_data = await response.text()
                    responce_data_dict = json.loads(responce_data)
                    if self.is_debug_mode:
                        print(response)
                else:
                    logging.error(response.status, "Получен код ошибки")
                    return None
                await session.close()
                return responce_data_dict["Valute"]
        except ClientConnectionError as error:
            logging.error(error)

    def start_server(self):
        app = self.create_server()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.create_tasks(app))
        loop.run_forever()
