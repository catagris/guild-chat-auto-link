"""Discord bot: turns [Item Name] in bridged WoW guild chat into Wowhead item embeds.

Run:   DISCORD_TOKEN=... python bot.py
Test:  python bot.py --test "Chris: [Murloc Scale Belt]"   (no Discord needed)
"""

import asyncio
import html
import json
import os
import re
import sys
import time
from urllib.parse import quote

import aiohttp

# Wowhead site section: "forever", "classic", "tbc", ... or "" for retail.
WOWHEAD_VERSION = os.environ.get("WOWHEAD_VERSION", "forever").strip("/")
# Comma-separated channel IDs to watch. Empty = every channel the bot can see.
CHANNEL_IDS = {int(c) for c in os.environ.get("CHANNEL_IDS", "").replace(" ", "").split(",") if c}
# Where to post the embeds. Default is a reply in the same channel; set one of
# these when that is blocked (WoW guild-chat-linked channels reject bot posts).
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()
OUTPUT_CHANNEL_ID = int(os.environ.get("OUTPUT_CHANNEL_ID", "").strip() or 0)
MAX_ITEMS_PER_MESSAGE = int(os.environ.get("MAX_ITEMS_PER_MESSAGE", "5"))
CACHE_FILE = os.environ.get("CACHE_FILE", "item_cache.json")
MISS_TTL = 6 * 3600  # re-check unknown names after this long (new items get added)

PREFIX = f"/{WOWHEAD_VERSION}" if WOWHEAD_VERSION else ""
SEARCH_URL = f"https://www.wowhead.com{PREFIX}/search/suggestions-template?q={{q}}"
TOOLTIP_URL = f"https://nether.wowhead.com{PREFIX}/tooltip/item/{{id}}"
ITEM_URL = f"https://www.wowhead.com{PREFIX}/item={{id}}"
ICON_URL = "https://wow.zamimg.com/images/wow/icons/large/{icon}.jpg"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; guild-chat-auto-link)"}

BRACKET_RE = re.compile(r"\[([^\[\]\n]{3,80})\]")
QUALITY_COLORS = {
    0: 0x9D9D9D, 1: 0xFFFFFF, 2: 0x1EFF00, 3: 0x0070DD,
    4: 0xA335EE, 5: 0xFF8000, 6: 0xE6CC80, 7: 0x00CCFF,
}
ITEM_TYPE = 3  # Wowhead's type id for items


