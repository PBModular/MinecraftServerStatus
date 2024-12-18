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
    def on_init(self):
        self.servers_file = os.path.join(os.path.dirname(__file__), "servers.json")
        self.servers = self.load_servers()
        self.cache = {}
        self.update_interval = 60
        self.active_chats = set()
        self.update_task = None
        self.start_background_update()

    def on_unload(self):
        if (self, 'update_task') and self.update_task:
            self.update_task.cancel()

    def load_servers(self):
        try:
            with open(self.servers_file, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def save_servers(self):
        with open(self.servers_file, "w") as file:
            json.dump(self.servers, file)

    def start_background_update(self):
        self.update_task = asyncio.create_task(self.background_update())
        self.update_task.add_done_callback(self.handle_task_completion)

    def handle_task_completion(self, task):
        try:
            task.result()
        except Exception as e:
            self.logger.error(f"Background task failed: {e}")

    async def background_update(self):
        try:
            while True:
                await asyncio.sleep(self.update_interval)
                await self.update_active_chats()
        except asyncio.CancelledError:
            return

    async def update_active_chats(self):
        tasks = []
        for chat_id in self.active_chats:
            server_list = self.servers.get(chat_id, [])
            if server_list:
                tasks.append(self.update_chat_servers(chat_id, server_list))
        await asyncio.gather(*tasks)

    async def update_chat_servers(self, chat_id, server_list):
        tasks = [self.get_server_status(server_address) for server_address in server_list]
        self.cache[chat_id] = [status for statuses in await asyncio.gather(*tasks) for status in statuses if statuses]

    async def check_servers_consistency(self, chat_id):
        if chat_id not in self.cache:
            self.cache[chat_id] = []
        
        server_list = self.servers.get(chat_id, [])
        server_statuses = self.cache.get(chat_id, [])
        
        if len(server_list) != len(server_statuses):
            await self.update_chat_servers(chat_id, server_list)

    @allowed_for(["chat_admins", "chat_owner"])
    @command("addmcserver")
    async def addserver_cmd(self, bot: Client, message: Message):
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply(self.S["mcaddserver"]["usage"])
            return

        server_address = parts[1]
        chat_id = str(message.chat.id)

        self.servers.setdefault(chat_id, [])

        if server_address in self.servers[chat_id]:
            await message.reply(self.S["mcaddserver"]["already_added"].format(server_address=server_address))
        else:
            self.servers[chat_id].append(server_address)
            self.save_servers()
            await message.reply(self.S["mcaddserver"]["added"].format(server_address=server_address))

    @allowed_for(["chat_admins", "chat_owner"])
    @command("delmcserver")
    async def delserver_cmd(self, bot: Client, message: Message):
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply(self.S["delmcserver"]["usage"])
            return

        server_address = parts[1]
        chat_id = str(message.chat.id)

        if chat_id not in self.servers or server_address not in self.servers[chat_id]:
            await message.reply(self.S["delmcserver"]["not_found"].format(server_address=server_address))
        else:
            self.servers[chat_id] = [s for s in self.servers[chat_id] if not s.startswith(server_address)]
            if not self.servers[chat_id]:
                del self.servers[chat_id]
            self.save_servers()
            await message.reply(self.S["delmcserver"]["deleted"].format(server_address=server_address))

    @command("mcstatus")
    async def status_cmd(self, bot: Client, message: Message):
        chat_id = str(message.chat.id)

        if not self.servers.get(chat_id):
            await message.reply(self.S["mcstatus"]["no_servers"])
            return

        wait_message = await message.reply(self.S["mcstatus"]["please_wait"])

        self.active_chats.add(chat_id)
        await self.check_servers_consistency(chat_id)
        server_statuses = self.cache.get(chat_id, [])

        refresh_button = InlineKeyboardMarkup([[InlineKeyboardButton(self.S["mcstatus"]["button"], callback_data="refresh_status")]])

        if all("🔴" in status for status in server_statuses):
            await wait_message.edit(self.S["mcstatus"]["no_statuses"], reply_markup=refresh_button)
        else:
            await wait_message.edit("\n".join(server_statuses), reply_markup=refresh_button)

    @command("mcinfo")
    async def mcinfo_cmd(self, bot: Client, message: Message):
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply(self.S["mcinfo"]["usage"])
            return

        server_address = parts[1]
        wait_message = await message.reply(self.S["mcstatus"]["please_wait"])

        server_statuses = await self.get_server_status(server_address)

        if all("🔴" in status for status in server_statuses):
            await wait_message.edit(self.S["mcinfo"]["no_status"])
        else:
            await wait_message.edit("\n".join(server_statuses))

    @callback_query(filters.regex("refresh_status"))
    async def refresh_status(self, bot: Client, callback_query):
        chat_id = str(callback_query.message.chat.id)

        message = callback_query.message
        await message.edit(self.S["mcstatus"]["please_wait"])

        await self.check_servers_consistency(chat_id)
        server_statuses = self.cache.get(chat_id, [])

        refresh_button = InlineKeyboardMarkup([[InlineKeyboardButton(self.S["mcstatus"]["button"], callback_data="refresh_status")]])

        if all("🔴" in status for status in server_statuses):
            await message.edit(self.S["mcstatus"]["no_statuses"], reply_markup=refresh_button)
        else:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updated_message = "\n".join(server_statuses) + "\n\n" + self.S["mcstatus"]["last_update"].format(current_time=current_time)
            await message.edit(updated_message, reply_markup=refresh_button)

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
                if java_status.players.max <= 20 and java_status.players.sample:
                    player_names = ", ".join([player.name for player in java_status.players.sample])
                    messages[-1] += self.S['server_status']['player_list'].format(player_names=player_names)
                return messages
            elif java_status:
                messages.append(self.S["server_status"]["java"].format(
                    server_address=server_address,
                    status_players_online=java_status.players.online,
                    status_players_max=java_status.players.max,
                    status_version_name=java_status.version.name
                ))
                if java_status.players.max <= 20 and java_status.players.sample:
                    player_names = ", ".join([player.name for player in java_status.players.sample])
                    messages[-1] += self.S['server_status']['player_list'].format(player_names=player_names)
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