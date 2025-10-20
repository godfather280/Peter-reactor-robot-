from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityMention
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
import asyncio
import json
import os
import time
import logging
import sys
import types

# --- Patch for imghdr (removed in Python 3.13) ---
if 'imghdr' not in sys.modules:
    imghdr = types.ModuleType("imghdr")
    imghdr.what = lambda file=None, h=None: None
    sys.modules['imghdr'] = imghdr

# --- Logging setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
API_ID = os.getenv('API_ID', '26568356')
API_HASH = os.getenv('API_HASH', '271624eab37e854cbd9ae06a855f23e9')
PHONE_NUMBER = os.getenv('PHONE_NUMBER', '19312975367')
SESSION_FILE = os.getenv('SESSION_FILE', 'my_session')

# 👑 Admin ID(s)
# Replace with your actual Telegram numeric user ID, or add multiple in a list
# You can get your ID by messaging @userinfobot on Telegram
ADMIN_IDS = [7733921002]  # 👈 Replace this with your actual Telegram ID(s)

# --- Reaction storage ---
active_reactions = {}
processing_chats = set()


class ReactionBot:
    def __init__(self):
        self.client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        self.setup_handlers()

    # --- Helper: Check if user is admin ---
    async def is_admin(self, event):
        sender = await event.get_sender()
        return sender.id in ADMIN_IDS

    def setup_handlers(self):
from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityMention
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
import asyncio
import json
import os
import time
import logging
import sys
import types

# --- Patch for imghdr (removed in Python 3.13) ---
if 'imghdr' not in sys.modules:
    imghdr = types.ModuleType("imghdr")
    imghdr.what = lambda file=None, h=None: None
    sys.modules['imghdr'] = imghdr

# --- Logging setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
API_ID = os.getenv('API_ID', '26568356')
API_HASH = os.getenv('API_HASH', '271624eab37e854cbd9ae06a855f23e9')
PHONE_NUMBER = os.getenv('PHONE_NUMBER', '19312975367')
SESSION_FILE = os.getenv('SESSION_FILE', 'my_session')

# 👑 Admin ID(s)
# Replace with your actual Telegram numeric user ID, or add multiple in a list
# You can get your ID by messaging @userinfobot on Telegram
ADMIN_IDS = [123456789]  # 👈 Replace this with your actual Telegram ID(s)

# --- Reaction storage ---
active_reactions = {}
processing_chats = set()


