import asyncio
import datetime
import logging
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, ForeignKey, BigInteger
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()


logging.basicConfig(
    level=logging.INFO,  # INFO, DEBUG, WARNING, ERROR
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

ADMIN_IDS = [6220854815, 6426346196, 1617370561]

# SQLAlchemy async setup
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

# Templates
templates = Jinja2Templates(directory="templates")
app = FastAPI()



class PostFSM(StatesGroup):
    waiting_for_media = State()
    waiting_for_caption = State()
# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)



class ButtonClick(Base):
    __tablename__ = "button_clicks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    button = Column(String)  # "xa" or "yoq"
    clicked_at = Column(DateTime, default=datetime.datetime.utcnow)


class PendingPost(Base):
    __tablename__ = "pending_posts"
    id = Column(Integer, primary_key=True)
    content = Column(String)
    media = Column(String, nullable=True)  # rasm/video link
    is_video = Column(Boolean, default=False)
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ---------------- Aiogram Bot ---------------- #
@dp.message(Command("start"))
async def start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤩 Albatta, ha deymanda !!!", callback_data="xa")]
    ])
    text = (
        "Hey, Siz! 😎\n\n"
        "*IELTS* oldidan aniq ballingizni bilib olishni xohlaysizmi? 🧐\n\n"
        "Sizni haqiqiy Britaniyalik ekspertlar baholasa-chi? 🇬🇧\n\n"
        "Original Reading & Listening savollarini Toshkentning eng katta rasmiy "
        "*“IELTS Exam Hall”*ida sinab ko‘rishga nima deysiz? 🎧📘"
    )

    async with async_session() as session:
        # Foydalanuvchi bor-yo'qligini tekshirish
        exists = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = exists.scalars().first()
        if not user:
            full_name = (message.from_user.full_name or "").strip()
            new_user = User(
                telegram_id=message.from_user.id,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                full_name=full_name
            )
            session.add(new_user)
            await session.commit()

    # Local rasm yuborish
    image = FSInputFile('niner.jpg')

    await message.answer_photo(
        photo=image,
        caption=text,
        reply_markup=kb
    )

@dp.callback_query(lambda c: c.data == "xa")
async def button_click(callback: types.CallbackQuery):
    async with async_session() as session:
        # Foydalanuvchini olish
        user_res = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user_res.scalars().first()
        if user:
            # Xa bosganini tekshirish
            xa_exists_res = await session.execute(
                select(ButtonClick)
                .where(ButtonClick.user_id == user.id)
                .where(ButtonClick.button == "xa")
            )
            xa_exists = xa_exists_res.scalars().first()

            if not xa_exists:
                # Faqat birinchi marta qo'shish
                click = ButtonClick(user_id=user.id, button="xa")
                session.add(click)
                await session.commit()

            # Video yuborish
            from aiogram.types import FSInputFile
            # video = FSInputFile("round_2025-11-26_15-17-20.mp4")
            # await callback.message.answer_video(video=video)
            await bot.send_video_note(chat_id=callback.message.chat.id, video_note="DQACAgUAAxkBAAIJ32km46aExDCnDPB81U05CM2pz7omAAIlFwACCq05VbUC_rBoimEbNgQ")
            await bot.send_message(chat_id=callback.message.chat.id, text="https://t.me/pretest_uzbekistan")
    await callback.answer()

class PostStates(StatesGroup):
    waiting_for_media = State()
    waiting_for_caption = State()
    waiting_for_confirm = State()

# ======================== POST FSM ========================= #

class PostFSM(StatesGroup):
    waiting_for_media = State()
    waiting_for_caption = State()


# ======================== /post COMMAND ========================= #

@dp.message(F.text == "/post")
async def cmd_post(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Siz admin emassiz.")
        return
    await message.answer("Post uchun rasm, video yoki dumaloq video yuboring:")
    await state.set_state(PostFSM.waiting_for_media)


# ======================== MEDIA QABUL QILISH ========================= #

@dp.message(PostFSM.waiting_for_media, F.photo | F.video | F.video_note)
async def process_media(message: types.Message, state: FSMContext):
    if message.photo:
        media_type = "photo"
        media_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_id = message.video.file_id
    elif message.video_note:
        media_type = "video_note"
        media_id = message.video_note.file_id

    await state.update_data(media_type=media_type, media_id=media_id)
    await message.answer("Endi caption yozing (video_note uchun caption alohida jo‘natiladi):")
    await state.set_state(PostFSM.waiting_for_caption)
# ======================== CAPTION QABUL QILISH ========================= #

@dp.message(PostFSM.waiting_for_caption)
async def process_caption(message: types.Message, state: FSMContext):
    data = await state.get_data()
    media_type = data.get("media_type")
    media_id = data.get("media_id")
    caption = message.text

    await state.update_data(caption=caption)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Tasdiqlash", callback_data="approve_post_send")]]
    )

    # Admin preview
    if media_type == "photo":
        await message.answer_photo(photo=media_id, caption=caption, reply_markup=kb)
    elif media_type == "video":
        await message.answer_video(video=media_id, caption=caption, reply_markup=kb)
    elif media_type == "video_note":
        await message.answer_video_note(video_note=media_id, reply_markup=kb)
        if caption.strip():
            await message.answer(caption)

    await state.set_state(None)

# ======================== POSTNI TASDIQLASH ========================= #

# Tasdiqlash va userlarga yuborish
@dp.callback_query(F.data == "approve_post_send")
async def approve_post_send(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media_type = data.get("media_type")
    media_id = data.get("media_id")
    caption = data.get("caption", "")

    async with async_session() as session:
        result = await session.execute(
            select(User.telegram_id).join(ButtonClick).where(ButtonClick.button == "xa")
        )
        users = result.scalars().all()

    for tg_id in users:
        try:
            if media_type == "photo":
                await bot.send_photo(tg_id, photo=media_id, caption=caption)
            elif media_type == "video":
                await bot.send_video(tg_id, video=media_id, caption=caption)
            elif media_type == "video_note":
                await bot.send_video_note(tg_id, video_note=media_id)
                if caption.strip():
                    await bot.send_message(tg_id, caption)
        except Exception as e:
            print(f"Xatolik {tg_id} ga yuborishda: {e}")

    await callback.answer("Post barcha Xa bosganlarga yuborildi.")
    await state.clear()
# ---------------- FastAPI Dashboard ---------------- #
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    async with async_session() as session:
        # Start bosgan barcha userlar
        users_res = await session.execute(select(User))
        users = users_res.scalars().all()

        # Xa bosganlar count
        xa_count_res = await session.execute(
            select(func.count(ButtonClick.id)).where(ButtonClick.button == "xa")
        )
        xa_count = xa_count_res.scalar()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "users": users,
        "xa_count": xa_count
    })


# ---------------- Run Both ---------------- #
async def main():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run bot and FastAPI together
    from uvicorn import Config, Server
    config = Config(app=app, host="0.0.0.0", port=8888, log_level="info")
    server = Server(config)
    await asyncio.gather(dp.start_polling(bot), server.serve())


if __name__ == "__main__":
    logger.info("Bot ishga tushdi...")
    asyncio.run(main())
