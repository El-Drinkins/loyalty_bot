from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from ..models import AsyncSessionLocal, Category, Brand, Model

router = Router()

# Константы для фильтрации
INSTAGRAM_URL = "https://instagram.com/fototehnika_arenda_ufa"
TELEGRAM_URL = "https://t.me/el_drinkins"


def get_category_word(category_name: str) -> str:
    """Возвращает правильное слово для категории"""
    category_words = {
        "Объективы": "объективов",
        "Фотоаппараты": "фотоаппаратов",
        "Освещение": "единиц",
        "Звук": "единиц",
        "Аксессуары": "единиц",
        "Экшен камеры": "камер"
    }
    return category_words.get(category_name, "моделей")


async def get_categories():
    """Получает все активные категории"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Category)
            .where(Category.is_active == True)
            .order_by(Category.sort_order)
        )
        return result.scalars().all()


async def get_brands_by_category(category_id: int):
    """Получает бренды для категории с количеством моделей и подгруженной категорией"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Brand, func.count(Model.id).label('count'))
            .options(selectinload(Brand.category))
            .outerjoin(Model, Brand.id == Model.brand_id)
            .where(Brand.category_id == category_id, Brand.is_active == True)
            .group_by(Brand.id)
            .order_by(Brand.sort_order)
        )
        brands_with_count = result.all()
        return [(brand, count) for brand, count in brands_with_count]


async def get_models_by_brand(brand_id: int, mount_filter: str = None):
    """Получает модели для бренда с опциональной фильтрацией по байонету"""
    async with AsyncSessionLocal() as session:
        query = (
            select(Model)
            .where(Model.brand_id == brand_id, Model.is_active == True)
        )
        
        if mount_filter and mount_filter != "all":
            query = query.where(Model.mount_type == mount_filter)
        
        result = await session.execute(query.order_by(Model.name))
        return result.scalars().all()


async def get_mount_types_for_brand(brand_id: int, category_id: int = None):
    """Получает уникальные типы байонетов для бренда с количеством моделей
       Только для категории Объективы"""
    # Проверяем категорию бренда
    if category_id:
        async with AsyncSessionLocal() as session:
            brand = await session.get(Brand, brand_id)
            if brand and brand.category_id != 4:  # 4 - ID категории Объективы
                return []  # Не показываем фильтр для других категорий
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Model.mount_type, func.count(Model.id).label('count'))
            .where(Model.brand_id == brand_id, Model.is_active == True, Model.mount_type.is_not(None))
            .group_by(Model.mount_type)
        )
        mounts = result.all()
        return [(m[0], m[1]) for m in mounts if m[0] is not None]


