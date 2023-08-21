import asyncio
import io
import random
import tempfile
from contextlib import suppress
from time import time

from PIL import Image
from aiogram import F, Router, exceptions, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.make_image import make_image

router = Router()

TIME = 60


class Check(StatesGroup):
    check = State()


@router.message(F.chat.type == "private", Command('start'))
async def start_handler(message: types.Message):
    await message.answer("Привіт. Я - бот для захисту твоїх чатів від спамерів. \n"
                         "Додай мене до чату і дай права адміністратора на кік та видалення повідомлень.")


@router.chat_member(lambda member: member.new_chat_member.status == 'member')
async def chat_member_handler(chat_member: types.ChatMemberUpdated, state: FSMContext):
    bot_id = state.bot.id
    new_user_id = chat_member.new_chat_member.user.id
    if new_user_id == bot_id:
        return await state.bot.send_message(chat_member.chat.id, "Привіт, дай мені права адміністратора на кік та видалення повідомлень")

    question, answer = make_question()
    image_bytes = make_image(question, TIME)

    bot_message = await state.bot.send_photo(
        chat_member.chat.id,
        photo=types.BufferedInputFile(image_bytes, filename="image.png"),
        caption=f"@{chat_member.new_chat_member.user.username}, відправте рішення арифметичної задачі,"
                " інакше будете додані до чорного списку чату.",
        reply_markup=types.ForceReply(selective=True)
    )

    await state.update_data(
        answer=answer,
        bot_message=bot_message,
    )
    await state.set_state(Check.check)
    await asyncio.sleep(TIME)

    data = await state.get_data()
    if data and data['bot_message'] == bot_message:  # Если пользователь не ответил то data еще не очищен
        await kick_user(state, chat_member.chat.id, new_user_id, chat_member.new_chat_member.user.username)  # и bot_message-ы совпадают.   в таком случае кикаем
        await state.set_state(None)  # и очищаем data и state


@router.message(StateFilter(Check.check))
async def answer_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    is_check_passed = message.text and str(data['answer']) in message.text

    if not is_check_passed:
        await kick_user(state, message.chat.id, message.from_user.id, message.from_user.username)

    bot_message = data['bot_message']
    await state.bot.delete_message(bot_message.chat.id, bot_message.message_id)
    await message.delete()
    await state.update_data(bot_message=None)
    await state.set_state(None)


def make_question():
    a, b, c = [random.randint(1, 9) for _ in range(3)]
    question = f'{a} + {b} * {c}'
    answer = a + b * c
    return question, answer


async def kick_user(state, chat_id, user_id, username):
    try:
        await state.bot.ban_chat_member(chat_id, user_id, until_date=int(time()) + 35) # бан на 35 сек. <30 = inf
        await state.bot.unban_chat_member(chat_id, user_id)
    except exceptions.TelegramBadRequest:
        await state.bot.send_message(chat_id, f'Не можу кікнути юзера або видалити повідомлення, дайте адмінку')
