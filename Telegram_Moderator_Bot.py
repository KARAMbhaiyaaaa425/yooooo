from telegram import Update
from telegram import Update, ChatPermissions
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ChatMemberHandler, CallbackQueryHandler, ChatJoinRequestHandler, filters
from telegram.ext import ContextTypes
import asyncio
import logging
import os
import re
import sqlite3
import threading
import time


DB_FILE = os.path.join(os.path.dirname(__file__), "mod_bot.db")
local = threading.local()

def get_db():
    if not hasattr(local, "conn"):
        local.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        local.conn.row_factory = sqlite3.Row
    return local.conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Groups Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            welcome_enabled INTEGER DEFAULT 1,
            welcome_text TEXT DEFAULT 'Welcome to the group, {name}!',
            welcome_media_type TEXT,
            welcome_media_id TEXT,
            welcome_button_name TEXT,
            welcome_button_url TEXT,
            anti_link INTEGER DEFAULT 0,
            anti_flood INTEGER DEFAULT 0,
            anti_flood_limit INTEGER DEFAULT 5,
            anti_flood_time INTEGER DEFAULT 10,
            max_warnings INTEGER DEFAULT 3,
            action_on_max_warn TEXT DEFAULT 'kick',
            del_service_delay INTEGER DEFAULT 0,
            media_photo INTEGER DEFAULT 1,
            media_video INTEGER DEFAULT 1,
            media_gif INTEGER DEFAULT 1,
            media_sticker INTEGER DEFAULT 1,
            media_doc INTEGER DEFAULT 1,
            media_voice INTEGER DEFAULT 1,
            media_audio INTEGER DEFAULT 1,
            media_poll INTEGER DEFAULT 1,
            word_blacklist INTEGER DEFAULT 0,
            auto_accept_joins INTEGER DEFAULT 0
        )
    ''')
    
    # Warnings Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS warnings (
            chat_id INTEGER,
            user_id INTEGER,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        )
    ''')
    
    # Blacklist Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS blacklists (
            chat_id INTEGER,
            word TEXT,
            PRIMARY KEY (chat_id, word)
        )
    ''')
    
    # Mutes Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS mutes (
            chat_id INTEGER,
            user_id INTEGER,
            unmute_time REAL,
            PRIMARY KEY (chat_id, user_id)
        )
    ''')
    
    # Auto Replies Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS auto_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            trigger_text TEXT,
            reply_text TEXT,
            reply_voice_id TEXT
        )
    ''')
    
    try:
        c.execute("ALTER TABLE groups ADD COLUMN group_name TEXT")
    except:
        pass
        
    try:
        c.execute("ALTER TABLE groups ADD COLUMN welcome_voice_id TEXT")
    except:
        pass
        
    try:
        c.execute("ALTER TABLE auto_replies ADD COLUMN reply_sticker_id TEXT")
    except:
        pass
        
    try:
        c.execute("ALTER TABLE auto_replies ADD COLUMN reply_gif_id TEXT")
    except:
        pass
        
    try:
        c.execute("ALTER TABLE groups ADD COLUMN auto_accept_joins INTEGER DEFAULT 0")
    except:
        pass
        
    c.execute('''CREATE TABLE IF NOT EXISTS link_violations
                 (chat_id INTEGER, user_id INTEGER, count INTEGER, PRIMARY KEY (chat_id, user_id))''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS user_cache
                 (username TEXT PRIMARY KEY, user_id INTEGER)''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS global_settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    conn.commit()

