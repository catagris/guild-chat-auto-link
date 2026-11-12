# Guild Chat Auto Link

A small Discord bot for guilds that bridge World of Warcraft guild chat into
Discord. Item links arrive in Discord as plain `[Item Name]` text; this bot
looks each one up on Wowhead and posts an embed with the icon, quality colour,
tooltip stats and a link to the item page.

```
Chris: [Murloc Scale Belt]

  Murloc Scale Belt                 -> wowhead.com/forever/item=5780
  Item Level 18
  Binds when equipped
  Waist · Leather
  42 Armor
  +2 Strength
  +3 Agility
  Durability 20 / 20
  Requires Level 13
  Sell Price: 2s 60c
```

- Only exact item-name matches get a response, so `[lol]` is ignored.
- Up to 5 items per message, combined into one post.
- Lookups are cached on disk.

Built for WoW Forever; set `WOWHEAD_VERSION` for other game versions.

## 1. Create the Discord bot

1. https://discord.com/developers/applications -> **New Application** -> **Bot**.
2. Enable **Message Content Intent**.
3. **Reset Token** and copy the token.
4. **OAuth2 -> URL Generator**: scope `bot`; permissions View Channels, Send
   Messages, Embed Links, Read Message History. Open the URL and add the bot to
   your server.
5. Get the guild-chat channel's ID: Discord Settings -> Advanced -> Developer
   Mode, then right-click the channel -> Copy Channel ID.

## 2. Configure

| Variable | Required | Meaning |
| --- | --- | --- |
| `DISCORD_TOKEN` | yes | Bot token from step 1. |
| `CHANNEL_IDS` | no | Channel ID(s) to watch, comma separated. Empty = all channels. |
| `WOWHEAD_VERSION` | no | Wowhead section: `forever` (default), `classic`, `tbc`, ... Empty = retail. |
| `WEBHOOK_URL` | no | Post through this webhook instead of replying. |
| `OUTPUT_CHANNEL_ID` | no | Post in this other channel instead, with a link back to the message. |
| `MAX_ITEMS_PER_MESSAGE` | no | Default 5. |

### Battle.net-linked channels

Discord does not let bots post in channels linked to WoW guild chat through
Battle.net. The bot can read them, but replies fail with
`403 ... error code: 20062`
([discord-api-docs#8628](https://github.com/discord/discord-api-docs/issues/8628),
closed as by design). Use one of:

- `WEBHOOK_URL`: create a webhook on the linked channel (Edit Channel ->
  Integrations -> Webhooks) and paste its URL. Posts appear in Discord only,
  not in game.
- `OUTPUT_CHANNEL_ID`: post the embeds in an ordinary channel such as
  `#item-links`.

If neither is set the bot replies directly, which is right for normal channels.

## 3. Run

### Docker Compose

```sh
cp .env.example .env   # fill in the values
docker compose up -d --build
```

### Portainer / TrueNAS (no build step)

Copy `bot.py` and `requirements.txt` to a folder on the server, then add a
stack:

```yaml
services:
  guild-chat-auto-link:
    image: python:3.13-slim
    restart: unless-stopped
    working_dir: /app
    volumes:
      - /path/on/server/guild-chat-auto-link:/app
    environment:
      DISCORD_TOKEN: "paste-token-here"
      CHANNEL_IDS: "paste-channel-id-here"
      WEBHOOK_URL: "paste-webhook-url-here"
      WOWHEAD_VERSION: forever
      PYTHONUNBUFFERED: "1"
    command: sh -c "pip install -q -r requirements.txt && python bot.py"
```

`WEBHOOK_URL` is for a Battle.net-linked channel. Swap it for
`OUTPUT_CHANNEL_ID` to post in another channel, or remove it for an ordinary
channel, where the bot replies directly.

Changing a setting means updating the stack; restarting the container only
reloads `bot.py`.

## Test without Discord

```sh
uv run --with aiohttp bot.py --test "Chris: [Murloc Scale Belt] [lol]"
```

## Notes

Item data comes from Wowhead's search-suggestion and tooltip endpoints, which
are not an official API and may change.

## License

Copyright (c) 2026 William Wilkins. Licensed under the [GNU AGPL-3.0](LICENSE): you may use and modify this, but anything built on it, including a hosted version, must publish its source under the same licence.