def tooltip_to_text(tooltip_html: str, name: str) -> str:
    """Flatten Wowhead's tooltip HTML into Discord markdown."""
    t = re.sub(r"<!--.*?-->", "", tooltip_html, flags=re.S)
    for coin, suffix in (("gold", "g"), ("silver", "s"), ("copper", "c")):
        t = re.sub(rf'<span class="money{coin}">(\d+)</span>', rf"\1{suffix}", t)
    t = re.sub(r"</td>\s*<th[^>]*>", " · ", t)          # "Waist · Leather"
    t = re.sub(r"<br\s*/?>|</tr>|</?table[^>]*>|</?div[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    lines = [html.unescape(line).strip(" · ") for line in t.split("\n")]
    lines = [line for line in lines if line]
    if lines and lines[0].lower() == name.lower():
        lines = lines[1:]
    return "\n".join(lines)[:2000]


class ItemResolver:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.sem = asyncio.Semaphore(3)
        self.cache: dict[str, dict] = {}
        try:
            with open(CACHE_FILE) as f:
                self.cache = json.load(f)
        except (OSError, ValueError):
            pass

    def _save(self):
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(self.cache, f)
        except OSError:
            pass

    async def _get_json(self, url: str):
        async with self.sem, self.session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return None
            return await r.json(content_type=None)

    async def resolve(self, name: str) -> dict | None:
        """Exact (case-insensitive) item name -> {id, name, quality, icon, text}, or None."""
        key = name.strip().lower()
        hit = self.cache.get(key)
        if hit and (hit.get("id") or time.time() - hit.get("at", 0) < MISS_TTL):
            return hit if hit.get("id") else None

        data = await self._get_json(SEARCH_URL.format(q=quote(name.strip())))
        if data is None:
            return None  # lookup failed; don't cache so we retry next time
        match = next(
            (r for r in data.get("results", [])
             if r.get("type") == ITEM_TYPE and r.get("name", "").lower() == key),
            None,
        )
        if not match:
            self.cache[key] = {"at": time.time()}
            self._save()
            return None

        item = {"id": match["id"], "name": match["name"],
                "quality": match.get("quality", 1), "icon": match.get("icon"), "text": ""}
        tip = await self._get_json(TOOLTIP_URL.format(id=item["id"]))
        if tip:
            item["quality"] = tip.get("quality", item["quality"])
            item["icon"] = tip.get("icon") or item["icon"]
            item["text"] = tooltip_to_text(tip.get("tooltip", ""), item["name"])
        self.cache[key] = item
        self._save()
        return item

    async def resolve_message(self, text: str) -> list[dict]:
        names = list(dict.fromkeys(BRACKET_RE.findall(text)))[:MAX_ITEMS_PER_MESSAGE]
        found = await asyncio.gather(*(self.resolve(n) for n in names))
        seen, items = set(), []
        for item in found:
            if item and item["id"] not in seen:
                seen.add(item["id"])
                items.append(item)
        return items


def run_bot():
    import discord

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    resolver: ItemResolver | None = None

    def make_embed(item: dict) -> "discord.Embed":
        embed = discord.Embed(
            title=item["name"],
            url=ITEM_URL.format(id=item["id"]),
            description=item["text"] or None,
            color=QUALITY_COLORS.get(item["quality"], 0xFFFFFF),
        )
        if item.get("icon"):
            embed.set_thumbnail(url=ICON_URL.format(icon=item["icon"]))
        return embed

    @client.event
    async def on_ready():
        nonlocal resolver
        if resolver is None:
            resolver = ItemResolver(aiohttp.ClientSession())
        print(f"Logged in as {client.user}; watching "
              f"{'channels ' + str(sorted(CHANNEL_IDS)) if CHANNEL_IDS else 'all channels'}", flush=True)

    @client.event
    async def on_message(message: "discord.Message"):
        # The guild-chat bridge posts as a bot/webhook, so only skip ourselves.
        if message.author.id == client.user.id or resolver is None:
            return
        if CHANNEL_IDS and message.channel.id not in CHANNEL_IDS:
            return
        text = "\n".join([message.content or ""] + [e.description or "" for e in message.embeds])
        if "[" not in text:
            return
        try:
            items = await resolver.resolve_message(text)
            if not items:
                return
            embeds = [make_embed(i) for i in items]
            # Discord blocks bots from posting in WoW guild-chat-linked channels
            # (error 20062), so a webhook or a separate channel can be used instead.
            if WEBHOOK_URL:
                hook = discord.Webhook.from_url(WEBHOOK_URL, session=resolver.session)
                await hook.send(embeds=embeds, username="Wowhead")
            elif OUTPUT_CHANNEL_ID:
                out = client.get_channel(OUTPUT_CHANNEL_ID) or await client.fetch_channel(OUTPUT_CHANNEL_ID)
                await out.send(content=message.jump_url, embeds=embeds)
            else:
                await message.reply(embeds=embeds, mention_author=False)
        except Exception as e:  # never let one bad message kill the bot
            print(f"error handling message {message.id}: {e!r}", flush=True)

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        sys.exit("Set DISCORD_TOKEN (see README.md)")
    client.run(token)


async def run_test(text: str):
    async with aiohttp.ClientSession() as session:
        items = await ItemResolver(session).resolve_message(text)
        if not items:
            print("(no items matched - bot would stay silent)")
        for i in items:
            print(f"== {i['name']}  (quality {i['quality']})\n   {ITEM_URL.format(id=i['id'])}\n   "
                  f"{ICON_URL.format(icon=i['icon'])}\n{i['text']}\n")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--test":
        asyncio.run(run_test(" ".join(sys.argv[2:])))
    else:
        run_bot()
