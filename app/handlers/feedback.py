from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from ..models import AsyncSessionLocal, User, Feedback
from ..config import settings
from ..notifications import send_telegram_notification

router = Router()

class FeedbackStates(StatesGroup):
    waiting_for_bug_report = State()
    waiting_for_improvement = State()
    waiting_for_equipment_request = State()

FEEDBACK_MESSAGES = {
    "bug": (
        "⚠️ <b>Сообщить об ошибке в боте</b>\n\n"
        "Пожалуйста, опишите проблему как можно подробнее:\n"
        "Что делали, на какие кнопки нажимали, что пошло не так, в каком разделе бота это произошло.\n\n"
        "Напишите ваше сообщение в поле для ввода текста."
    ),
    "improvement": (
        "💡 <b>Предложение по улучшению</b>\n\n"
        "Опишите вашу идею: что бы вы хотели улучшить в боте,\n"
        "какую функцию добавить, что сделать удобнее.\n\n"
        "Напишите ваше сообщение в поле для ввода текста."
    ),
    "equipment": (
        "📷 <b>Запрос на добавление техники в прокат</b>\n\n"
        "Напишите, какую фототехнику вы хотели бы видеть в прокате.\n"
        "Укажите максимально полное название модели.\n\n"
        "Примеры правильно оформленного запроса:\n"
        "✅ Canon EF 16-35mm f/2.8 II\n"
        "✅ Godox V860III для Sony\n"
        "✅ Sony FE 70-200mm f/2.8 GM II\n"
        "✅ DJI RS 4 Pro\n"
        "✅ MacBook 14 2023 M3 Pro\n\n"
        "Примеры неправильно оформленного запроса:\n"
        "❌ ширик для Canon\n"
        "❌ вспышка для Sony\n"
        "❌ что-то для видео\n"
        "❌ дрон\n"
        "❌ Мощный комп для обработки фото/видео\n\n"
        "Также рассмотрю ваше предложение на покупку любой техники под ваши задачи при аренде от трёх месяцев.\n\n"
        "Напишите ваше сообщение в поле для ввода текста."
    ),
}

async def send_to_admin(bot, user: User, feedback_type: str, text: str):
    """Сохраняет в базу и отправляет сообщение обратной связи админу"""
    type_names = {
        "bug": "⚠️ Сообщить об ошибке в боте",
        "improvement": "💡 Предложить улучшение",
        "equipment": "📷 Какую технику добавить в прокат",
    }

    # Сохраняем в базу
    async with AsyncSessionLocal() as session:
        feedback = Feedback(
            user_id=user.id,
            feedback_type=feedback_type,
            text=text
        )
        session.add(feedback)
        await session.commit()

    # Отправляем админу
    admin_msg = (
        f"📝 <b>Новое сообщение обратной связи</b>\n\n"
        f"👤 <b>От:</b> {user.full_name} (ID: {user.id})\n"
        f"📱 <b>Телефон:</b> {user.phone}\n"
        f"📌 <b>Тема:</b> {type_names.get(feedback_type, feedback_type)}\n\n"
        f"💬 <b>Текст сообщения:</b>\n"
        f"{text}"
    )

    for admin_id in settings.ADMIN_IDS:
        try:
            await send_telegram_notification(admin_id, admin_msg)
        except Exception as e:
            print(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def process_feedback(message: Message, state: FSMContext, feedback_type: str, success_text: str):
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user.scalar_one_or_none()
        if user:
            await send_to_admin(message.bot, user, feedback_type, message.text)
    await message.answer(success_text, parse_mode="HTML")
    await state.clear()

@router.callback_query(F.data == "feedback_bug")
async def feedback_bug(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(FEEDBACK_MESSAGES["bug"], parse_mode="HTML")
    await state.set_state(FeedbackStates.waiting_for_bug_report)
    await callback.answer()

@router.callback_query(F.data == "feedback_improvement")
async def feedback_improvement(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(FEEDBACK_MESSAGES["improvement"], parse_mode="HTML")
    await state.set_state(FeedbackStates.waiting_for_improvement)
    await callback.answer()

@router.callback_query(F.data == "feedback_equipment")
async def feedback_equipment(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(FEEDBACK_MESSAGES["equipment"], parse_mode="HTML")
    await state.set_state(FeedbackStates.waiting_for_equipment_request)
    await callback.answer()

@router.message(FeedbackStates.waiting_for_bug_report)
async def process_bug_report(message: Message, state: FSMContext):
    await process_feedback(message, state, "bug", "✅ Спасибо! Ваше сообщение об ошибке отправлено администратору.")

@router.message(FeedbackStates.waiting_for_improvement)
async def process_improvement(message: Message, state: FSMContext):
    await process_feedback(message, state, "improvement", "✅ Спасибо! Ваше предложение отправлено администратору.")

@router.message(FeedbackStates.waiting_for_equipment_request)
async def process_equipment_request(message: Message, state: FSMContext):
    await process_feedback(message, state, "equipment", "✅ Спасибо! Ваш запрос на технику отправлен администратору.")