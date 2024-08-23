from telethon import TelegramClient, events, Button
import json
import os
import sys
import csv
import xlsxwriter
from datetime import datetime, timedelta
from asyncio import sleep

from config import api_id, api_hash, bot_token

client = TelegramClient('bot_session', api_id, api_hash)

users_pending_approval = {}
approved_users = {}
orders = {}
poll_message_id = None
poll_active = False
menu_options = []
menu_items = {}
poll_end_time = None
data_file = 'users_data.json'
admin_states = {}
confirm_states = {}
admin_username = "@FameOfReality"  # Ваше имя пользователя в Telegram
admin_id = None

# Load data from file
def load_data():
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    return {}

# Save data to file
def save_data(data):
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Initialize approved_users with data from file
approved_users = load_data()

# Helper functions
def save_orders_to_file():
    date_today = datetime.now().strftime("%d.%m.%Y")
    with open(f'order_summary_{date_today}.txt', 'w', encoding='utf-8-sig') as f:
        for option, users in orders.items():
            if isinstance(users, list):
                f.write(f"{menu_items.get(str(option), 'Неизвестный обед')} - {len(users)} шт\n")

def save_distribution_to_excel():
    date_today = datetime.now().strftime("%d.%m.%Y")
    file_path = f'order_distribution_{date_today}.xlsx'

    try:
        workbook = xlsxwriter.Workbook(file_path)
        worksheet = workbook.add_worksheet()

        col = 0
        for option in sorted(orders.keys(), key=lambda x: int(x)):
            if isinstance(orders[option], list):
                row = 1
                worksheet.write(0, col, menu_items.get(str(option), 'Неизвестный обед'))
                for user_id in orders[option]:
                    worksheet.write(row, col, approved_users.get(str(user_id), 'Неизвестный пользователь'))
                    row += 1
                col += 1

        workbook.close()
    except Exception as e:
        print(f"Error saving Excel file: {e}")
        # Попробуем создать новый файл с другим именем
        try:
            file_path = f'order_distribution_{date_today}_{datetime.now().strftime("%H%M%S")}.xlsx'
            workbook = xlsxwriter.Workbook(file_path)
            worksheet = workbook.add_worksheet()

            col = 0
            for option in sorted(orders.keys(), key=lambda x: int(x)):
                if isinstance(orders[option], list):
                    row = 1
                    worksheet.write(0, col, menu_items.get(str(option), 'Неизвестный обед'))
                    for user_id in orders[option]:
                        worksheet.write(row, col, approved_users.get(str(user_id), 'Неизвестный пользователь'))
                        row += 1
                    col += 1

            workbook.close()
        except Exception as e:
            print(f"Failed to save Excel file again: {e}")
            return None
    
    return file_path

def save_poll_results_to_csv():
    date_today = datetime.now().strftime("%d.%m.%Y")
    file_path = f'poll_results_{date_today}.csv'
    with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
        fieldnames = ['User ID', 'Full Name', 'Choice']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for user_id, choice in orders.items():
            if not isinstance(choice, list):
                writer.writerow({
                    'User ID': user_id,
                    'Full Name': approved_users.get(str(user_id), 'Неизвестный пользователь'),
                    'Choice': menu_items.get(str(choice), 'Неизвестный обед')
                })
    return file_path

async def get_user_id(username):
    try:
        user = await client.get_entity(username)
        return user.id
    except:
        return None

def is_admin(user_id):
    return user_id == admin_id

async def update_admin(new_admin_username):
    global admin_id, admin_username
    new_admin_id = await get_user_id(new_admin_username)
    if new_admin_id:
        admin_id = new_admin_id
        admin_username = new_admin_username
        return True
    return False

async def end_poll():
    global poll_active, orders, menu_options, menu_items, poll_end_time

    poll_active = False
    await client.send_message(admin_id, "Опрос завершен автоматически.")
    save_orders_to_file()
    file_path = save_distribution_to_excel()
    if file_path:
        await client.send_message(admin_id, f"Результаты опроса сохранены в файл: {file_path}")
    else:
        await client.send_message(admin_id, "Ошибка при сохранении файла результатов опроса.")
    
    for user_id in list(approved_users.keys()):
        try:
            await client.send_message(int(user_id), "Опрос завершен. Спасибо за участие!")
        except ValueError:
            pass

    # Очищаем позиции меню и заказы
    menu_options.clear()
    menu_items.clear()
    orders.clear()
    poll_end_time = None

