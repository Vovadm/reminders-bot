from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
from aiogram import Dispatcher, Bot, F, types
import os
from re import compile, findall
from time import time, ctime

from dotenv import load_dotenv
from sqlalchemy import DECIMAL, Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.future import select


load_dotenv()
bot = Bot(token=os.get_env("TOKEN"))
DB_URL = os.get_env("DB_URL")
dp = Dispatcher(storage=MemoryStorage())
tasksdata = {}
cancelKB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True
)
clearKB = ReplyKeyboardMarkup(keyboard=[])
backKB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Назад", callback_data="show_tasks"),
        ]
    ],
    resize_keyboard=True,
)
backKB2 = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Выполнено", callback_data="sss"),
            InlineKeyboardButton(text="Назад", callback_data="show_tasks"),
        ]
    ],
    resize_keyboard=True,
)

minutesPattern = compile(r"\s*([1-9][0-9]?)m\s*")
daysPattern = compile(r"\s*([1-6])d\s*")
weeksPattern = compile(r"\s*([1-5])w\s*")


engine = create_async_engine(DB_URL, echo=True)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)
Base = declarative_base()


class Tasks(Base):
    __tablename__ = "tasks"

    num = Column(Integer, primary_key=True)
    id = Column(Integer)
    name = Column(String(255))
    description = Column(String(255))
    expires = Column(DECIMAL(20, 10))
    points = Column(Integer)


class Users(Base):
    __tablename__ = "users"

    num = Column(Integer, primary_key=True)
    id = Column(Integer)
    name = Column(String(255))
    username = Column(String(255))
    points = Column(Integer)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)


async def get_data(
    session: AsyncSession, id: int, username: str = None, name: str = None
):
    result = await session.execute(select(Users).where(Users.id == id))
    user = result.scalars().first()

    if user:
        if username:
            user.username = username
        if name:
            user.name = name
        await session.commit()
        return user

    new_user = Users(id=id, username=username, name=name, points=0)
    session.add(new_user)
    await session.commit()
    return new_user


class TaskStates(StatesGroup):
    waiting_for_task_name = State()
    waiting_for_task_description = State()
    waiting_for_task_expire = State()
    waiting_for_task_points = State()
    enteredData = {}


@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "Добро пожаловать в бот-ежедневник\nчто бы увидеть функции бота нажмите:\n/menu"
    )


@dp.message(Command("menu"))
async def menu_command(message: types.Message):
    async with AsyncSessionLocal() as session:
        await get_data(
            session=session,
            id=message.from_user.id,
            username=message.from_user.username,
            name=message.from_user.first_name,
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Добавить задачу", callback_data="add_task"
                    )
                ],
                [InlineKeyboardButton(text="Список задач", callback_data="show_tasks")],
            ]
        )
        await message.answer("Привет! Выберите действие:", reply_markup=keyboard)


@dp.callback_query(F.data == "add_task")
async def add_task_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите имя задачи:", reply_markup=cancelKB)
    await state.set_state(TaskStates.waiting_for_task_name)
    await callback.answer()


@dp.message(TaskStates.waiting_for_task_name)
async def get_task_name(message: types.Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tasks).where(
                Tasks.name == message.text.strip(),
                Tasks.id == message.from_user.id,
            )
        )
        task = result.scalars().first()

        if task is None:
            tasksdata[message.from_user.id] = {"name": message.text.strip()}
            await state.clear()
            await state.set_state(TaskStates.waiting_for_task_description)
            await message.reply("Введите описание задачи", reply_markup=cancelKB)
        else:
            await message.reply(
                "Задача с таким именем уже существует\nУдалите её или придумайте другое имя",
                reply_markup=cancelKB,
            )
            await state.set_state(TaskStates.waiting_for_task_name)
            await state.clear()


@dp.message(TaskStates.waiting_for_task_description)
async def get_description_text(message: types.Message, state: FSMContext):
    if message.text.strip() == "Отмена":
        await state.clear()
        return await start_command(message)
    tasksdata[message.from_user.id]["description"] = message.text.strip()
    await state.clear()
    await state.set_state(TaskStates.waiting_for_task_points)
    await message.reply(
        "Введите количество баллов которые вы получите за выполнение задачи",
        reply_markup=cancelKB,
    )


