# MinecraftServerStatus
### Description:
This module for [PBModular](https://github.com/PBModular/bot) is designed to request current data from Minecraft Servers (supports both Bedrock and Java editions). It can display server status, online players, version, and more.

### Installation
-   <code>/mod_install https://github.com/PBModular/MinecraftServerStatus</code>

### Usage

**1. Add a server to the chat's tracking list:**
   -   Command: <code>/addmcserver <server_address>[:port]</code>
   -   Description: Adds a Minecraft server to the list of servers monitored for this chat.
   -   *Note: This command can only be used by chat admins or the owner.*

**2. Remove a server from the chat's tracking list:**
   -   Command: <code>/delmcserver <server_address>[:port]</code>
   -   *Note: This command can only be used by chat admins or the owner.*

**3. Get the status of all tracked servers in the chat:**
   -   Command: <code>/mcstatus</code>
   -   Description: Displays the current status of all Minecraft servers added to this chat. Includes an inline button to refresh the status.

**4. Get detailed information for a specific server (not necessarily tracked):**
   -   Command: <code>/mcinfo <server_address>[:port]</code>
   -   Description: Shows detailed status information for a specific Minecraft server, whether it's tracked in the chat or not.