# Handlers
@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    buttons = [Button.inline("Регистрация", b'register')]
    await event.respond("Добро пожаловать! Пожалуйста, зарегистрируйтесь, нажав на кнопку ниже.", buttons=buttons)
    raise events.StopPropagation

@client.on(events.CallbackQuery(data=b'register'))
async def register(event):
    user_id = event.sender_id
    if str(user_id) in approved_users:
        await event.answer("Вы уже зарегистрированы и подтверждены.")
    else:
        await client.send_message(user_id, "Пожалуйста, введите ваши ФИО:")
        @client.on(events.NewMessage(from_users=user_id))
        async def get_full_name(event):
            full_name = event.message.message
            users_pending_approval[user_id] = full_name
            await client.send_message(user_id, "Ваши данные отправлены на проверку, ожидайте подтверждения.")
            await client.send_message(admin_id, f"Пользователь {full_name} (ID: {user_id}) запрашивает подтверждение.",
                                      buttons=[Button.inline("Подтвердить", f'approve_{user_id}'.encode())])
            client.remove_event_handler(get_full_name)

@client.on(events.CallbackQuery(pattern=b'approve_'))
async def approve(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    user_id = int(event.data.decode('utf-8').split('_')[1])
    if user_id in users_pending_approval:
        full_name = users_pending_approval.pop(user_id)
        if str(user_id) not in approved_users:
            approved_users[str(user_id)] = full_name
        save_data(approved_users)
        await client.send_message(user_id, "Ваши данные подтверждены, теперь вы можете делать заказы.")
        await event.answer(f"Пользователь {full_name} подтвержден.")
    else:
        await event.answer("Пользователь не найден в списке на проверку.")

@client.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    if not is_admin(event.sender_id):
        await event.respond("У вас нет прав для выполнения этой команды.")
        return

    # Сбрасываем состояние админа
    admin_states.pop(event.sender_id, None)

    buttons = [
        [Button.inline("Создать опрос", b'create_poll')],
        [Button.inline("Закрыть опрос", b'close_poll')],
        [Button.inline("Добавить опцию меню", b'add_menu_option')],
        [Button.inline("Удалить опцию меню", b'remove_menu_option')],
        [Button.inline("Готовность обедов", b'order_ready')],
        [Button.inline("Список пользователей", b'list_users')],
        [Button.inline("Удалить пользователя", b'remove_user')],
        [Button.inline("Очистить список пользователей", b'clear_users')],
        [Button.inline("Перезапустить бота", b'restart')],
        [Button.inline("Назначить нового админа", b'assign_new_admin')]
    ]
    await event.respond("Панель администратора", buttons=buttons)

@client.on(events.CallbackQuery(data=b'create_poll'))
async def create_poll(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    global poll_message_id, poll_active, poll_end_time
    poll_active = True
    await client.send_message(event.sender_id, "Введите время окончания опроса (в формате ЧЧ:ММ):")
    admin_states[event.sender_id] = 'awaiting_poll_end_time'

@client.on(events.NewMessage)
async def handle_admin_input(event):
    user_id = event.sender_id
    if user_id in admin_states:
        state = admin_states[user_id]
        
        if state == 'awaiting_poll_end_time':
            poll_end_time_str = event.message.message
            try:
                global poll_end_time
                poll_end_time = datetime.strptime(poll_end_time_str, '%H:%M').time()
                poll_text = "Меню на сегодня:\n"
                for i, option in enumerate(menu_options):
                    poll_text += f"Комплексный обед {i + 1}: {option}\n"
                buttons = [[Button.inline(f"Комплексный обед {i + 1}", f'poll_{i + 1}'.encode())] for i in range(len(menu_options))]
                if not buttons:
                    await client.send_message(user_id, "Ошибка: меню пусто. Сначала добавьте опции меню.")
                    admin_states.pop(user_id, None)
                else:
                    for user_id in approved_users.keys():
                        try:
                            await client.send_message(int(user_id), poll_text)
                            await client.send_message(int(user_id), "Выберите ваш обед:", buttons=buttons)
                        except ValueError:
                            pass
                    admin_states.pop(user_id, None)
                    # Запустить таймер до окончания опроса
                    remaining_time = (datetime.combine(datetime.today(), poll_end_time) - datetime.now()).total_seconds()
                    if remaining_time > 0:
                        await sleep(remaining_time)
                        await end_poll()
            except ValueError:
                admin_states.pop(user_id, None)
                await event.respond("Неверный формат времени. Попробуйте еще раз.")
        elif state == 'awaiting_new_menu_option':
            new_option = event.message.message
            menu_options.append(new_option)
            menu_items[str(len(menu_options))] = new_option
            await event.respond(f"Опция '{new_option}' добавлена в меню.")
            admin_states.pop(user_id, None)
        elif state == 'awaiting_remove_menu_option':
            option_to_remove = event.message.message
            if option_to_remove in menu_options:
                index = menu_options.index(option_to_remove)
                menu_options.remove(option_to_remove)
                menu_items.pop(str(index + 1), None)
                await event.respond(f"Опция '{option_to_remove}' удалена из меню.")
            else:
                await event.respond(f"Опция '{option_to_remove}' не найдена в меню.")
            admin_states.pop(user_id, None)
        elif state == 'awaiting_user_id_to_remove':
            try:
                user_id_to_remove = int(event.message.message)
                if str(user_id_to_remove) in approved_users:
                    full_name = approved_users.pop(str(user_id_to_remove))
                    save_data(approved_users)
                    await event.respond(f"Пользователь {full_name} удален.")
                else:
                    await event.respond("Пользователь не найден среди подтвержденных.")
            except Exception as e:
                await event.respond(f"Ошибка: {str(e)}")
            admin_states.pop(user_id, None)
        elif state == 'awaiting_new_admin':
            new_admin_username = event.message.message
            if await update_admin(new_admin_username):
                await event.respond(f"Новый админ назначен: {new_admin_username}")
            else:
                await event.respond("Не удалось найти пользователя с таким именем.")
            admin_states.pop(user_id, None)

@client.on(events.CallbackQuery(pattern=b'poll_'))
async def poll_callback(event):
    global poll_active, orders, poll_end_time

    if not poll_active:
        await event.answer("Опрос завершен.")
        return

    if poll_end_time is None:
        await event.answer("Время окончания опроса не установлено.")
        return

    current_time = datetime.now().time()
    if current_time > poll_end_time:
        await end_poll()
        return

    user_id = event.sender_id
    selected_option = int(event.data.decode('utf-8').split('_')[1])

    if str(user_id) in orders:
        previous_option = orders[str(user_id)]
        if previous_option != selected_option:
            confirm_states[user_id] = selected_option
            await client.send_message(event.chat_id, "⚠️ Вы уже выбрали другой обед. Хотите изменить выбор?", buttons=[
                Button.inline("✅ Да", b'confirm_change_yes'),
                Button.inline("❌ Нет", b'confirm_change_no')
            ])
        else:
            await event.answer("Вы уже выбрали этот обед.")
    else:
        if str(selected_option) not in orders:
            orders[str(selected_option)] = []
        orders[str(selected_option)].append(user_id)
        orders[str(user_id)] = selected_option  # Save user's choice
        
        # Формируем сообщение с подтверждением выбора
        meal_name = menu_items.get(str(selected_option), 'Неизвестный обед')
        confirmation_message = f"✅ Вы выбрали Комплексный обед {selected_option}: {meal_name}"

        await client.send_message(user_id, confirmation_message)
        await event.answer(f"Вы выбрали Комплексный обед {selected_option}")


@client.on(events.CallbackQuery(data=b'confirm_change_yes'))
async def confirm_change_yes(event):
    user_id = event.sender_id
    if user_id in confirm_states:
        new_option = confirm_states.pop(user_id)
        for option, users in orders.items():
            if isinstance(users, list) and user_id in users:
                users.remove(user_id)
                break
        if str(new_option) not in orders:
            orders[str(new_option)] = []
        orders[str(new_option)].append(user_id)
        orders[str(user_id)] = new_option  # Update user's choice
        save_data(approved_users)
        await event.answer(f"Вы изменили выбор на Комплексный обед {new_option}")
    else:
        await event.answer("Не удалось изменить выбор.")

@client.on(events.CallbackQuery(data=b'confirm_change_no'))
async def confirm_change_no(event):
    user_id = event.sender_id
    if user_id in confirm_states:
        confirm_states.pop(user_id)
    await event.answer("Выбор остался прежним.")

@client.on(events.CallbackQuery(data=b'close_poll'))
async def close_poll(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    await end_poll()

@client.on(events.CallbackQuery(data=b'order_ready'))
async def order_ready(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    # Рассылаем сообщение о готовности обедов всем зарегистрированным пользователям
    for user_id in approved_users.keys():
        try:
            await client.send_message(int(user_id), "Обеды готовы! Можете забирать.")
        except ValueError:
            pass

    # Сохранение данных в CSV файл
    save_distribution_to_csv()

    await event.answer("Уведомление отправлено всем пользователям и CSV файл сохранен.")

def save_distribution_to_csv():
    date_today = datetime.now().strftime("%d.%m.%Y")
    file_path = f'order_distribution_{date_today}.csv'
    
    with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)
        
        for option in sorted(orders.keys(), key=lambda x: int(x)):
            if isinstance(orders[option], list):
                row = [menu_items.get(str(option), 'Неизвестный обед')]
                row.extend([approved_users.get(str(user_id), 'Неизвестный пользователь') for user_id in orders[option]])
                writer.writerow(row)
    
    print(f"CSV файл создан: {file_path}")
    return file_path

@client.on(events.CallbackQuery(data=b'list_users'))
async def list_users(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    user_list = "Список пользователей:\n\n"
    unique_users = {}
    for user_id, full_name in approved_users.items():
        if isinstance(full_name, list):
            full_name = full_name[0]
        unique_users[user_id] = full_name

    for user_id, full_name in unique_users.items():
        user_list += f"{full_name} (ID: {user_id})\n"

    await client.send_message(event.chat_id, user_list)
    await event.answer("Список пользователей отправлен.")

@client.on(events.CallbackQuery(data=b'add_menu_option'))
async def add_menu_option(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    await client.send_message(event.sender_id, "Введите название новой опции меню:")
    admin_states[event.sender_id] = 'awaiting_new_menu_option'

@client.on(events.CallbackQuery(data=b'remove_menu_option'))
async def remove_menu_option(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    await client.send_message(event.sender_id, "Введите название опции меню для удаления:")
    admin_states[event.sender_id] = 'awaiting_remove_menu_option'

@client.on(events.CallbackQuery(data=b'remove_user'))
async def remove_user(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    await client.send_message(event.sender_id, "Введите ID пользователя для удаления:")
    admin_states[event.sender_id] = 'awaiting_user_id_to_remove'

@client.on(events.CallbackQuery(data=b'clear_users'))
async def clear_users(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    approved_users.clear()
    save_data(approved_users)
    await client.send_message(event.chat_id, "Список всех пользователей очищен.")
    await event.answer("Список пользователей очищен.")

@client.on(events.CallbackQuery(data=b'restart'))
async def restart(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    await event.respond("Перезапуск бота...")
    await client.disconnect()
    sys.exit(0)

@client.on(events.CallbackQuery(data=b'assign_new_admin'))
async def assign_new_admin(event):
    if not is_admin(event.sender_id):
        await event.answer("У вас нет прав для выполнения этой команды.")
        return

    await client.send_message(event.sender_id, "Введите имя нового админа (например, @username):")
    admin_states[event.sender_id] = 'awaiting_new_admin'

async def main():
    global admin_id
    await client.start(bot_token=bot_token)
    admin_id = await get_user_id(admin_username)
    print(f"Admin ID: {admin_id}")
    await client.run_until_disconnected()

client.loop.run_until_complete(main())