@dp.message(TaskStates.waiting_for_task_points)
async def get_task_points(message: types.Message, state: FSMContext):
    if message.text.strip() == "Отмена":
        await state.clear()
        return await start_command(message)
    tasksdata[message.from_user.id]["points"] = message.text.strip()
    await state.clear()
    await state.set_state(TaskStates.waiting_for_task_expire)
    await message.reply(
        "Введите время через которое надо напомнить об этой задаче",
        reply_markup=cancelKB,
    )


@dp.message(TaskStates.waiting_for_task_expire)
async def get_expire_data(message: types.Message, state: FSMContext):
    if message.text.strip() == "Отмена":
        await state.clear()
        return await start_command(message)

    texts = message.text.strip()

    print(f"Полученный ввод: {texts}")

    minute = (
        int(findall(minutesPattern, texts)[0]) if findall(minutesPattern, texts) else 0
    )
    day = int(findall(daysPattern, texts)[0]) if findall(daysPattern, texts) else 0
    weeks = int(findall(weeksPattern, texts)[0]) if findall(weeksPattern, texts) else 0

    print(f"Минуты: {minute}, Дни: {day}, Недели: {weeks}")

    secs = (minute * 60) + (day * 24 * 3600) + (weeks * 7 * 24 * 3600)

    if secs == 0:
        await message.reply(
            "Вы не ввели время или ввели его неправильно.\n"
            "Пример: 1m 1d 1w - 1 минута, 1 день, 1 неделя соответственно.",
            reply_markup=cancelKB,
        )
        await state.set_state(TaskStates.waiting_for_task_expire)
        return

    expireDate = time() + secs

    expireDate_float = float(expireDate)
    print(type(expireDate_float))

    print(
        f"Время истечения (timestamp): {expireDate_float}, Читаемое: {ctime(expireDate_float)}"
    )

    name = tasksdata[message.from_user.id]["name"]
    description = tasksdata[message.from_user.id]["description"]
    points = tasksdata[message.from_user.id]["points"]

    new_task = Tasks(
        id=message.from_user.id,
        name=name,
        description=description,
        expires=expireDate_float,
        points=points,
    )

    async with AsyncSessionLocal() as session:
        session.add(new_task)
        await session.commit()

    await state.clear()
    await message.reply(
        f"Задача {name}\nОписание задачи\n<blockquote>{description}</blockquote>\n\nНужно выполнить до {ctime(expireDate_float)}",
        reply_markup=backKB,
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "show_tasks")
async def show_tasks(callback: types.CallbackQuery):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tasks).where(Tasks.id == callback.from_user.id)
        )
        tasks = result.scalars().all()

        if tasks:
            keyboard = [
                [InlineKeyboardButton(text=task.name, callback_data=task.name)]
                for task in tasks
            ]
            await callback.message.answer(
                "Выберите задачу",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            )
        else:
            await callback.message.answer("Список задач пуст.")

        await callback.answer()


async def taskFilter(call: types.CallbackQuery) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tasks.name).where(Tasks.id == call.from_user.id)
        )
        tasks = [task[0] for task in result.fetchall()]

    return call.data in tasks


@dp.callback_query(taskFilter)
async def show_current_task(call: types.CallbackQuery):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tasks).where(Tasks.id == call.from_user.id, Tasks.name == call.data)
        )
        task = result.scalars().first()

        if not task:
            return

        expireDate = task.expires
        name = task.name
        description = task.description
        points = task.points

        if expireDate < time():
            result = await session.execute(
                select(Users).where(Users.id == call.from_user.id)
            )
            user = result.scalars().first()
            if user:
                user.points -= points
                await session.commit()

            await bot.answer_callback_query(
                call.id,
                f"Задача не была выполнена в срок!\nВы потеряли {points} баллов",
            )
        else:
            result = await session.execute(
                select(Users).where(Users.id == call.from_user.id)
            )
            user = result.scalars().first()
            if user:
                if user.points is None:
                    user.points = 0
                user.points += points
                await session.commit()

            await bot.answer_callback_query(
                call.id,
                f"Задача была выполнена в срок!\nВы получили {points} баллов",
            )

        expireDate_float = float(expireDate)
        await call.message.reply(
            f"ID: {task.id}\nЗадача {name}\nОписание задачи\n<blockquote>{description}</blockquote>\n\nНужно выполнить до {ctime(expireDate_float)}",
            reply_markup=backKB2,
            parse_mode="HTML",
        )


async def main():
    print("dadadada")
    await create_tables()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
