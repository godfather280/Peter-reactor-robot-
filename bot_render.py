from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityMention
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
import asyncio
import json
import os
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment variables
API_ID = os.getenv('API_ID', '26568356')
API_HASH = os.getenv('API_HASH', '271624eab37e854cbd9ae06a855f23e9')
PHONE_NUMBER = os.getenv('PHONE_NUMBER', '19312975367')
SESSION_FILE = os.getenv('SESSION_FILE', 'my_session')

# Store active reaction targets
active_reactions = {}
processing_chats = set()

class ReactionBot:
    def __init__(self):
        self.client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        self.setup_handlers()
    
    def setup_handlers(self):
        @self.client.on(events.NewMessage(pattern='\.react'))
        async def react_handler(event):
            """Handle .react command to start reacting to user's messages in ALL chats"""
            if not event.is_reply and not event.message.entities:
                await event.reply("Please reply to a user's message or mention a user with .react")
                return
            
            # Get the target user
            target_user = None
            
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_user = await reply_msg.get_sender()
            else:
                # Check for mentions
                for entity in event.message.entities:
                    if isinstance(entity, MessageEntityMention):
                        mention_text = event.message.text[entity.offset:entity.offset+entity.length]
                        if mention_text.startswith('@'):
                            username = mention_text[1:]
                            try:
                                target_user = await self.client.get_entity(username)
                                break
                            except:
                                continue
            
            if not target_user:
                await event.reply("Could not find the target user. Please make sure you're replying to their message or mentioning them correctly.")
                return
            
            # Extract reaction from command
            command_parts = event.message.text.split(' ', 1)
            if len(command_parts) < 2:
                await event.reply("Please specify a reaction emoji. Usage: .react 🎉 (reply to user or mention)")
                return
            
            reaction_emoji = command_parts[1].strip()
            
            # Store the reaction target (global - no chat restriction)
            user_id = target_user.id
            
            active_reactions[user_id] = {
                'reaction': reaction_emoji,
                'added_by': event.sender_id,
                'username': getattr(target_user, 'username', None),
                'first_name': getattr(target_user, 'first_name', 'Unknown')
            }
            
            # Save immediately
            self.save_reactions()
            
            await event.reply(f"✅ Now reacting to {target_user.first_name}'s messages in ALL chats with {reaction_emoji}")
            
            # Don't react to past messages on Render to avoid timeouts
            logger.info(f"Started reacting to user {target_user.first_name} with {reaction_emoji}")
        
        @self.client.on(events.NewMessage(pattern='\.stop'))
        async def stop_handler(event):
            """Handle .stop command to stop reacting to a user globally"""
            if not event.is_reply and not event.message.entities:
                # Stop all global reactions
                stopped_count = len(active_reactions)
                active_reactions.clear()
                self.save_reactions()
                
                await event.reply(f"✅ Stopped ALL reactions globally ({stopped_count} targets)")
                return
            
            # Stop reaction for specific user globally
            target_user = None
            
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_user = await reply_msg.get_sender()
            else:
                # Check for mentions
                for entity in event.message.entities:
                    if isinstance(entity, MessageEntityMention):
                        mention_text = event.message.text[entity.offset:entity.offset+entity.length]
                        if mention_text.startswith('@'):
                            username = mention_text[1:]
                            try:
                                target_user = await self.client.get_entity(username)
                                break
                            except:
                                continue
            
            if not target_user:
                await event.reply("Could not find the target user. Please make sure you're replying to their message or mentioning them correctly.")
                return
            
            user_id = target_user.id
            
            if user_id in active_reactions:
                user_info = active_reactions[user_id]['first_name']
                del active_reactions[user_id]
                self.save_reactions()
                await event.reply(f"✅ Stopped reacting to {user_info}'s messages in ALL chats")
            else:
                await event.reply(f"❌ No active reaction found for {target_user.first_name}")
        
        @self.client.on(events.NewMessage())
        async def message_handler(event):
            """React to new messages from targeted users in ANY chat"""
            if not event.message.sender_id:
                return
            
            user_id = event.message.sender_id
            
            if user_id in active_reactions:
                reaction_emoji = active_reactions[user_id]['reaction']
                await self.add_reaction(event.message, reaction_emoji)
        
        @self.client.on(events.NewMessage(pattern='\.status'))
        async def status_handler(event):
            """Show current active reactions"""
            if not active_reactions:
                await event.reply("❌ No active reactions")
                return
            
            status_text = "🤖 **Active Reactions:**\n\n"
            for user_id, data in active_reactions.items():
                username = data['username']
                name = data['first_name']
                reaction = data['reaction']
                status_text += f"• {name} (@{username if username else 'no_username'}) - {reaction}\n"
            
            status_text += f"\n**Total:** {len(active_reactions)} users"
            await event.reply(status_text)
    
    async def add_reaction(self, message, reaction_emoji):
        """Add reaction to a message"""
        try:
            # Skip if we're the sender to avoid reacting to our own messages
            if message.sender_id == await self.client.get_me():
                return
                
            reaction = ReactionEmoji(emoticon=reaction_emoji)
            await self.client(SendReactionRequest(
                peer=message.peer_id,
                msg_id=message.id,
                reaction=[reaction]
            ))
            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)
        except Exception as e:
            # Ignore common errors like message not found, reaction not allowed, etc.
            if "MESSAGE_NOT_MODIFIED" not in str(e) and "MESSAGE_ID_INVALID" not in str(e):
                logger.error(f"Error adding reaction: {e}")
    
    def save_reactions(self):
        """Save active reactions to file"""
        try:
            with open('active_reactions.json', 'w') as f:
                json.dump(active_reactions, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving reactions: {e}")
    
    def load_reactions(self):
        """Load active reactions from file"""
        global active_reactions
        try:
            if os.path.exists('active_reactions.json'):
                with open('active_reactions.json', 'r') as f:
                    loaded = json.load(f)
                    # Convert string keys back to integers
                    active_reactions = {int(k): v for k, v in loaded.items()}
                logger.info(f"Loaded {len(active_reactions)} active reactions")
        except Exception as e:
            logger.error(f"Error loading reactions: {e}")
            active_reactions = {}
    
    async def start(self):
        """Start the bot"""
        logger.info("🔐 Logging in to Telegram...")
        
        try:
            await self.client.start(
                phone=PHONE_NUMBER
            )
            
            me = await self.client.get_me()
            logger.info(f"✅ Logged in as: {me.first_name} (@{me.username})")
            
            self.load_reactions()
            
            logger.info("\n🤖 Bot started! Listening for messages...")
            logger.info("Available commands:")
            logger.info(".react 🎉 (reply to user) - React to user's messages in ALL chats")
            logger.info(".stop (reply to user) - Stop reacting to user globally")
            logger.info(".stop - Stop ALL reactions")
            logger.info(".status - Show active reactions")
            
            # Send a startup message to yourself
            try:
                await self.client.send_message(me.id, "🤖 Bot started successfully on Render!")
            except:
                pass
            
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise

async def main():
    bot = ReactionBot()
    await bot.start()

if __name__ == '__main__':
    # Keep the bot running with error handling
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            logger.info("Restarting in 10 seconds...")
            time.sleep(10)
