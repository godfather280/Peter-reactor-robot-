

import asyncio
import json
import os
import time
from math import ceil

from telethon import TelegramClient, events
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji, MessageEntityMention

# =========================
# CONFIG
# =========================
API_ID = 26568356
API_HASH = '271624eab37e854cbd9ae06a855f23e9'
SESSION_FILE = 'my_session'        # Session filename (session-file auth)
ADMIN_IDS = [7733921002]          # <-- Replace with your Telegram user ID(s)

ACTIVE_FILE = "active_reactions.json"
PROGRESS_UPDATE_INTERVAL = 2.0    # seconds between editing the progress message
PER_MSG_DELAY = 0.35              # delay between reactions (safe default) 

# =========================
# GLOBALS
# =========================
active_reactions = {}   # user_id (int) -> {reaction, added_by, username, first_name}
processing_chats = set()
client = TelegramClient(SESSION_FILE, API_ID, API_HASH)


# =========================
# UTIL: persistence
# =========================
def load_active_reactions():
    global active_reactions
    if os.path.exists(ACTIVE_FILE):
        try:
            with open(ACTIVE_FILE, "r") as f:
                data = json.load(f)
                # keys may be strings; convert to int
                active_reactions = {int(k): v for k, v in data.items()}
                print(f"[Jarvis] Loaded {len(active_reactions)} active reaction(s).")
        except Exception as e:
            print(f"[Jarvis] Failed loading {ACTIVE_FILE}: {e}")
            active_reactions = {}
    else:
        active_reactions = {}


def save_active_reactions():
    try:
        with open(ACTIVE_FILE, "w") as f:
            # convert keys to strings for JSON
            json.dump({str(k): v for k, v in active_reactions.items()}, f, indent=2)
    except Exception as e:
        print(f"[Jarvis] Failed saving {ACTIVE_FILE}: {e}")


# =========================
# HELPERS
# =========================
async def safe_add_reaction(message, emoji):
    """Try to add reaction to a message. Silently continue on common failures."""
    try:
        me = await client.get_me()
        # don't react to our own messages
        if message.sender_id == me.id:
            return False

        # Build ReactionEmoji; Telethon expects ReactionEmoji(emoticon=...)
        reaction = ReactionEmoji(emoticon=emoji)
        await client(SendReactionRequest(peer=message.peer_id, msg_id=message.id, reaction=[reaction]))
        await asyncio.sleep(PER_MSG_DELAY)
        return True
    except Exception as exc:
        # Common reasons: reaction not allowed in channel, message deleted, invalid emoji, flood, etc.
        # We ignore and continue, but log unexpected ones.
        txt = str(exc)
        if "REACTION_INVALID" in txt or "MESSAGE_ID_INVALID" in txt or "MESSAGE_NOT_MODIFIED" in txt:
            return False
        # Print other exceptions for debugging
        print(f"[Jarvis] add_reaction error: {exc}")
        await asyncio.sleep(PER_MSG_DELAY)
        return False


def format_progress_bar(percent, length=24):
    filled = int(percent * length / 100)
    return "[" + "█" * filled + "░" * (length - filled) + "]"


def human_time(seconds):
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    mins = seconds // 60
    sec = seconds % 60
    if mins < 60:
        return f"{mins}m {sec}s"
    hrs = mins // 60
    mins = mins % 60
    return f"{hrs}h {mins}m"


# =========================
# COMMAND HANDLERS
# =========================
@client.on(events.NewMessage(pattern=r'\.react'))
async def react_handler(event):
    """Start reacting to all past + future messages of a user.
       Usage: reply to target's message with `.react ❤️`  OR mention them with `.react ❤️`
    """
    sender = event.sender_id
    if sender not in ADMIN_IDS:
        await event.reply("❌ You are not authorized to use this command.")
        return

    # get emoji
    parts = event.message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await event.reply("❌ Usage: `.react <emoji>` (reply to target user's message or mention them).")
        return
    emoji = parts[1].strip()

    # find target user (reply preferred)
    target = None
    if event.is_reply:
        reply_msg = await event.get_reply_message()
        if reply_msg:
            target = await reply_msg.get_sender()
    else:
        for ent in event.message.entities or []:
            if isinstance(ent, MessageEntityMention):
                uname = event.message.text[ent.offset + 1: ent.offset + ent.length]
                try:
                    target = await client.get_entity(uname)
                    break
                except:
                    continue

    if not target:
        await event.reply("❌ Couldn't find the target user. Reply to their message or mention them.")
        return

    user_id = target.id
    active_reactions[user_id] = {
        "reaction": emoji,
        "added_by": sender,
        "username": getattr(target, "username", None),
        "first_name": getattr(target, "first_name", "Unknown")
    }
    save_active_reactions()

    info_msg = await event.reply(f"🔥 Starting full past-scan + live-react for **{active_reactions[user_id]['first_name']}** with `{emoji}`\nScanning all chats... Please wait ⏳")
    # start the heavy operation in background so we don't block handlers
    asyncio.create_task(react_to_all_past_messages(user_id, emoji, info_msg))