class ReactionBot:
    def __init__(self):
        self.client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        self.setup_handlers()

    # --- Helper: Check if user is admin ---
    async def is_admin(self, event):
        sender = await event.get_sender()
        return sender.id in ADMIN_IDS

    def setup_handlers(self):
        @self.client.on(events.NewMessage(pattern=r'\.react'))
        async def react_handler(event):
            """Start reacting to user's messages"""
            if not await self.is_admin(event):
                await event.reply("🚫 You are not authorized to use this command.")
                return

            if not event.is_reply and not event.message.entities:
                await event.reply("Please reply to a user's message or mention a user with `.react`")
                return

            target_user = None
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_user = await reply_msg.get_sender()
            else:
                for entity in event.message.entities or []:
                    if isinstance(entity, MessageEntityMention):
                        mention_text = event.message.text[entity.offset:entity.offset + entity.length]
                        if mention_text.startswith('@'):
                            username = mention_text[1:]
                            try:
                                target_user = await self.client.get_entity(username)
                                break
                            except Exception:
                                continue

            if not target_user:
                await event.reply("Could not find the target user. Reply or mention them correctly.")
                return

            command_parts = event.message.text.split(' ', 1)
            if len(command_parts) < 2:
                await event.reply("Usage: `.react 🎉` (reply to user or mention)")
                return

            reaction_emoji = command_parts[1].strip()
            user_id = target_user.id

            active_reactions[user_id] = {
                'reaction': reaction_emoji,
                'added_by': event.sender_id,
                'username': getattr(target_user, 'username', None),
                'first_name': getattr(target_user, 'first_name', 'Unknown')
            }

            self.save_reactions()
            await event.reply(f"✅ Now reacting to {target_user.first_name}'s messages with {reaction_emoji}")
            logger.info(f"Started reacting to user {target_user.first_name} ({user_id}) with {reaction_emoji}")

        @self.client.on(events.NewMessage(pattern=r'\.stop'))
        async def stop_handler(event):
            """Stop reacting"""
            if not await self.is_admin(event):
                await event.reply("🚫 You are not authorized to use this command.")
                return

            if not event.is_reply and not event.message.entities:
                stopped_count = len(active_reactions)
                active_reactions.clear()
                self.save_reactions()
                await event.reply(f"✅ Stopped ALL reactions ({stopped_count} targets)")
                return

            target_user = None
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_user = await reply_msg.get_sender()
            else:
                for entity in event.message.entities or []:
                    if isinstance(entity, MessageEntityMention):
                        mention_text = event.message.text[entity.offset:entity.offset + entity.length]
                        if mention_text.startswith('@'):
                            username = mention_text[1:]
                            try:
                                target_user = await self.client.get_entity(username)
                                break
                            except Exception:
                                continue

            if not target_user:
                await event.reply("Could not find the user to stop reacting to.")
                return

            user_id = target_user.id
            if user_id in active_reactions:
                user_info = active_reactions[user_id]['first_name']
                del active_reactions[user_id]
                self.save_reactions()
                await event.reply(f"✅ Stopped reacting to {user_info}")
            else:
                await event.reply(f"❌ No active reaction for {target_user.first_name}")

        @self.client.on(events.NewMessage())
        async def message_handler(event):
            """React to new messages from targeted users"""
            if not event.message or not event.message.sender_id:
                return

            user_id = event.message.sender_id
            if user_id in active_reactions:
                reaction_emoji = active_reactions[user_id]['reaction']
                await self.add_reaction(event.message, reaction_emoji)

        @self.client.on(events.NewMessage(pattern=r'\.status'))
        async def status_handler(event):
            """Show active reactions"""
            if not await self.is_admin(event):
                await event.reply("🚫 You are not authorized to use this command.")
                return

            if not active_reactions:
                await event.reply("❌ No active reactions")
                return

            status_text = "🤖 **Active Reactions:**\n\n"
            for user_id, data in active_reactions.items():
                username = data['username']
                name = data['first_name']
                reaction = data['reaction']
                status_text += f"• {name} (@{username or 'no_username'}) - {reaction}\n"

            status_text += f"\n**Total:** {len(active_reactions)} users"
            await event.reply(status_text)

    async def add_reaction(self, message, reaction_emoji):
        """Add reaction to a message"""
        try:
            me = await self.client.get_me()
            if message.sender_id == me.id:
                return  # Skip our own messages

            reaction = ReactionEmoji(emoticon=reaction_emoji)
            await self.client(SendReactionRequest(
                peer=message.peer_id,
                msg_id=message.id,
                reaction=[reaction]
            ))
            await asyncio.sleep(0.5)
        except Exception as e:
            if "MESSAGE_NOT_MODIFIED" not in str(e) and "MESSAGE_ID_INVALID" not in str(e):
                logger.error(f"Error adding reaction: {e}")

    def save_reactions(self):
        try:
            with open('active_reactions.json', 'w') as f:
                json.dump(active_reactions, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving reactions: {e}")

    def load_reactions(self):
        global active_reactions
        try:
            if os.path.exists('active_reactions.json'):
                with open('active_reactions.json', 'r') as f:
                    loaded = json.load(f)
                    active_reactions = {int(k): v for k, v in loaded.items()}
                logger.info(f"Loaded {len(active_reactions)} active reactions")
        except Exception as e:
            logger.error(f"Error loading reactions: {e}")
            active_reactions = {}

    async def start(self):
        logger.info("🔐 Logging in to Telegram...")
        try:
            await self.client.start(phone=PHONE_NUMBER)
            me = await self.client.get_me()
            logger.info(f"✅ Logged in as: {me.first_name} (@{me.username})")

            self.load_reactions()
            logger.info("🤖 Bot started! Listening for messages...")

            try:
                await self.client.send_message(me.id, "🤖 Bot started successfully!")
            except Exception:
                pass

            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise


async def main():
    bot = ReactionBot()
    await bot.start()


if __name__ == '__main__':
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            logger.info("Restarting in 10 seconds...")
            time.sleep(10)     @self.client.on(events.NewMessage(pattern=r'\.react'))
        async def react_handler(event):
            """Start reacting to user's messages"""
            if not await self.is_admin(event):
                await event.reply("🚫 You are not authorized to use this command.")
                return

            if not event.is_reply and not event.message.entities:
                await event.reply("Please reply to a user's message or mention a user with `.react`")
                return

            target_user = None
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_user = await reply_msg.get_sender()
            else:
                for entity in event.message.entities or []:
                    if isinstance(entity, MessageEntityMention):
                        mention_text = event.message.text[entity.offset:entity.offset + entity.length]
                        if mention_text.startswith('@'):
                            username = mention_text[1:]
                            try:
                                target_user = await self.client.get_entity(username)
                                break
                            except Exception:
                                continue

            if not target_user:
                await event.reply("Could not find the target user. Reply or mention them correctly.")
                return

            command_parts = event.message.text.split(' ', 1)
            if len(command_parts) < 2:
                await event.reply("Usage: `.react 🎉` (reply to user or mention)")
                return

            reaction_emoji = command_parts[1].strip()
            user_id = target_user.id

            active_reactions[user_id] = {
                'reaction': reaction_emoji,
                'added_by': event.sender_id,
                'username': getattr(target_user, 'username', None),
                'first_name': getattr(target_user, 'first_name', 'Unknown')
            }

            self.save_reactions()
            await event.reply(f"✅ Now reacting to {target_user.first_name}'s messages with {reaction_emoji}")
            logger.info(f"Started reacting to user {target_user.first_name} ({user_id}) with {reaction_emoji}")

        @self.client.on(events.NewMessage(pattern=r'\.stop'))
        async def stop_handler(event):
            """Stop reacting"""
            if not await self.is_admin(event):
                await event.reply("🚫 You are not authorized to use this command.")
                return

            if not event.is_reply and not event.message.entities:
                stopped_count = len(active_reactions)
                active_reactions.clear()
                self.save_reactions()
                await event.reply(f"✅ Stopped ALL reactions ({stopped_count} targets)")
                return

            target_user = None
      if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_user = await reply_msg.get_sender()
            else:
                for entity in event.message.entities or []:
                    if isinstance(entity, MessageEntityMention):
                        mention_text = event.message.text[entity.offset:entity.offset + entity.length]
                        if mention_text.startswith('@'):
                            username = mention_text[1:]
                            try:
                                target_user = await self.client.get_entity(username)
                                break
                            except Exception:
                                continue

            if not target_user:
                await event.reply("Could not find the user to stop reacting to.")
                return

            user_id = target_user.id
            if user_id in active_reactions:
                user_info = active_reactions[user_id]['first_name']
                del active_reactions[user_id]
                self.save_reactions()
                await event.reply(f"✅ Stopped reacting to {user_info}")
            else:
                await event.reply(f"❌ No active reaction for {target_user.first_name}")

        @self.client.on(events.NewMessage())
        async def message_handler(event):
            """React to new messages from targeted users"""
            if not event.message or not event.message.sender_id:
                return

            user_id = event.message.sender_id
            if user_id in active_reactions:
                reaction_emoji = active_reactions[user_id]['reaction']
                await self.add_reaction(event.message, reaction_emoji)

        @self.client.on(events.NewMessage(pattern=r'\.status'))
        async def status_handler(event):
            """Show active reactions"""
            if not await self.is_admin(event):
                await event.reply("🚫 You are not authorized to use this command.")
                return

            if not active_reactions:
                await event.reply("❌ No active reactions")
                return

            status_text = "🤖 **Active Reactions:**\n\n"
            for user_id, data in active_reactions.items():
                username = data['username']
                name = data['first_name']
                reaction = data['reaction']
                status_text += f"• {name} (@{username or 'no_username'}) - {reaction}\n"

            status_text += f"\n**Total:** {len(active_reactions)} users"
            await event.reply(status_text)

    async def add_reaction(self, message, reaction_emoji):
        """Add reaction to a message"""
        try:
            me = await self.client.get_me()
            if message.sender_id == me.id:
