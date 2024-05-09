import json
import os
import asyncio
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from base.module import BaseModule, command, allowed_for, callback_query
from mcstatus import BedrockServer, JavaServer


class ServerStatusModule(BaseModule):
    def on_init(self, *args, **kwargs):
        super().on_init(*args, **kwargs)
        self.servers_file = os.path.join(os.path.dirname(__file__), "servers.json")
        self.servers = self.load_servers()

    def load_servers(self):
        try:
            with open(self.servers_file, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def save_servers(self):
        with open(self.servers_file, "w") as file:
            json.dump(self.servers, file)

    #@allowed_for("chat_admins")
    @command("addmcserver")
    async def addserver_cmd(self, bot: Client, message: Message):
        if len(message.text.split()) < 2:
            await message.reply(self.S["mcaddserver"]["usage"])
            return

        server_address = message.text.split(" ", maxsplit=1)[1]
        server_ip = server_address.split(":")[0]
        chat_id = str(message.chat.id)

        self.servers.setdefault(chat_id, [])

        if server_ip in [s.split(":")[0] for s in self.servers[chat_id]]:
            await message.reply(self.S["mcaddserver"]["already_added"].format(server_address=server_ip))
        else:
            self.servers[chat_id].append(server_address)
            self.save_servers()
            await message.reply(self.S["mcaddserver"]["added"].format(server_address=server_address))

    @command("mcstatus")
    async def status_cmd(self, bot: Client, message: Message):
        chat_id = str(message.chat.id)

        if not self.servers.get(chat_id):
            await message.reply(self.S["mcstatus"]["no_servers"])
            return

        server_statuses = await asyncio.gather(*[self.get_server_status(server_address) for server_address in self.servers[chat_id]])
        server_statuses = [status for status in server_statuses if status]

        if all("🔴" in status for status in server_statuses):
            await message.reply(self.S["mcstatus"]["no_statuses"])
        else:
            refresh_button = InlineKeyboardMarkup([[InlineKeyboardButton(self.S["mcstatus"]["button"], callback_data="refresh_status")]])
            await message.reply("\n".join(server_statuses), reply_markup=refresh_button)

    @callback_query(filters.regex("refresh_status"))
    async def refresh_status(self, bot: Client, callback_query):
        message = callback_query.message
        chat_id = str(message.chat.id)

        server_statuses = await asyncio.gather(*[self.get_server_status(server_address) for server_address in self.servers[chat_id]])
        server_statuses = [status for status in server_statuses if status]

        if all("🔴" in status for status in server_statuses):
            await message.edit_text(self.S["mcstatus"]["no_statuses"])
        else:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updated_message = "\n".join(server_statuses) + "\n" + self.S["mcstatus"]["last_update"].format(current_time=current_time)
            await message.edit_text(updated_message, reply_markup=message.reply_markup)

        await callback_query.answer()

    async def get_server_status(self, server_address: str) -> str:
        try:
            status = await asyncio.wait_for(self.fetch_server(server_address), timeout=5)
            if status is None:
                return self.S["server_status"]["server_offline"].format(server_address=server_address)
            elif isinstance(status, dict):
                if status["type"] == "bedrock":
                    return self.S["server_status"]["bedrock"].format(
                        server_address=server_address,
                        status_players_online=status["players_online"],
                        status_players_max=status["players_max"],
                        status_version_name=status["version_name"]
                    )
                elif status["type"] == "java":
                    return self.S["server_status"]["java"].format(
                        server_address=server_address,
                        status_players_online=status["players_online"],
                        status_players_max=status["players_max"],
                        status_version_name=status["version_name"]
                    )
                
        except asyncio.TimeoutError:
            return self.S["server_status"]["server_offline"].format(server_address=server_address)
        except Exception as e:
            self.logger.error(f"Failed to retrieve status for {server_address}: {str(e)}")
            return None

    async def fetch_server(self, server_address: str) -> dict | None:
        java_task = asyncio.create_task(self.fetch_java(server_address))
        bedrock_task = asyncio.create_task(self.fetch_bedrock(server_address))

        results = await asyncio.gather(java_task, bedrock_task)
        java_status, bedrock_status = results

        if java_status is not None:
            return java_status
        elif bedrock_status is not None:
            return bedrock_status
        else:
            return None

    async def fetch_java(self, server_address: str) -> dict | None:
        try:
            server = await JavaServer.async_lookup(server_address)
            status = await server.async_status()
            return {
                "type": "java",
                "players_online": status.players.online,
                "players_max": status.players.max,
                "version_name": status.version.name
            }
        except Exception:
            return None

    async def fetch_bedrock(self, server_address: str) -> dict | None:
        try:
            server = BedrockServer.lookup(server_address)
            status = await server.async_status()
            return {
                "type": "bedrock",
                "players_online": status.players_online,
                "players_max": status.players_max,
                "version_name": status.version.name
            }
        except Exception:
            return None