@client.on(events.NewMessage(pattern=r'\.stop'))
async def stop_handler(event):
    """Stop reacting. Reply to a user's message to stop that user, or `.stop` alone to stop all."""
    sender = event.sender_id
    if sender not in ADMIN_IDS:
        await event.reply("❌ You are not authorized to use this command.")
        return

    # If reply -> stop that user
    if event.is_reply:
        reply_msg = await event.get_reply_message()
        if not reply_msg:
            await event.reply("❌ Reply to the target user's message to stop reacting to them.")
            return
        target = await reply_msg.get_sender()
        if not target:
            await event.reply("❌ Couldn't resolve user.")
            return
        uid = target.id
        if uid in active_reactions:
            name = active_reactions[uid]['first_name']
            del active_reactions[uid]
            save_active_reactions()
            await event.reply(f"🛑 Stopped reacting to **{name}**.")
        else:
            await event.reply("❌ That user was not being auto-reacted to.")
        return

    # No reply -> stop all
    count = len(active_reactions)
    active_reactions.clear()
    save_active_reactions()
    await event.reply(f"🛑 Stopped ALL reactions ({count} targets).")


@client.on(events.NewMessage(pattern=r'\.status'))
async def status_handler(event):
    sender = event.sender_id
    if sender not in ADMIN_IDS:
        await event.reply("❌ You are not authorized to use this command.")
        return

    if not active_reactions:
        await event.reply("No active reactions currently.")
        return

    lines = ["🤖 **Active Reactions:**\n"]
    for uid, data in active_reactions.items():
        lines.append(f"• {data['first_name']} (@{data['username'] or 'no_username'}) → {data['reaction']}")
    lines.append(f"\n**Total:** {len(active_reactions)}")
    await event.reply("\n".join(lines))


# =========================
# NEW MESSAGES -> instant reaction
# =========================
@client.on(events.NewMessage())
async def new_message_reactor(event):
    # instant react if sender is in active_reactions
    uid = event.message.sender_id
    if not uid:
        return
    if uid in active_reactions:
        emoji = active_reactions[uid]['reaction']
        await safe_add_reaction(event.message, emoji)


