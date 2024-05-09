import json
import os
import asyncio
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from base.module import BaseModule, command, allowed_for, callback_query
from mcstatus import BedrockServer, JavaServer
from mcstatus.status_response import BedrockStatusResponse, JavaStatusResponse

class ServerStatusModule(BaseModule):
    def on_init(self, *args, **kwargs):
        super().on_init(*args, **kwargs)
        self.servers_file = os.path.join(os.path.dirname(__file__), "servers.json")
        self.servers = self.load_servers()
        self.processing_lock = asyncio.Lock()

    def load_servers(self):
        try:
            with open(self.servers_file, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def save_servers(self):
        with open(self.servers_file, "w") as file:
            json.dump(self.servers, file)

    @allowed_for(["chat_admins", "chat_owner"])
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
        async with self.processing_lock:
            chat_id = str(message.chat.id)

            if not self.servers.get(chat_id):
                await message.reply(self.S["mcstatus"]["no_servers"])
                return

            wait_message = await message.reply(self.S["mcstatus"]["please_wait"])

            server_statuses = await asyncio.gather(*[self.get_server_status(server_address) for server_address in self.servers[chat_id]])
            server_statuses = [message for sublist in server_statuses for message in sublist]

            if all("🔴" in status for status in server_statuses):
                await wait_message.edit(self.S["mcstatus"]["no_statuses"])
            else:
                refresh_button = InlineKeyboardMarkup([[InlineKeyboardButton(self.S["mcstatus"]["button"], callback_data="refresh_status")]])
                await wait_message.edit("\n".join(server_statuses), reply_markup=refresh_button)

    @callback_query(filters.regex("refresh_status"))
    async def refresh_status(self, bot: Client, callback_query):
        async with self.processing_lock:
            message = callback_query.message
            chat_id = str(message.chat.id)

            await message.edit(self.S["mcstatus"]["please_wait"])

            server_statuses = await asyncio.gather(*[self.get_server_status(server_address) for server_address in self.servers[chat_id]])
            server_statuses = [message for sublist in server_statuses for message in sublist]

            if all("🔴" in status for status in server_statuses):
                await message.edit(self.S["mcstatus"]["no_statuses"])
            else:
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                updated_message = "\n".join(server_statuses) + "\n" + self.S["mcstatus"]["last_update"].format(current_time=current_time)
                await message.edit(updated_message, reply_markup=message.reply_markup)

            await callback_query.answer()

    async def get_server_status(self, server_address: str) -> list[str]:
        messages = []
        try:
            java_status, bedrock_status = await asyncio.gather(
                self.fetch_java(server_address),
                self.fetch_bedrock(server_address)
            )
            if not java_status and not bedrock_status:
                messages.append(self.S["server_status"]["server_offline"].format(server_address=server_address))
                return messages
            elif java_status and bedrock_status:
                messages.append(self.S["server_status"]["both"].format(
                    server_address=server_address,
                    status_players_online=bedrock_status.players.online,
                    status_players_max=bedrock_status.players.max,
                    bedrock_status_version_name=bedrock_status.version.name,
                    java_status_version_name=java_status.version.name
                ))
                return messages
            elif java_status:
                messages.append(self.S["server_status"]["java"].format(
                    server_address=server_address,
                    status_players_online=java_status.players.online,
                    status_players_max=java_status.players.max,
                    status_version_name=java_status.version.name
                ))
            elif bedrock_status:
                messages.append(self.S["server_status"]["bedrock"].format(
                    server_address=server_address,
                    status_players_online=bedrock_status.players.online,
                    status_players_max=bedrock_status.players.max,
                    status_version_name=bedrock_status.version.name
                ))
        except Exception as e:
            self.logger.error(f"Failed to retrieve status for {server_address}: {str(e)}")

        return messages

    async def fetch_java(self, server_address: str) -> JavaStatusResponse | None:
        try:
            server = await JavaServer.async_lookup(server_address)
            return await server.async_status()
        except Exception:
            return None

    async def fetch_bedrock(self, server_address: str) -> BedrockStatusResponse | None:
        try:
            server = BedrockServer.lookup(server_address)
            return await server.async_status()
        except Exception:
            return None