def get_group_settings(chat_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM groups WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO groups (chat_id) VALUES (?)", (chat_id,))
        conn.commit()
        c.execute("SELECT * FROM groups WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
    return dict(row)

def update_group_setting(chat_id, key, value):
    conn = get_db()
    c = conn.cursor()
    get_group_settings(chat_id)
    c.execute(f"UPDATE groups SET {key}=? WHERE chat_id=?", (value, chat_id))
    conn.commit()

def update_group_name(chat_id, group_name):
    conn = get_db()
    c = conn.cursor()
    get_group_settings(chat_id)
    c.execute("UPDATE groups SET group_name=? WHERE chat_id=?", (group_name, chat_id))
    conn.commit()

def get_all_groups():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT chat_id, group_name FROM groups")
    return [dict(r) for r in c.fetchall()]

def add_auto_reply(chat_id, trigger_text, reply_text, reply_voice_id=None, reply_sticker_id=None, reply_gif_id=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO auto_replies (chat_id, trigger_text, reply_text, reply_voice_id, reply_sticker_id, reply_gif_id) VALUES (?, ?, ?, ?, ?, ?)", 
              (chat_id, trigger_text, reply_text, reply_voice_id, reply_sticker_id, reply_gif_id))
    conn.commit()

def get_auto_replies(chat_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM auto_replies WHERE chat_id=?", (chat_id,))
    return [dict(r) for r in c.fetchall()]

def delete_auto_reply(chat_id, trigger_text):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM auto_replies WHERE chat_id=? AND trigger_text=?", (chat_id, trigger_text))
    conn.commit()

def get_warnings(chat_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT count FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    row = c.fetchone()
    return row['count'] if row else 0

def add_warning(chat_id, user_id):
    conn = get_db()
    c = conn.cursor()
    count = get_warnings(chat_id, user_id) + 1
    c.execute("INSERT OR REPLACE INTO warnings (chat_id, user_id, count) VALUES (?, ?, ?)", (chat_id, user_id, count))
    conn.commit()
    return count

def reset_warnings(chat_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    conn.commit()

def get_blacklists(chat_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT word FROM blacklists WHERE chat_id=?", (chat_id,))
    return [row['word'] for row in c.fetchall()]

def add_link_violation(chat_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT count FROM link_violations WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    row = c.fetchone()
    if row:
        count = row['count'] + 1
        c.execute("UPDATE link_violations SET count=? WHERE chat_id=? AND user_id=?", (count, chat_id, user_id))
    else:
        count = 1
        c.execute("INSERT INTO link_violations (chat_id, user_id, count) VALUES (?, ?, ?)", (chat_id, user_id, count))
    conn.commit()
    return count

def reset_link_violation(chat_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM link_violations WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    conn.commit()

def set_user_cache(username, user_id):
    if not username: return
    username = username.lower().replace("@", "")
    conn = get_db()
    c = conn.cursor()
    c.execute("REPLACE INTO user_cache (username, user_id) VALUES (?, ?)", (username, user_id))
    conn.commit()

def get_user_id_by_username(username):
    username = username.lower().replace("@", "")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM user_cache WHERE username=?", (username,))
    row = c.fetchone()
    return row['user_id'] if row else None

def get_global_setting(key):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM global_settings WHERE key=?", (key,))
    row = c.fetchone()
    return row['value'] if row else None

def set_global_setting(key, value):
    conn = get_db()
    c = conn.cursor()
    c.execute("REPLACE INTO global_settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()

def add_blacklist(chat_id, word):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO blacklists (chat_id, word) VALUES (?, ?)", (chat_id, word.lower()))
    conn.commit()

def del_blacklist(chat_id, word):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM blacklists WHERE chat_id=? AND word=?", (chat_id, word.lower()))
    conn.commit()

def set_mute(chat_id, user_id, unmute_time):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO mutes (chat_id, user_id, unmute_time) VALUES (?, ?, ?)", (chat_id, user_id, unmute_time))
    conn.commit()

def get_mutes():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM mutes")
    return [dict(r) for r in c.fetchall()]

def del_mute(chat_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM mutes WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    conn.commit()

async def is_admin(bot, chat_id, user_id):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def get_target_user(update, context):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    if context.args:
        try:
            user_id = int(context.args[0])
            member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
            return member.user
        except:
            pass
    return None

async def kick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_admin(context.bot, chat_id, update.effective_user.id): return
    target = await get_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to a message or provide User ID.")
        return
    if await is_admin(context.bot, chat_id, target.id):
        await update.message.reply_text("Cannot kick an admin.")
        return
    try:
        await context.bot.ban_chat_member(chat_id, target.id)
        await context.bot.unban_chat_member(chat_id, target.id)
        await update.message.reply_text(f"ðŸ‘¢ Kicked {target.mention_html()}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_admin(context.bot, chat_id, update.effective_user.id): return
    target = await get_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to a message or provide User ID.")
        return
    if await is_admin(context.bot, chat_id, target.id):
        await update.message.reply_text("Cannot ban an admin.")
        return
    try:
        await context.bot.ban_chat_member(chat_id, target.id)
        await update.message.reply_text(f"ðŸ”¨ Banned {target.mention_html()}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_admin(context.bot, chat_id, update.effective_user.id): return
    target = await get_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to a message or provide User ID.")
        return
    try:
        await context.bot.unban_chat_member(chat_id, target.id)
        await update.message.reply_text(f"âœ… Unbanned {target.mention_html()}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")

def parse_time(time_str):
    unit = time_str[-1]
    if unit not in ['s', 'm', 'h', 'd']: return None
    try:
        val = int(time_str[:-1])
    except:
        return None
    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    return val * multipliers[unit]

async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_admin(context.bot, chat_id, update.effective_user.id): return
    target = await get_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to a message or provide User ID.")
        return
    if await is_admin(context.bot, chat_id, target.id):
        await update.message.reply_text("Cannot mute an admin.")
        return
        
    duration = 3600 
    if context.args and not update.message.reply_to_message:
        if len(context.args) > 1:
            t = parse_time(context.args[1])
            if t: duration = t
    elif context.args and update.message.reply_to_message:
        t = parse_time(context.args[0])
        if t: duration = t
        
    unmute_time = time.time() + duration
    perms = ChatPermissions(can_send_messages=False)
    try:
        await context.bot.restrict_chat_member(chat_id, target.id, permissions=perms, until_date=int(unmute_time))
        set_mute(chat_id, target.id, unmute_time)
        await update.message.reply_text(f"ðŸ”‡ Muted {target.mention_html()} for {duration} seconds.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")

async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_admin(context.bot, chat_id, update.effective_user.id): return
    target = await get_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to a message or provide User ID.")
        return
    perms = ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True
    )
    try:
        await context.bot.restrict_chat_member(chat_id, target.id, permissions=perms)
        del_mute(chat_id, target.id)
        await update.message.reply_text(f"ðŸ”Š Unmuted {target.mention_html()}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")

async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_admin(context.bot, chat_id, update.effective_user.id): return
    target = await get_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to a message or provide User ID.")
        return
    if await is_admin(context.bot, chat_id, target.id):
        await update.message.reply_text("Cannot warn an admin.")
        return
        
    settings = get_group_settings(chat_id)
    count = add_warning(chat_id, target.id)
    max_w = settings['max_warnings']
    
    if count >= max_w:
        action = settings['action_on_max_warn']
        msg = f"âš ï¸ Warning {count}/{max_w} for {target.mention_html()}.\nMaximum reached! Action: {action}."
        try:
            if action == 'kick':
                await context.bot.ban_chat_member(chat_id, target.id)
                await context.bot.unban_chat_member(chat_id, target.id)
            elif action == 'ban':
                await context.bot.ban_chat_member(chat_id, target.id)
            elif action == 'mute':
                perms = ChatPermissions(can_send_messages=False)
                await context.bot.restrict_chat_member(chat_id, target.id, permissions=perms)
        except Exception as e:
            msg += f"\nFailed to apply action: {e}"
        reset_warnings(chat_id, target.id)
        await update.message.reply_text(msg, parse_mode="HTML")
    else:
        await update.message.reply_text(f"âš ï¸ Warning {count}/{max_w} for {target.mention_html()}.", parse_mode="HTML")

spam_cache = {}

def get_spam_cache(chat_id, user_id):
    if chat_id not in spam_cache:
        spam_cache[chat_id] = {}
    if user_id not in spam_cache[chat_id]:
        spam_cache[chat_id][user_id] = {'times': [], 'last_msg': ""}
    return spam_cache[chat_id][user_id]

async def filter_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    chat_id = msg.chat.id
    user_id = msg.from_user.id
    
    # Cache username
    if msg.from_user.username:
        set_user_cache(msg.from_user.username, user_id)
    
    if msg.chat.type == "private":
        return
        
    update_group_name(chat_id, msg.chat.title)
    settings = get_group_settings(chat_id)
    
    # Check Auto Replies first
    if msg.text:
        msg_lower = msg.text.lower()
        replies = get_auto_replies(chat_id)
        for r in replies:
            if r['trigger_text'] in msg_lower:
                try:
                    if r['reply_text']:
                        await msg.reply_text(r['reply_text'])
                    if r['reply_voice_id']:
                        await msg.reply_voice(r['reply_voice_id'])
                    if r['reply_sticker_id']:
                        await msg.reply_sticker(r['reply_sticker_id'])
                    if r.get('reply_gif_id'):
                        await msg.reply_animation(r['reply_gif_id'])
                except:
                    pass
                # Keep going to check anti-link etc.
    
    if await is_admin(context.bot, chat_id, user_id):
        return 
        
    should_delete = False
    
    if not settings['media_photo'] and msg.photo: should_delete = True
    if not settings['media_video'] and msg.video: should_delete = True
    if not settings['media_gif'] and (msg.animation or msg.document and getattr(msg.document, 'mime_type', '').startswith('video/mp4')): should_delete = True
    if not settings['media_sticker'] and msg.sticker: should_delete = True
    if not settings['media_doc'] and msg.document: should_delete = True
    if not settings['media_voice'] and msg.voice: should_delete = True
    if not settings['media_audio'] and msg.audio: should_delete = True
    if not settings['media_poll'] and msg.poll: should_delete = True
    
    if should_delete:
        try: 
            await msg.delete()
        except Exception as e: 
            print(f"Error deleting media: {e}")
        return

    if settings['anti_link']:
        import re
        import time
        from telegram import ChatPermissions
        text_to_check = msg.text or msg.caption or ""
        if re.search(r'(https?://|www\.)[^\s]+|t\.me/[^\s]+', text_to_check, re.IGNORECASE):
            try: 
                await msg.delete()
            except: 
                pass
            
            # Apply progressive mute
            count = add_link_violation(chat_id, user_id)
            if count >= 3:
                mute_duration = 0
                if count == 3:
                    mute_duration = 60 # 1 min
                elif count == 4:
                    mute_duration = 300 # 5 min
                else:
                    mute_duration = 1800 # 30 min
                    
                unmute_time = time.time() + mute_duration
                perms = ChatPermissions(can_send_messages=False)
                try:
                    await context.bot.restrict_chat_member(chat_id, user_id, permissions=perms, until_date=int(unmute_time))
                    mins = mute_duration // 60
                    await context.bot.send_message(
                        chat_id, 
                        f"ðŸš« {msg.from_user.mention_html()} has been muted for {mins} minutes for repeatedly posting links!\n\nTo get unmuted early, DM the Owner.", 
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"Failed to mute: {e}")
            else:
                try:
                    await context.bot.send_message(
                        chat_id, 
                        f"âš ï¸ {msg.from_user.mention_html()}, links are not allowed here! (Warning {count}/2)", 
                        parse_mode="HTML"
                    )
                except:
                    pass
            return

    if settings['word_blacklist']:
        text = msg.text or msg.caption or ""
        blacklists = get_blacklists(chat_id)
        text_lower = text.lower()
        for word in blacklists:
            if word in text_lower:
                try: 
                    await msg.delete()
                except: 
                    pass
                return

    if settings['anti_flood']:
        cache = get_spam_cache(chat_id, user_id)
        now = time.time()
        
        text = msg.text or msg.caption or ""
        if text and text == cache['last_msg']:
            try: 
                await msg.delete()
            except: 
                pass
            return
        cache['last_msg'] = text
        
        cache['times'].append(now)
        cache['times'] = [t for t in cache['times'] if now - t <= settings['anti_flood_time']]
        
        if len(cache['times']) >= settings['anti_flood_limit']:
            try: 
                await msg.delete()
                from telegram import ChatPermissions
                perms = ChatPermissions(can_send_messages=False)
                await context.bot.restrict_chat_member(chat_id, user_id, permissions=perms, until_date=int(now + 300))
                await context.bot.send_message(chat_id, f"ðŸš« Muted {msg.from_user.mention_html()} for 5m due to flooding.", parse_mode="HTML")
            except: 
                pass
            cache['times'] = []

async def addword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private" or not await is_admin(context.bot, chat_id, update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /addword <word>")
        return
    word = " ".join(context.args)
    add_blacklist(chat_id, word)
    await update.message.reply_text(f"âœ… Added '{word}' to blacklist.")

async def delword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private" or not await is_admin(context.bot, chat_id, update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /delword <word>")
        return
    word = " ".join(context.args)
    del_blacklist(chat_id, word)
    await update.message.reply_text(f"âœ… Removed '{word}' from blacklist.")

async def listwords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private" or not await is_admin(context.bot, chat_id, update.effective_user.id):
        return
    words = get_blacklists(chat_id)
    if not words:
        await update.message.reply_text("List is empty.")
    else:
        await update.message.reply_text("Blacklisted words:\n" + ", ".join(words))

async def welcome_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if not result:
        return
        
    was_member = result.old_chat_member.status in [
        result.old_chat_member.MEMBER,
        result.old_chat_member.OWNER,
        result.old_chat_member.ADMINISTRATOR,
        result.old_chat_member.RESTRICTED,
    ]
    is_member = result.new_chat_member.status in [
        result.new_chat_member.MEMBER,
        result.new_chat_member.OWNER,
        result.new_chat_member.ADMINISTRATOR,
        result.new_chat_member.RESTRICTED,
    ]

    if not was_member and is_member:
        chat_id = result.chat.id
        member = result.new_chat_member.user
        if member.id == context.bot.id:
            return
            
        settings = get_group_settings(chat_id)
        if settings['welcome_enabled']:
            mention = f"@{member.username}" if member.username else member.mention_html()
            text = settings['welcome_text'].replace("{name}", mention).replace("{group}", result.chat.title).replace("{id}", str(member.id))
            reply_markup = None
            if settings['welcome_button_name'] and settings['welcome_button_url']:
                reply_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton(settings['welcome_button_name'], url=settings['welcome_button_url'])
                ]])
                
            try:
                await asyncio.sleep(2)
                
                if settings['welcome_media_type'] == 'photo':
                    await context.bot.send_photo(chat_id, photo=settings['welcome_media_id'], caption=text, reply_markup=reply_markup, parse_mode="HTML")
                elif settings['welcome_media_type'] == 'video':
                    await context.bot.send_video(chat_id, video=settings['welcome_media_id'], caption=text, reply_markup=reply_markup, parse_mode="HTML")
                else:
                    await context.bot.send_message(chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
                    
                if settings.get('welcome_voice_id'):
                    await context.bot.send_voice(chat_id, voice=settings['welcome_voice_id'], caption=f"Welcome {mention}!", parse_mode="HTML")
            except Exception as e:
                print(f"Error sending welcome: {e}")

async def welcome_message_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.new_chat_members:
        return
        
    chat_id = msg.chat.id
    settings = get_group_settings(chat_id)
    if not settings['welcome_enabled']:
        return
        
    for member in msg.new_chat_members:
        if member.id == context.bot.id:
            continue
            
        mention = f"@{member.username}" if member.username else member.mention_html()
        text = settings['welcome_text'].replace("{name}", mention).replace("{group}", msg.chat.title).replace("{id}", str(member.id))
        reply_markup = None
        if settings['welcome_button_name'] and settings['welcome_button_url']:
            reply_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(settings['welcome_button_name'], url=settings['welcome_button_url'])
            ]])
            
        try:
            await asyncio.sleep(2)
            
            if settings['welcome_media_type'] == 'photo':
                await context.bot.send_photo(chat_id, photo=settings['welcome_media_id'], caption=text, reply_markup=reply_markup, parse_mode="HTML")
            elif settings['welcome_media_type'] == 'video':
                await context.bot.send_video(chat_id, video=settings['welcome_media_id'], caption=text, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await context.bot.send_message(chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
                
            if settings.get('welcome_voice_id'):
                await context.bot.send_voice(chat_id, voice=settings['welcome_voice_id'], caption=f"Welcome {mention}!", parse_mode="HTML")
        except Exception as e:
            print(f"Error sending welcome fallback: {e}")

async def delete_service_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg and (msg.new_chat_members or msg.left_chat_member):
        try:
            await msg.delete()
        except:
            pass

async def set_welcome_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
        
    chat_member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
    if chat_member.status not in ['administrator', 'creator']:
        return
        
    if not context.args:
        await update.message.reply_text("Usage: /setwelcome <text>\nSupports {name} and {group}")
        return
        
    text = " ".join(context.args)
    update_group_setting(chat_id, "welcome_text", text)
    await update.message.reply_text("âœ… Welcome message updated!")

async def set_button_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    chat_member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
    if chat_member.status not in ['administrator', 'creator']:
        return
        
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /setbutton <Name> <URL>\nTo remove: /setbutton remove remove")
        return
        
    name = " ".join(args[:-1])
    url = args[-1]
    
    if name.lower() == "remove":
        update_group_setting(chat_id, "welcome_button_name", None)
        update_group_setting(chat_id, "welcome_button_url", None)
        await update.message.reply_text("âœ… Button removed!")
    else:
        update_group_setting(chat_id, "welcome_button_name", name)
        update_group_setting(chat_id, "welcome_button_url", url)
        await update.message.reply_text("âœ… Button updated!")

def get_settings_keyboard(target_chat_id):
    settings = get_group_settings(target_chat_id)
    kb = [
        [
            InlineKeyboardButton(f"Welcome System: {'âœ…' if settings['welcome_enabled'] else 'âŒ'}", callback_data=f"tg_we_{target_chat_id}"),
            InlineKeyboardButton(f"Anti-Link: {'âœ…' if settings['anti_link'] else 'âŒ'}", callback_data=f"tg_al_{target_chat_id}")
        ],
        [
            InlineKeyboardButton(f"Auto-Accept Join Requests: {'âœ…' if settings.get('auto_accept_joins') else 'âŒ'}", callback_data=f"tg_aa_{target_chat_id}")
        ],
        [
            InlineKeyboardButton(f"Anti-Flood: {'âœ…' if settings['anti_flood'] else 'âŒ'}", callback_data=f"tg_af_{target_chat_id}"),
            InlineKeyboardButton(f"Bad Words: {'âœ…' if settings['word_blacklist'] else 'âŒ'}", callback_data=f"tg_wb_{target_chat_id}")
        ],
        [
            InlineKeyboardButton(f"Block Photos: {'âŒ' if settings['media_photo'] else 'âœ…'}", callback_data=f"tg_mp_{target_chat_id}"),
            InlineKeyboardButton(f"Block Videos: {'âŒ' if settings['media_video'] else 'âœ…'}", callback_data=f"tg_mv_{target_chat_id}")
        ],
        [
            InlineKeyboardButton(f"Block GIFs: {'âŒ' if settings['media_gif'] else 'âœ…'}", callback_data=f"tg_mg_{target_chat_id}"),
            InlineKeyboardButton(f"Block Stickers: {'âŒ' if settings['media_sticker'] else 'âœ…'}", callback_data=f"tg_ms_{target_chat_id}")
        ],
        [
            InlineKeyboardButton("Set Welcome Video / Photo", callback_data=f"tg_wlmd_{target_chat_id}")
        ],
        [
            InlineKeyboardButton("Set Welcome Text", callback_data=f"tg_sw_{target_chat_id}"),
            InlineKeyboardButton("Set Welcome Voice", callback_data=f"tg_sv_{target_chat_id}")
        ],
        [
            InlineKeyboardButton("Remove Video/Photo", callback_data=f"tg_wlrmd_{target_chat_id}"),
            InlineKeyboardButton("Remove Voice", callback_data=f"tg_rv_{target_chat_id}")
        ],
        [
            InlineKeyboardButton("Broadcast Message to Group", callback_data=f"tg_bc_{target_chat_id}")
        ],
        [
            InlineKeyboardButton("Manage Auto-Replies", callback_data=f"tg_ar_{target_chat_id}")
        ],
        [
            InlineKeyboardButton("ðŸ”Š Unmute a User", callback_data=f"tg_unm_{target_chat_id}"),
            InlineKeyboardButton("ðŸ‘‘ Promote to Admin", callback_data=f"tg_mkad_{target_chat_id}")
        ],
        [
            InlineKeyboardButton("Back to Groups" if str(target_chat_id).startswith("-100") else "Close", callback_data="tg_close")
        ]
    ]
    return InlineKeyboardMarkup(kb)

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        await update.message.reply_text("Run this in a group, or if you are owner, just type /start here.")
        return
    if not await is_admin(context.bot, chat_id, update.effective_user.id):
        return
        
    await update.message.reply_text(f"âš™ï¸ <b>Settings for {update.effective_chat.title}</b>", reply_markup=get_settings_keyboard(chat_id), parse_mode="HTML")

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    data = query.data
    
    if data == "tg_close":
        if str(user_id) == "8373276191":
            # If owner is in DM, show groups list
            groups = get_all_groups()
            kb = []
            for g in groups:
                if g['group_name']:
                    kb.append([InlineKeyboardButton(g['group_name'], callback_data=f"tg_open_{g['chat_id']}")])
            if not kb:
                kb.append([InlineKeyboardButton("No groups found", callback_data="ignore")])
            kb.append([InlineKeyboardButton("ðŸ“ Set Bot Start Message", callback_data="tg_gstart")])
            await query.edit_message_text("ðŸ¢ <b>Your Groups</b>\nSelect a group to manage:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            return
        else:
            await query.message.delete()
            return
            
    if data.startswith("tg_open_"):
        if str(user_id) != "8373276191":
            await query.answer("Not authorized.", show_alert=True)
            return
        target_id = int(data.split("_")[2])
        await query.edit_message_text(f"âš™ï¸ <b>Settings for Group</b>", reply_markup=get_settings_keyboard(target_id), parse_mode="HTML")
        return

    if data == "tg_gstart":
        if str(user_id) != "8373276191":
            await query.answer("Not authorized.", show_alert=True)
            return
        context.user_data['awaiting_global_start'] = True
        await query.message.reply_text("ðŸ¤– Please send or forward the message you want to set as the Bot's Start Message.\nType /cancel to abort.")
        return

    # For other toggles
    parts = data.split("_")
    if len(parts) >= 3:
        key_code = parts[1]
        target_id = int(parts[2])
        
        # Verify admin
        if str(user_id) != "8373276191":
            if not await is_admin(context.bot, target_id, user_id):
                await query.answer("You are not an admin in that group.", show_alert=True)
                return

        mapping = {
            'we': 'welcome_enabled', 'al': 'anti_link', 'af': 'anti_flood', 
            'wb': 'word_blacklist', 'mp': 'media_photo', 'mv': 'media_video', 
            'mg': 'media_gif', 'ms': 'media_sticker', 'dd': 'del_service_delay',
            'aa': 'auto_accept_joins'
        }
        
        if key_code == 'wl':
            settings = get_group_settings(target_id)
            en_status = 'âœ… ON' if settings.get('welcome_enabled', 1) else 'âŒ OFF'
            media_status = "ðŸ–¼ Set" if settings.get('welcome_media_id') else "Not Set"
            voice_status = "ðŸŽ™ Set" if settings.get('welcome_voice_id') else "Not Set"
            
            kb = [
                [InlineKeyboardButton(f"Welcome System: {en_status}", callback_data=f"tg_wlen_{target_id}")],
                [InlineKeyboardButton("âž• Set Text", callback_data=f"tg_sw_{target_id}")],
                [InlineKeyboardButton(f"âž• Set Photo/Video ({media_status})", callback_data=f"tg_wlmd_{target_id}")],
                [InlineKeyboardButton(f"âž• Set Voice ({voice_status})", callback_data=f"tg_sv_{target_id}")],
                [InlineKeyboardButton("ðŸ—‘ Remove Photo/Video", callback_data=f"tg_wlrmd_{target_id}")],
                [InlineKeyboardButton("ðŸ—‘ Remove Voice", callback_data=f"tg_rv_{target_id}")],
                [InlineKeyboardButton("ðŸ”™ Back to Settings", callback_data=f"tg_open_{target_id}")]
            ]
            await query.edit_message_text("ðŸ‘‹ <b>Welcome Message Management</b>\nConfigure how new members are greeted:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            return
            
        if key_code == 'wlen':
            settings = get_group_settings(target_id)
            current = settings.get('welcome_enabled', 1)
            new_val = 0 if current else 1
            update_group_setting(target_id, 'welcome_enabled', new_val)
            
            # refresh wl menu
            settings = get_group_settings(target_id)
            en_status = 'âœ… ON' if settings.get('welcome_enabled', 1) else 'âŒ OFF'
            media_status = "ðŸ–¼ Set" if settings.get('welcome_media_id') else "Not Set"
            voice_status = "ðŸŽ™ Set" if settings.get('welcome_voice_id') else "Not Set"
            
            kb = [
                [InlineKeyboardButton(f"Welcome System: {en_status}", callback_data=f"tg_wlen_{target_id}")],
                [InlineKeyboardButton("âž• Set Text", callback_data=f"tg_sw_{target_id}")],
                [InlineKeyboardButton(f"âž• Set Photo/Video ({media_status})", callback_data=f"tg_wlmd_{target_id}")],
                [InlineKeyboardButton(f"âž• Set Voice ({voice_status})", callback_data=f"tg_sv_{target_id}")],
                [InlineKeyboardButton("ðŸ—‘ Remove Photo/Video", callback_data=f"tg_wlrmd_{target_id}")],
                [InlineKeyboardButton("ðŸ—‘ Remove Voice", callback_data=f"tg_rv_{target_id}")],
                [InlineKeyboardButton("ðŸ”™ Back to Settings", callback_data=f"tg_open_{target_id}")]
            ]
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb))
            return
            
        if key_code == 'wlmd':
            context.user_data['awaiting_welcome_media'] = target_id
            await query.message.reply_text("ðŸ–¼ Please send a **Photo** or **Video** you want to attach to the Welcome Message now.\nType /cancel to abort.", parse_mode="Markdown")
            return
            
        if key_code == 'wlrmd':
            update_group_setting(target_id, 'welcome_media_type', None)
            update_group_setting(target_id, 'welcome_media_id', None)
            await query.answer("Photo/Video removed!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_settings_keyboard(target_id))
            return

        if key_code == 'sw':
            context.user_data['awaiting_welcome'] = target_id
            await query.message.reply_text("âœï¸ Please send the new Welcome Message for this group now.\n(Supports {name} and {group})\nType /cancel to abort.")
            return
            
        if key_code == 'sv':
            context.user_data['awaiting_welcome_voice'] = target_id
            await query.message.reply_text("ðŸŽ™ Please send or forward the Voice Note for the Welcome Message now.\nType /cancel to abort.")
            return
            
        if key_code == 'rv':
            update_group_setting(target_id, 'welcome_voice_id', None)
            await query.answer("Voice removed!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_settings_keyboard(target_id))
            return
            
        if key_code == 'bc':
            context.user_data['awaiting_broadcast'] = target_id
            await query.message.reply_text("ðŸ“¢ Please forward or send the message you want to broadcast to this group now.\nType /cancel to abort.")
            return
            
        if key_code == 'unm':
            context.user_data['awaiting_unmute'] = target_id
            await query.message.reply_text("ðŸ”Š Please send the **User ID** OR **Username** (e.g. @sagar) of the user you want to unmute.\nType /cancel to abort.", parse_mode="Markdown")
            return
            
        if key_code == 'mkad':
            context.user_data['awaiting_admin'] = target_id
            await query.message.reply_text("ðŸ‘‘ Please send the **User ID** OR **Username** (e.g. @sagar) of the user you want to promote to Admin.\nType /cancel to abort.", parse_mode="Markdown")
            return
            
        if key_code == 'ar':
            kb = [
                [InlineKeyboardButton("âž• Add Text Reply", callback_data=f"tg_artxt_{target_id}")],
                [InlineKeyboardButton("âž• Add Voice Reply", callback_data=f"tg_arvc_{target_id}")],
                [InlineKeyboardButton("âž• Add Sticker/GIF Reply", callback_data=f"tg_arst_{target_id}")],
                [InlineKeyboardButton("ðŸ—‘ View & Delete Auto-Replies", callback_data=f"tg_arls_{target_id}")],
                [InlineKeyboardButton("ðŸ”™ Back to Settings", callback_data=f"tg_open_{target_id}")]
            ]
            await query.edit_message_text(f"ðŸ¤– <b>Auto-Replies Management</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            return
            
        if key_code in ['artxt', 'arvc', 'arst']:
            context.user_data['ar_type'] = key_code
            context.user_data['ar_state'] = 'trigger'
            context.user_data['ar_chat_id'] = target_id
            await query.message.reply_text("1ï¸âƒ£ Send the **Trigger Word** (e.g. 'help'). If anyone says this in the group, I will reply.\nType /cancel to abort.", parse_mode="Markdown")
            return
            
        if key_code == 'arls':
            replies = get_auto_replies(target_id)
            if not replies:
                await query.answer("No auto-replies found.", show_alert=True)
                return
            kb = []
            for r in replies:
                kb.append([InlineKeyboardButton(f"âŒ Delete '{r['trigger_text']}'", callback_data=f"tg_ardl_{target_id}_{r['trigger_text']}")])
            kb.append([InlineKeyboardButton("ðŸ”™ Back", callback_data=f"tg_ar_{target_id}")])
            await query.edit_message_text("ðŸ—‘ Select an Auto-Reply to delete:", reply_markup=InlineKeyboardMarkup(kb))
            return
            
        if key_code == 'ardl':
            trigger_text = parts[3]
            delete_auto_reply(target_id, trigger_text)
            await query.answer("Auto-reply deleted!", show_alert=True)
            
            # Refresh list
            replies = get_auto_replies(target_id)
            kb = []
            for r in replies:
                kb.append([InlineKeyboardButton(f"âŒ Delete '{r['trigger_text']}'", callback_data=f"tg_ardl_{target_id}_{r['trigger_text']}")])
            kb.append([InlineKeyboardButton("ðŸ”™ Back", callback_data=f"tg_ar_{target_id}")])
            if not replies:
                kb = [[InlineKeyboardButton("ðŸ”™ Back", callback_data=f"tg_ar_{target_id}")]]
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb))
            return

        if key_code in mapping:
            db_key = mapping[key_code]
            settings = get_group_settings(target_id)
            
            if db_key == "del_service_delay":
                current = settings[db_key]
                next_val = {0: 5, 5: 10, 10: 30, 30: 60, 60: 0}.get(current, 0)
                update_group_setting(target_id, db_key, next_val)
            else:
                current = settings[db_key]
                update_group_setting(target_id, db_key, 0 if current else 1)
                
            await query.edit_message_reply_markup(reply_markup=get_settings_keyboard(target_id))

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8704551345:AAEZ-lbq0CXCtfYMtg87_znRoW26SY-0oAY"


async def dm_media_handler(update: Update, context):
    if update.effective_chat.type == "private":
        # Handle Broadcast
        target_id_bc = context.user_data.get('awaiting_broadcast')
        if target_id_bc:
            if update.message.text == "/cancel":
                context.user_data['awaiting_broadcast'] = None
                await update.message.reply_text("Broadcast cancelled.")
                return
            try:
                sent_msg = await context.bot.copy_message(chat_id=target_id_bc, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
                try:
                    await context.bot.pin_chat_message(chat_id=target_id_bc, message_id=sent_msg.message_id)
                except Exception as pin_e:
                    print(f"Failed to pin message: {pin_e}")
                await update.message.reply_text("âœ… Message Broadcasted and Pinned to the group successfully!")
            except Exception as e:
                await update.message.reply_text(f"âŒ Error broadcasting: {e}")
            context.user_data['awaiting_broadcast'] = None
            return

        # Handle Auto-Reply Setup
        ar_state = context.user_data.get('ar_state')
        if ar_state:
            if update.message.text == "/cancel":
                context.user_data['ar_state'] = None
                await update.message.reply_text("Auto-reply setup cancelled.")
                return
                
            if ar_state == 'trigger' and update.message.text:
                context.user_data['ar_trigger'] = update.message.text.lower()
                ar_type = context.user_data.get('ar_type')
                
                if ar_type == 'artxt':
                    context.user_data['ar_state'] = 'reply_only_text'
                    await update.message.reply_text("2ï¸âƒ£ Send the **Text Message** you want the bot to reply with.")
                elif ar_type == 'arvc':
                    context.user_data['ar_state'] = 'reply_only_voice'
                    await update.message.reply_text("2ï¸âƒ£ Send the **Voice Note** you want the bot to reply with.")
                elif ar_type == 'arst':
                    context.user_data['ar_state'] = 'reply_only_sticker'
                    await update.message.reply_text("2ï¸âƒ£ Send the **Sticker** or **GIF** you want the bot to reply with.")
                return

            if ar_state == 'reply_only_text' and update.message.text:
                add_auto_reply(context.user_data['ar_chat_id'], context.user_data['ar_trigger'], update.message.text, None, None, None)
                context.user_data['ar_state'] = None
                await update.message.reply_text("âœ… Text Auto-Reply saved successfully!")
                return
                
            if ar_state == 'reply_only_voice' and update.message.voice:
                add_auto_reply(context.user_data['ar_chat_id'], context.user_data['ar_trigger'], None, update.message.voice.file_id, None, None)
                context.user_data['ar_state'] = None
                await update.message.reply_text("âœ… Voice Auto-Reply saved successfully!")
                return
                
            if ar_state == 'reply_only_sticker' and (update.message.sticker or update.message.animation):
                r_sticker = update.message.sticker.file_id if update.message.sticker else None
                r_gif = update.message.animation.file_id if update.message.animation else None
                add_auto_reply(context.user_data['ar_chat_id'], context.user_data['ar_trigger'], None, None, r_sticker, r_gif)
                context.user_data['ar_state'] = None
                await update.message.reply_text("âœ… Sticker/GIF Auto-Reply saved successfully!")
                return
                
            if ar_state in ['reply_only_text', 'reply_only_voice', 'reply_only_sticker']:
                await update.message.reply_text("âŒ You sent the wrong type of message for this option. Please send the correct media type or type /cancel.")
                return
            return

        target_id_md = context.user_data.get('awaiting_welcome_media')
        if target_id_md:
            if update.message.text == "/cancel":
                context.user_data['awaiting_welcome_media'] = None
                await update.message.reply_text("Cancelled.")
                return
            if update.message.photo:
                update_group_setting(target_id_md, 'welcome_media_type', 'photo')
                update_group_setting(target_id_md, 'welcome_media_id', update.message.photo[-1].file_id)
                context.user_data['awaiting_welcome_media'] = None
                await update.message.reply_text("âœ… Welcome Photo saved successfully!")
            elif update.message.video:
                update_group_setting(target_id_md, 'welcome_media_type', 'video')
                update_group_setting(target_id_md, 'welcome_media_id', update.message.video.file_id)
                context.user_data['awaiting_welcome_media'] = None
                await update.message.reply_text("âœ… Welcome Video saved successfully!")
            else:
                await update.message.reply_text("âŒ Please send a Photo or Video, or type /cancel.")
            return

        target_id_unm = context.user_data.get('awaiting_unmute')
        if target_id_unm and update.message.text:
            if update.message.text == "/cancel":
                context.user_data['awaiting_unmute'] = None
                await update.message.reply_text("Cancelled.")
                return
            try:
                raw = update.message.text.strip()
                user_id_to_unmute = None
                if raw.startswith('@') or not raw.isdigit():
                    user_id_to_unmute = get_user_id_by_username(raw)
                    if not user_id_to_unmute:
                        await update.message.reply_text(f"âŒ User '{raw}' not found in database. Please use their User ID instead.")
                        return
                else:
                    user_id_to_unmute = int(raw)
                    
                from telegram import ChatPermissions
                perms = ChatPermissions(
                    can_send_messages=True,
                    can_send_audios=True,
                    can_send_documents=True,
                    can_send_photos=True,
                    can_send_videos=True,
                    can_send_video_notes=True,
                    can_send_voice_notes=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
                await context.bot.restrict_chat_member(target_id_unm, user_id_to_unmute, permissions=perms)
                reset_link_violation(target_id_unm, user_id_to_unmute)
                context.user_data['awaiting_unmute'] = None
                await update.message.reply_text(f"âœ… User {raw} has been successfully unmuted and their warning count reset!")
            except Exception as e:
                await update.message.reply_text(f"âŒ Failed to unmute user: {e}")
            return

        target_id_v = context.user_data.get('awaiting_welcome_voice')
        if target_id_v and update.message.voice:
            update_group_setting(target_id_v, "welcome_voice_id", update.message.voice.file_id)
            context.user_data['awaiting_welcome_voice'] = None
            await update.message.reply_text("âœ… Welcome Voice updated for the group!")
            return
            
        target_id_ad = context.user_data.get('awaiting_admin')
        if target_id_ad and update.message.text:
            if update.message.text == "/cancel":
                context.user_data['awaiting_admin'] = None
                await update.message.reply_text("Cancelled.")
                return
            try:
                raw = update.message.text.strip()
                user_id_to_promote = None
                if raw.startswith('@') or not raw.isdigit():
                    user_id_to_promote = get_user_id_by_username(raw)
                    if not user_id_to_promote:
                        await update.message.reply_text(f"âŒ User '{raw}' not found in database. Please use their User ID instead.")
                        return
                else:
                    user_id_to_promote = int(raw)
                    
                await context.bot.promote_chat_member(
                    target_id_ad, 
                    user_id_to_promote,
                    can_manage_chat=True,
                    can_change_info=True,
                    can_delete_messages=True,
                    can_restrict_members=True,
                    can_invite_users=True,
                    can_pin_messages=True
                )
                context.user_data['awaiting_admin'] = None
                await update.message.reply_text(f"ðŸ‘‘ User {raw} has been promoted to Admin in the group!")
            except Exception as e:
                await update.message.reply_text(f"âŒ Failed to promote user: {e}")
            return
            
        if context.user_data.get('awaiting_global_start'):
            if update.message.text and update.message.text == "/cancel":
                context.user_data['awaiting_global_start'] = False
                await update.message.reply_text("Cancelled.")
                return
            
            # Save message id to DB
            set_global_setting("start_msg_id", update.message.message_id)
            set_global_setting("start_msg_chat", update.effective_chat.id)
            context.user_data['awaiting_global_start'] = False
            await update.message.reply_text("âœ… Bot Start Message saved successfully! Anyone starting the bot will receive this exact message.")
            return

        target_id = context.user_data.get('awaiting_welcome')
        if target_id and update.message.text:
            if update.message.text == "/cancel":
                context.user_data['awaiting_welcome'] = None
                await update.message.reply_text("Cancelled.")
                return
            update_group_setting(target_id, "welcome_text", update.message.text)
            context.user_data['awaiting_welcome'] = None
            await update.message.reply_text("âœ… Welcome message updated for the group!")
            return
        return
        
    await filter_messages(update, context)
    
async def handle_join_request(update: Update, context):
    request = update.chat_join_request
    if not request: return
    chat_id = request.chat.id
    settings = get_group_settings(chat_id)
    if settings and settings.get('auto_accept_joins'):
        try:
            await request.approve()
            # Cache user info since they just joined
            set_user_cache(request.from_user.username, request.from_user.id)
        except Exception as e:
            print(f"Failed to auto-approve join request: {e}")

async def start_cmd(update: Update, context):
    user_id = str(update.effective_user.id)
    if update.effective_chat.type == "private":
        if user_id == "8373276191":
            groups = get_all_groups()
            kb = []
            for g in groups:
                if g['group_name']:
                    kb.append([InlineKeyboardButton(g['group_name'], callback_data=f"tg_open_{g['chat_id']}")])
            if not kb:
                kb.append([InlineKeyboardButton("No groups found. Add me to a group first!", callback_data="ignore")])
            
            kb.append([InlineKeyboardButton("ðŸ“ Set Bot Start Message", callback_data="tg_gstart")])
                
            await update.message.reply_text("ðŸ¢ <b>Central Control Panel</b>\nSelect a group to manage its settings directly from here:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        else:
            msg_id = get_global_setting("start_msg_id")
            chat_id = get_global_setting("start_msg_chat")
            if msg_id and chat_id:
                try:
                    await context.bot.copy_message(chat_id=update.effective_chat.id, from_chat_id=chat_id, message_id=msg_id)
                except Exception as e:
                    await update.message.reply_text("Hi! I am the Group Moderation Bot.")
            else:
                await update.message.reply_text("Hi! I am the Group Moderation Bot. Add me to a group and use /settings inside the group to configure me!")

import os
from threading import Thread
try:
    from flask import Flask
    web_app = Flask(__name__)
    @web_app.route('/')
    def home():
        return "Bot is running!"
    def run_server():
        port = int(os.environ.get("PORT", 8080))
        web_app.run(host="0.0.0.0", port=port)
    Thread(target=run_server).start()
except ImportError:
    print("Flask not installed, skipping web server.")

def main():
    init_db()
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(ChatMemberHandler(welcome_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_message))
    
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^tg_"))
    
    app.add_handler(CommandHandler("setwelcome", set_welcome_cmd))
    app.add_handler(CommandHandler("setbutton", set_button_cmd))
    
    app.add_handler(CommandHandler("kick", kick_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("unmute", unmute_cmd))
    app.add_handler(CommandHandler("warn", warn_cmd))
    
    app.add_handler(CommandHandler("addword", addword_cmd))
    app.add_handler(CommandHandler("delword", delword_cmd))
    app.add_handler(CommandHandler("listwords", listwords_cmd))
    
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.StatusUpdate.ALL, dm_media_handler))
    
    print("Group Moderation Bot Started...")
    app.run_polling(allowed_updates=["message", "chat_member", "callback_query", "chat_join_request"], drop_pending_updates=True)

if __name__ == "__main__":
    main()