# =========================
# PAST SCAN with live progress (edits info_msg)
# =========================
async def react_to_all_past_messages(user_id, emoji, info_msg):
    """
    Scans every dialog and reacts to all messages by user_id.
    Edits info_msg periodically with progress + ETA.
    """
    try:
        dialogs = await client.get_dialogs()
    except Exception as e:
        await info_msg.edit(f"❌ Failed to get dialogs: {e}")
        return

    # Build list of (dialog_entity, count_estimate) by iterating once to count messages per dialog.
    # WARNING: Counting itself requires iter_messages; we'll instead iterate messages and react as we go,
    # keeping totals and using an exponential moving average to estimate remaining time.
    total_attempted = 0
    total_reacted = 0
    start_time = time.time()
    last_edit = 0.0
    msg_counts = []

    # First, count approximate total messages to set ETA:
    # We'll attempt a fast count per dialog by iterating messages but not reacting - limited to reasonable time.
    # Note: This counting step may be slow for huge accounts; it's optional. We'll do a light pass with limit=300 per dialog
    approx_total = 0
    for dialog in dialogs:
        try:
            # Quick count: up to 300 messages per dialog to estimate
            cnt = 0
            async for _ in client.iter_messages(dialog.entity, from_user=user_id, limit=300):
                cnt += 1
            if cnt:
                msg_counts.append((dialog, cnt))
                approx_total += cnt
        except Exception:
            continue

    # If approx_total == 0, we still want to try full scan (maybe user has messages beyond 300 per chat)
    # We'll iterate dialogs fully and react; use approx_total only for initial ETA estimate
    if approx_total == 0:
        # fallback: include all dialogs but with 1 estimate each so ETA shows something
        msg_counts = [(d, 1) for d in dialogs]
        approx_total = max(1, len(msg_counts))

    # Prepare ETA estimation variables
    avg_time_per_msg = PER_MSG_DELAY + 0.05  # initial guess (delay + overhead)
    total_estimated = approx_total

    # Edit initial info
    await info_msg.edit(f"🔍 Scanning all chats for past messages of **{active_reactions[user_id]['first_name']}**...\nEstimated messages (sample): {approx_total}\nEstimated time: {human_time(total_estimated * avg_time_per_msg)}\n\nProgress: {format_progress_bar(0)} 0%")

    # Now full scan & react
    # We'll go dialog by dialog and iterate all messages (limit=None) and react.
    for dialog, sample_cnt in msg_counts:
        chat = dialog.entity
        chat_name = getattr(chat, "title", getattr(chat, "first_name", str(dialog.id)))
        # Skip if already processing this chat by parallel task
        if dialog.id in processing_chats:
            continue
        processing_chats.add(dialog.id)
        try:
            async for message in client.iter_messages(chat, from_user=user_id, limit=None):
                # react
                total_attempted += 1
                t0 = time.time()
                reacted = await safe_add_reaction(message, emoji)
                took = time.time() - t0
                # update EMA for per-message time
                avg_time_per_msg = (avg_time_per_msg * 0.9) + (took * 0.1)
                if reacted:
                    total_reacted += 1

                # Update ETA & progress occasionally
                now = time.time()
                if now - last_edit >= PROGRESS_UPDATE_INTERVAL:
                    elapsed = now - start_time
                    # estimate remaining messages: we don't know exact total; use extrapolation:
                    # if approx_total > 0, scale based on ratio of dialogs scanned to sample dialogs
                    # Simpler: estimate remaining = max(0, approx_total - total_attempted)
                    remaining = max(0, total_estimated - total_attempted)
                    eta = remaining * avg_time_per_msg
                    percent = (total_attempted / max(1, total_estimated)) * 100
                    percent = min(100, int(percent))
                    bar = format_progress_bar(percent)
                    await info_msg.edit(
                        f"📂 Scanning: **{chat_name}**\nReactions done: {total_reacted}/{total_attempted}\nETA: {human_time(eta)}\n\nProgress: {bar} {percent}%"
                    )
                    last_edit = now

            # small pause between dialogs for safety
            await asyncio.sleep(1.2)
        except Exception as e:
            # log and continue
            print(f"[Jarvis] Error scanning {chat_name}: {e}")
            continue
        finally:
            processing_chats.discard(dialog.id)

    # Final: full exhaustive pass over all dialogs to catch messages beyond sampled dialogs
    # We'll check any dialog not fully scanned above
    # (This ensures we attempt to reach as many messages as allowed by server)
    for dialog in dialogs:
        chat = dialog.entity
        # try full iteration again, but skip duplicates handled earlier because iter_messages always returns full history
        # For safety, iterate again but continue silently if no new messages or errors.
        try:
            async for message in client.iter_messages(chat, from_user=user_id, limit=None):
                # we may be reprocessing same messages; safe_add_reaction will silently ignore if duplicate reaction or fail
                total_attempted += 1
                reacted = await safe_add_reaction(message, emoji)
                if reacted:
                    total_reacted += 1
                # light throttle
                await asyncio.sleep(0.2)
        except Exception:
            continue

    # Final edit
    await info_msg.edit(f"✅ Completed past-scan. Reacted to **{total_reacted}** messages from **{active_reactions[user_id]['first_name']}**.\nNow auto-reacting to new messages instantly with `{emoji}` 🎉")
    print(f"[Jarvis] Completed reacting to user {user_id}: {total_reacted} reactions.")


# =========================
# START
# =========================
async def main():
    load_active_reactions()
    print("[Jarvis] Starting client (session-file auth)...")
    await client.start()   # will use session file; if not present, starts login flow
    me = await client.get_me()
    print(f"[Jarvis] Logged in as {me.first_name} (@{getattr(me, 'username', 'no_username')})")
    print("[Jarvis] Bot is running. Commands: .react <emoji> (reply), .stop (reply or alone), .status")
    # keep running
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
