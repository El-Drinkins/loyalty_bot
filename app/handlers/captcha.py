import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..keyboards import contact_keyboard

router = Router()

class CaptchaStates(StatesGroup):
    waiting_for_answer = State()

class MathCaptcha:
    """Генератор математической капчи"""
    
    def __init__(self):
        self.operations = ['+', '-', '*']
    
    def generate(self):
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        op = random.choice(self.operations)
        
        if op == '+':
            result = a + b
        elif op == '-':
            if a < b:
                a, b = b, a
            result = a - b
        else:
            a = random.randint(1, 10)
            b = random.randint(1, 10)
            result = a * b
        
        question = f"{a} {op} {b} = ?"
        return question, result
    
    def create_keyboard(self, correct_answer):
        options = [correct_answer]
        while len(options) < 4:
            wrong = correct_answer + random.randint(-5, 5)
            if wrong != correct_answer and wrong not in options and wrong > 0:
                options.append(wrong)
        
        random.shuffle(options)
        
        keyboard = []
        row = []
        for i, opt in enumerate(options):
            row.append(InlineKeyboardButton(text=str(opt), callback_data=f"captcha_{opt}"))
            if (i + 1) % 2 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(text="🔄 Новый пример", callback_data="captcha_refresh")])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

captcha = MathCaptcha()

@router.callback_query(F.data == "captcha_refresh")
async def refresh_captcha(callback: CallbackQuery, state: FSMContext):
    """Обновляет капчу"""
    question, answer = captcha.generate()
    await state.update_data(captcha_answer=answer)
    
    keyboard = captcha.create_keyboard(answer)
    await callback.message.edit_text(
        f"🔐 **Проверка: решите пример**\n\n{question}\n\nВыберите правильный ответ:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("captcha_"))
async def check_captcha(callback: CallbackQuery, state: FSMContext):
    """Проверяет ответ на капчу и отправляет кнопку с контактом"""
    answer = int(callback.data.split("_")[1])
    data = await state.get_data()
    correct_answer = data.get("captcha_answer")
    
    if answer == correct_answer:
        # Капча пройдена
        await state.update_data(captcha_passed=True)
        
        # Удаляем сообщение с капчей
        await callback.message.delete()
        
        # Отправляем новое сообщение с просьбой отправить контакт и клавиатурой
        await callback.message.answer(
            "✅ Капча пройдена!\n\n"
            "📱 Теперь, пожалуйста, отправьте ваш номер телефона, нажав на кнопку ниже.\n"
            "Это необходимо для идентификации в системе лояльности.",
            reply_markup=contact_keyboard()
        )
        await callback.answer()
    else:
        # Неправильный ответ
        await callback.answer("❌ Неправильный ответ. Попробуйте еще раз.", show_alert=True)