import json
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from base.module import BaseModule, command, allowed_for
from mcstatus import BedrockServer, JavaServer
from mcstatus.status_response import BedrockStatusResponse, JavaStatusResponse

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

        if chat_id not in self.servers:
            self.servers[chat_id] = []

        if any(server_ip == s.split(":")[0] for s in self.servers[chat_id]):
            await message.reply(self.S["mcaddserver"]["already_added"].format(server_address=server_ip))
        else:
            self.servers[chat_id].append(server_address)
            self.save_servers()
            await message.reply(self.S["mcaddserver"]["added"].format(server_address=server_address))

    @command("mcstatus")
    async def status_cmd(self, bot: Client, message: Message):
        chat_id = str(message.chat.id)

        if chat_id not in self.servers or not self.servers[chat_id]:
            await message.reply(self.S["mcstatus"]["no_servers"])
            return

        status_messages = await asyncio.gather(*[self.get_server_status(server_address) for server_address in self.servers[chat_id]])
        server_statuses = [msg for msg in status_messages if msg is not None]

        if all("🔴" in status for status in server_statuses):
            await message.reply(self.S["mcstatus"]["no_statuses"])
        else:
            await message.reply("\n".join(server_statuses))

    async def get_server_status(self, server_address: str) -> str:
        try:
            status = await self.handle_exceptions(
                *(
                    await asyncio.wait(
                        {
                            asyncio.create_task(self.handle_java(server_address)),
                            asyncio.create_task(self.handle_bedrock(server_address)),
                        },
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                )
            )

            if status is None:
                return self.S["server_status"]["server_offline"].format(server_address=server_address)
            elif isinstance(status, BedrockStatusResponse):
                return self.S["server_status"]["bedrock"].format(server_address=server_address, status_players_online=status.players.online, 
                                                                status_players_max=status.players.max, status_version_name=status.version.name)
            elif isinstance(status, JavaStatusResponse):
                return self.S["server_status"]["java"].format(server_address=server_address, status_players_online=status.players.online, 
                                                            status_players_max=status.players.max, status_version_name=status.version.name)
                
        except Exception as e:
            return self.logger.error(f"Failed to retrieve status for {server_address}: {str(e)}")


    async def handle_exceptions(self, done: set[asyncio.Task], pending: set[asyncio.Task]) -> JavaStatusResponse | BedrockStatusResponse | None:
        if len(done) == 0:
            return None

        for task in done:
            if task.exception() is None:
                for pending_task in pending:
                    pending_task.cancel()
                return task.result()
            
        self.logger.error("No tasks were successful. Server might be offline.")
        return None
    
    async def handle_java(self, server_address: str) -> JavaStatusResponse:
        try:
            return await (await JavaServer.async_lookup(server_address)).async_status()
        except Exception:
            pass

    async def handle_bedrock(self, server_address: str) -> BedrockStatusResponse:
        try:
            return await BedrockServer.lookup(server_address).async_status()
        except Exception:
            pass