async def get_model_details(model_id: int):
    """Получает детали модели"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Model)
            .where(Model.id == model_id)
            .options(selectinload(Model.brand))
        )
        return result.scalar_one_or_none()


def format_specs(specs: str) -> str:
    """Форматирует характеристики для отображения"""
    if not specs:
        return "• Нет данных"
    
    if specs.strip().startswith('•'):
        return specs
    
    lines = specs.strip().split('\n')
    return '\n'.join([f"• {line.strip()}" for line in lines if line.strip()])


def format_equipment(equipment: str) -> str:
    """Форматирует комплектацию для отображения"""
    if not equipment:
        return "• Нет данных"
    
    lines = equipment.strip().split('\n')
    return '\n'.join([f"• {line.strip()}" for line in lines if line.strip()])


def format_price(price: int) -> str:
    """Форматирует цену с пробелами"""
    return f"{price:,}".replace(",", " ")


@router.message(Command("catalog"))
async def cmd_catalog(message: Message):
    await show_categories(message)


@router.message(F.text == "📸 Каталог")
async def catalog_button(message: Message):
    await cmd_catalog(message)


async def show_categories(message: Message):
    categories = await get_categories()
    
    if not categories:
        await message.answer("📭 Каталог временно недоступен. Попробуйте позже.")
        return
    
    buttons = []
    row = []
    for i, category in enumerate(categories):
        row.append(InlineKeyboardButton(
            text=f"{category.icon} {category.name}",
            callback_data=f"cat_{category.id}"
        ))
        if len(row) == 2 or i == len(categories) - 1:
            buttons.append(row)
            row = []
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        "📸 **КАТАЛОГ ТЕХНИКИ**\n\nВыберите категорию:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def show_brands(callback: CallbackQuery, category_id: int):
    brands_with_count = await get_brands_by_category(category_id)
    
    if not brands_with_count:
        await callback.message.edit_text(
            "📭 В этой категории пока нет техники.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")]
            ])
        )
        await callback.answer()
        return
    
    # Получаем название категории
    category_name = brands_with_count[0][0].category.name
    category_word = get_category_word(category_name)
    
    buttons = []
    for brand, count in brands_with_count:
        buttons.append([InlineKeyboardButton(
            text=f"📷 {brand.name} ({count})",
            callback_data=f"brand_{brand.id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        f"📷 **{category_name}**\n\nВыберите бренд:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


async def show_mount_filter(callback: CallbackQuery, brand_id: int, brand_name: str):
    """Показывает выбор байонета для объективов"""
    mount_types = await get_mount_types_for_brand(brand_id)
    
    models = await get_models_by_brand(brand_id)
    total_count = len(models)
    
    buttons = []
    
    buttons.append([InlineKeyboardButton(
        text=f"🔘 Все ({total_count})",
        callback_data=f"mount_all_{brand_id}"
    )])
    
    for mount_type, count in mount_types:
        display_name = mount_type.upper()
        buttons.append([InlineKeyboardButton(
            text=f"🔘 {display_name} ({count})",
            callback_data=f"mount_{mount_type}_{brand_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад к брендам", callback_data=f"back_to_brands_{brand_id}")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        f"📷 **{brand_name}** ({total_count} объективов)\n\nВыберите тип байонета:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


async def show_models(callback: CallbackQuery, brand_id: int, brand_name: str, mount_filter: str = None, category_name: str = None):
    """Показывает модели для выбранного бренда с фильтром"""
    models = await get_models_by_brand(brand_id, mount_filter)
    
    if not models:
        await callback.message.edit_text(
            f"📭 Нет моделей с фильтром '{mount_filter}'",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к выбору байонета", callback_data=f"back_to_mount_{brand_id}")]
            ])
        )
        await callback.answer()
        return
    
    # Получаем категорию для правильного слова
    if not category_name:
        async with AsyncSessionLocal() as session:
            brand = await session.get(Brand, brand_id)
            if brand:
                category_name = brand.category.name
    category_word = get_category_word(category_name)
    
    if mount_filter and mount_filter != "all":
        title = f"📷 **{brand_name} {mount_filter.upper()}** ({len(models)} {category_word})"
    else:
        title = f"📷 **{brand_name}** ({len(models)} {category_word})"
    
    buttons = []
    for model in models:
        buttons.append([InlineKeyboardButton(
            text=f"📷 {model.name}",
            callback_data=f"model_{model.id}"
        )])
    
    mount_types = await get_mount_types_for_brand(brand_id)
    if mount_types:
        filter_text = f"🔍 Фильтр: {mount_filter.upper() if mount_filter else 'Все'}"
        buttons.append([InlineKeyboardButton(text=filter_text, callback_data=f"change_filter_{brand_id}")])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад к брендам", callback_data=f"back_to_brands_{brand_id}")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        f"{title}\n\nВыберите модель:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


async def show_model_detail(callback: CallbackQuery, model_id: int):
    model = await get_model_details(model_id)
    
    if not model:
        await callback.answer("Модель не найдена", show_alert=True)
        return
    
    text = f"📷 **{model.name}**\n\n"
    
    text += "📸 **Характеристики:**\n"
    text += format_specs(model.specs) + "\n\n"
    
    text += f"💰 **Цена:** {format_price(model.price_per_day)} ₽/сутки\n\n"
    
    if model.default_equipment:
        text += "📦 **Комплектация:**\n"
        text += format_equipment(model.default_equipment) + "\n\n"
    
    buttons = [
        [InlineKeyboardButton(text="📸 Заказать в Instagram", url=INSTAGRAM_URL)],
        [InlineKeyboardButton(text="📱 Заказать в Telegram", url=TELEGRAM_URL)],
        [InlineKeyboardButton(text="◀️ Назад к моделям", callback_data=f"back_to_models_{model.brand_id}")]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    if model.image_url:
        try:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=model.image_url,
                caption=text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")
            await callback.message.edit_text(
                text + "\n⚠️ Фото временно недоступно",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    else:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    await callback.answer()


@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    await show_categories(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("cat_"))
async def category_callback(callback: CallbackQuery):
    category_id = int(callback.data.split("_")[1])
    await show_brands(callback, category_id)
    await callback.answer()


@router.callback_query(F.data.startswith("brand_"))
async def brand_callback(callback: CallbackQuery):
    brand_id = int(callback.data.split("_")[1])
    
    # Получаем категорию бренда
    async with AsyncSessionLocal() as session:
        brand = await session.get(Brand, brand_id)
        category_id = brand.category_id if brand else None
        brand_name = brand.name if brand else "Техника"
    
    # Проверяем, нужно ли показывать фильтр байонета (только для объективов)
    if category_id == 4:  # 4 - ID категории Объективы
        mount_types = await get_mount_types_for_brand(brand_id, category_id)
        if mount_types:
            await show_mount_filter(callback, brand_id, brand_name)
        else:
            await show_models(callback, brand_id, brand_name, category_name="Объективы")
    else:
        # Для остальных категорий показываем модели без фильтра
        await show_models(callback, brand_id, brand_name, category_name=brand.category.name if brand else None)
    
    await callback.answer()


@router.callback_query(F.data.startswith("mount_all_"))
async def mount_all_callback(callback: CallbackQuery):
    brand_id = int(callback.data.split("_")[2])
    
    async with AsyncSessionLocal() as session:
        brand = await session.get(Brand, brand_id)
        brand_name = brand.name if brand else "Техника"
    
    await show_models(callback, brand_id, brand_name, "all")
    await callback.answer()


@router.callback_query(F.data.startswith("mount_"))
async def mount_filter_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    mount_type = parts[1]
    brand_id = int(parts[2])
    
    async with AsyncSessionLocal() as session:
        brand = await session.get(Brand, brand_id)
        brand_name = brand.name if brand else "Техника"
    
    await show_models(callback, brand_id, brand_name, mount_type)
    await callback.answer()


@router.callback_query(F.data.startswith("change_filter_"))
async def change_filter_callback(callback: CallbackQuery):
    brand_id = int(callback.data.split("_")[2])
    
    async with AsyncSessionLocal() as session:
        brand = await session.get(Brand, brand_id)
        brand_name = brand.name if brand else "Техника"
        category_id = brand.category_id if brand else None
    
    await show_mount_filter(callback, brand_id, brand_name)
    await callback.answer()


@router.callback_query(F.data.startswith("back_to_brands_"))
async def back_to_brands_callback(callback: CallbackQuery):
    brand_id = int(callback.data.split("_")[3])
    
    async with AsyncSessionLocal() as session:
        brand = await session.get(Brand, brand_id)
        category_id = brand.category_id if brand else None
    
    if category_id:
        await show_brands(callback, category_id)
    else:
        await show_categories(callback.message)
    
    await callback.answer()


@router.callback_query(F.data.startswith("back_to_mount_"))
async def back_to_mount_callback(callback: CallbackQuery):
    brand_id = int(callback.data.split("_")[3])
    
    async with AsyncSessionLocal() as session:
        brand = await session.get(Brand, brand_id)
        brand_name = brand.name if brand else "Техника"
    
    await show_mount_filter(callback, brand_id, brand_name)
    await callback.answer()


@router.callback_query(F.data.startswith("back_to_models_"))
async def back_to_models_callback(callback: CallbackQuery):
    brand_id = int(callback.data.split("_")[3])
    
    async with AsyncSessionLocal() as session:
        brand = await session.get(Brand, brand_id)
        brand_name = brand.name if brand else "Техника"
        category_id = brand.category_id if brand else None
    
    if category_id == 4:  # Объективы
        mount_types = await get_mount_types_for_brand(brand_id, category_id)
        if mount_types:
            await show_mount_filter(callback, brand_id, brand_name)
        else:
            await show_models(callback, brand_id, brand_name, category_name="Объективы")
    else:
        await show_models(callback, brand_id, brand_name, category_name=brand.category.name if brand else None)
    
    await callback.answer()


@router.callback_query(F.data.startswith("model_"))
async def model_callback(callback: CallbackQuery):
    model_id = int(callback.data.split("_")[1])
    await show_model_detail(callback, model_id)
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()