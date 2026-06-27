import asyncio
import logging
import secrets
import string
from os import getenv

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = getenv("BOT_TOKEN")
API_URL = getenv("API_URL", "http://localhost:7535")
SUPERADMIN_TOKEN = getenv("SUPERADMIN_TOKEN")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"


def generate_password(length: int = 16) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


class CreateAdmin(StatesGroup):
    full_name = State()
    username = State()
    email = State()
    phone = State()


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 System adminlar ro'yxati", callback_data="list_admins")],
        [InlineKeyboardButton(text="➕ Yangi system admin yaratish", callback_data="create_admin")],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")],
    ])


def skip_cancel_kb(skip_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=skip_data)],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")],
    ])


async def _parse_response(resp: aiohttp.ClientResponse) -> dict | list:
    try:
        return await resp.json(content_type=None)
    except Exception:
        text = await resp.text()
        return {"detail": text or "Server xatosi"}


async def api_get(path: str) -> tuple[int, dict | list]:
    headers = {"X-Token": SUPERADMIN_TOKEN}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}{path}", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return resp.status, await _parse_response(resp)
    except aiohttp.ClientConnectorError:
        return 503, {"detail": f"API serverga ulanib bo'lmadi ({API_URL}). Server ishga tushirilganmi?"}
    except asyncio.TimeoutError:
        return 504, {"detail": "API server javob bermadi (timeout)."}


async def api_post(path: str, data: dict) -> tuple[int, dict]:
    headers = {"X-Token": SUPERADMIN_TOKEN, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_URL}{path}", json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return resp.status, await _parse_response(resp)
    except aiohttp.ClientConnectorError:
        return 503, {"detail": f"API serverga ulanib bo'lmadi ({API_URL}). Server ishga tushirilganmi?"}
    except asyncio.TimeoutError:
        return 504, {"detail": "API server javob bermadi (timeout)."}


async def _do_create_admin(data: dict, password: str, target: Message):
    payload = {
        "full_name": data["full_name"],
        "username": data["username"],
        "password": password,
    }
    if data.get("email"):
        payload["email"] = data["email"]
    if data.get("phone"):
        payload["phone"] = data["phone"]

    status, resp = await api_post("/superadmin/system-admins", payload)

    if status == 201:
        email = resp.get("email") or "—"
        phone = resp.get("phone") or "—"
        username = resp.get("username") or "—"
        await target.answer(
            f"✅ <b>System admin muvaffaqiyatli yaratildi!</b>\n\n"
            f"👤 Ism: <b>{resp['full_name']}</b>\n"
            f"🔖 Username: <b>{username}</b>\n"
            f"📧 Email: <b>{email}</b>\n"
            f"📞 Telefon: <b>{phone}</b>\n"
            f"🆔 ID: <b>{resp['id']}</b>\n\n"
            f"🔐 Parol: <tg-spoiler>{password}</tg-spoiler>",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
    elif status == 409:
        await target.answer(
            "⚠️ Bu username yoki email allaqachon mavjud. Qayta urinib ko'ring.",
            reply_markup=main_menu(),
        )
    else:
        detail = resp.get("detail", "Nomalum xato")
        await target.answer(f"❌ Xatolik: {detail}", reply_markup=main_menu())


# ── Handlers ──────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer(
        "👋 <b>Superadmin bot</b>ga xush kelibsiz!\n\n"
        "Bu bot orqali siz <b>AIDiagnostika</b> tizimida system adminlarni boshqarishingiz mumkin.",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


@dp.message(Command("menu"))
async def cmd_menu(msg: Message):
    await msg.answer("Asosiy menyu:", reply_markup=main_menu())


# ── List admins ───────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "list_admins")
async def cb_list_admins(cb: CallbackQuery):
    await cb.answer()
    status, data = await api_get("/superadmin/system-admins")

    if status != 200:
        await cb.message.answer(f"❌ Xatolik yuz berdi: {data.get('detail', 'Nomalum xato')}")
        return

    if not data:
        await cb.message.answer("📭 Hozircha system adminlar yo'q.", reply_markup=main_menu())
        return

    lines = ["👥 <b>System adminlar ro'yxati:</b>\n"]
    for i, admin in enumerate(data, 1):
        username = admin.get("username") or "—"
        email = admin.get("email") or "—"
        phone = admin.get("phone") or "—"
        lines.append(
            f"{i}. <b>{admin['full_name']}</b>\n"
            f"   🔖 {username}\n"
            f"   📧 {email}\n"
            f"   📞 {phone}\n"
            f"   🆔 ID: {admin['id']}"
        )

    await cb.message.answer("\n\n".join(lines), parse_mode="HTML", reply_markup=main_menu())


# ── Create admin conversation ─────────────────────────────────────────────────

@dp.callback_query(F.data == "create_admin")
async def cb_create_admin(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(CreateAdmin.full_name)
    await cb.message.answer(
        "➕ <b>Yangi system admin yaratish</b>\n\n"
        "To'liq ismini kiriting:",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@dp.message(CreateAdmin.full_name)
async def step_full_name(msg: Message, state: FSMContext):
    await state.update_data(full_name=msg.text.strip())
    await state.set_state(CreateAdmin.username)
    await msg.answer("🔖 Username kiriting:", reply_markup=cancel_kb())


@dp.message(CreateAdmin.username)
async def step_username(msg: Message, state: FSMContext):
    await state.update_data(username=msg.text.strip())
    await state.set_state(CreateAdmin.email)
    await msg.answer(
        "📧 Email manzilini kiriting (ixtiyoriy):",
        reply_markup=skip_cancel_kb("skip_email"),
    )


@dp.callback_query(F.data == "skip_email", CreateAdmin.email)
async def skip_email(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(email=None)
    await state.set_state(CreateAdmin.phone)
    await cb.message.answer(
        "📞 Telefon raqamini kiriting (ixtiyoriy):",
        reply_markup=skip_cancel_kb("skip_phone"),
    )


@dp.message(CreateAdmin.email)
async def step_email(msg: Message, state: FSMContext):
    await state.update_data(email=msg.text.strip())
    await state.set_state(CreateAdmin.phone)
    await msg.answer(
        "📞 Telefon raqamini kiriting (ixtiyoriy):",
        reply_markup=skip_cancel_kb("skip_phone"),
    )


@dp.callback_query(F.data == "skip_phone", CreateAdmin.phone)
async def skip_phone(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(phone=None)
    data = await state.get_data()
    await state.clear()
    await _do_create_admin(data, generate_password(), cb.message)


@dp.message(CreateAdmin.phone)
async def step_phone(msg: Message, state: FSMContext):
    await state.update_data(phone=msg.text.strip())
    data = await state.get_data()
    await state.clear()
    await _do_create_admin(data, generate_password(), msg)


# ── Cancel ────────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await cb.message.answer("❌ Bekor qilindi.", reply_markup=main_menu())


async def main():
    log.info("Bot ishga tushmoqda...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
