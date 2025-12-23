from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flasgger import Swagger
import sqlite3
import re
import os

# Создаем папку static если её нет
if not os.path.exists('static'):
    os.makedirs('static')

app = Flask(__name__, static_folder='static')
CORS(app)

# Настройка Swagger
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/api-docs"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "PhoneBook API",
        "description": "API для управления телефонной книгой",
        "version": "1.0.0"
    },
    "basePath": "/",
    "schemes": ["http", "https"]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('phonebook.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            is_favorite BOOLEAN DEFAULT 0,
            order_index INTEGER DEFAULT 0
        )
    ''')
    # Добавляем колонку order_index если её нет (миграция для существующих БД)
    try:
        cursor.execute('ALTER TABLE contacts ADD COLUMN order_index INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
    
    # Обновляем order_index для существующих записей, если они равны 0
    cursor.execute('UPDATE contacts SET order_index = id WHERE order_index = 0 OR order_index IS NULL')
    
    conn.commit()
    conn.close()

# Валидация телефона
def validate_phone(phone):
    pattern = r'^\+7 \(\d{3}\) \d{3}-\d{2}-\d{2}$'
    return re.match(pattern, phone) is not None

# Главная страница
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# API: Получение контактов
@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    """
    Получение списка контактов
    ---
    tags:
      - Контакты
    parameters:
      - name: search
        in: query
        type: string
        required: false
        description: Поисковый запрос (по имени или телефону)
    responses:
      200:
        description: Список контактов
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID контакта
              name:
                type: string
                description: Имя контакта
              phone:
                type: string
                description: Номер телефона
              is_favorite:
                type: boolean
                description: Статус избранного
              order_index:
                type: integer
                description: Порядок сортировки
    """
    search = request.args.get('search', '').strip()
    conn = sqlite3.connect('phonebook.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Загружаем все контакты
    cursor.execute('''
        SELECT * FROM contacts
        ORDER BY is_favorite DESC, order_index ASC, name ASC
    ''')
    
    rows = cursor.fetchall()
    contacts = [dict(zip(row.keys(), row)) for row in rows]
    
    # Фильтруем контакты в Python для корректной работы с русскими буквами
    if search:
        search_lower = search.lower()
        # Извлекаем только цифры из поискового запроса для поиска по телефону
        search_digits = ''.join(filter(str.isdigit, search))
        
        def matches_contact(contact):
            # Поиск по имени (без учета регистра) - корректно работает с русскими буквами
            name_match = search_lower in contact['name'].lower()
            # Поиск по телефону (по цифрам)
            phone_digits = ''.join(filter(str.isdigit, contact['phone']))
            phone_match = search_digits in phone_digits if search_digits else False
            return name_match or phone_match
        
        contacts = [c for c in contacts if matches_contact(c)]
    conn.close()
    return jsonify(contacts)

# API: Добавление контакта
@app.route('/api/contacts', methods=['POST'])
def add_contact():
    """
    Добавление нового контакта
    ---
    tags:
      - Контакты
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
            - phone
          properties:
            name:
              type: string
              description: Имя контакта
              example: "Иван Иванов"
            phone:
              type: string
              description: Номер телефона в формате +7 (999) 999-99-99
              example: "+7 (999) 123-45-67"
            is_favorite:
              type: boolean
              description: Добавить в избранное
              default: false
    responses:
      201:
        description: Контакт успешно создан
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            phone:
              type: string
            is_favorite:
              type: boolean
            order_index:
              type: integer
      400:
        description: Ошибка валидации данных
        schema:
          type: object
          properties:
            error:
              type: string
      500:
        description: Внутренняя ошибка сервера
        schema:
          type: object
          properties:
            error:
              type: string
    """
    data = request.get_json()
    if not data or 'name' not in data or 'phone' not in data:
        return jsonify({'error': 'Требуются поля: name и phone'}), 400
    name = data['name'].strip()
    phone = data['phone'].strip()
    is_favorite = bool(data.get('is_favorite', False))
    if not name:
        return jsonify({'error': 'Имя не может быть пустым'}), 400
    if not validate_phone(phone):
        return jsonify({'error': 'Неверный формат телефона. Используйте: +7 (999) 999-99-99'}), 400
    conn = sqlite3.connect('phonebook.db')
    conn.row_factory = sqlite3.Row  # Устанавливаем row_factory
    cursor = conn.cursor()
    try:
        # Получаем максимальный order_index и добавляем 1 для нового контакта
        cursor.execute('SELECT COALESCE(MAX(order_index), 0) FROM contacts')
        max_order = cursor.fetchone()[0]
        new_order = max_order + 1
        
        cursor.execute('''
            INSERT INTO contacts (name, phone, is_favorite, order_index)
            VALUES (?, ?, ?, ?)
        ''', (name, phone, is_favorite, new_order))
        conn.commit()
        new_id = cursor.lastrowid
        # Проверяем, что lastrowid вернул корректный ID
        if new_id is not None and new_id > 0:
            # Получаем только что вставленную строку
            cursor.execute('SELECT * FROM contacts WHERE id = ?', (new_id,))
            row = cursor.fetchone()
            # Проверяем, что строка действительно была возвращена
            if row is not None:
                new_contact = dict(zip(row.keys(), row))  # Исправленное преобразование
                conn.close() # Закрываем соединение до return
                return jsonify(new_contact), 201
            else:
                # Если строка не найдена, возвращаем ошибку
                conn.close()
                return jsonify({'error': 'Не удалось получить данные нового контакта после вставки'}), 500
        else:
            # Если lastrowid не дал результата
            conn.close()
            return jsonify({'error': 'Не удалось получить ID нового контакта'}), 500
    except sqlite3.Error as e:
        conn.rollback() # Откатываем транзакцию в случае ошибки
        conn.close()
        return jsonify({'error': f'Ошибка базы данных: {str(e)}'}), 500
    except Exception as e:
        conn.close()
        return jsonify({'error': f'Внутренняя ошибка сервера: {str(e)}'}), 500

# API: Удаление контакта
@app.route('/api/contacts/<int:contact_id>', methods=['DELETE'])
def delete_contact(contact_id):
    """
    Удаление контакта
    ---
    tags:
      - Контакты
    parameters:
      - name: contact_id
        in: path
        type: integer
        required: true
        description: ID контакта для удаления
    responses:
      200:
        description: Контакт успешно удалён
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Контакт удалён"
      404:
        description: Контакт не найден
        schema:
          type: object
          properties:
            error:
              type: string
      500:
        description: Внутренняя ошибка сервера
        schema:
          type: object
          properties:
            error:
              type: string
    """
    conn = sqlite3.connect('phonebook.db')
    cursor = conn.cursor()
    try:
        # Проверяем, существует ли контакт
        cursor.execute('SELECT 1 FROM contacts WHERE id = ?', (contact_id,))
        exists = cursor.fetchone()
        if not exists:
            conn.close()
            return jsonify({'error': 'Контакт не найден'}), 404
        # Удаляем контакт
        cursor.execute('DELETE FROM contacts WHERE id = ?', (contact_id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Контакт удалён'}), 200
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Ошибка базы данных: {str(e)}'}), 500
    except Exception as e:
        conn.close()
        return jsonify({'error': f'Внутренняя ошибка сервера: {str(e)}'}), 500

# API: Изменение статуса избранного
@app.route('/api/contacts/<int:contact_id>/favorite', methods=['PUT'])
def toggle_favorite(contact_id):
    """
    Переключение статуса избранного контакта
    ---
    tags:
      - Контакты
    parameters:
      - name: contact_id
        in: path
        type: integer
        required: true
        description: ID контакта
    responses:
      200:
        description: Статус избранного успешно изменён
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            phone:
              type: string
            is_favorite:
              type: boolean
            order_index:
              type: integer
      404:
        description: Контакт не найден
        schema:
          type: object
          properties:
            error:
              type: string
      500:
        description: Внутренняя ошибка сервера
        schema:
          type: object
          properties:
            error:
              type: string
    """
    conn = sqlite3.connect('phonebook.db')
    conn.row_factory = sqlite3.Row  # Устанавливаем row_factory
    cursor = conn.cursor()
    try:
        # Проверяем, существует ли контакт
        cursor.execute('SELECT is_favorite FROM contacts WHERE id = ?', (contact_id,))
        row = cursor.fetchone()
        if row is None:
            conn.close()
            return jsonify({'error': 'Контакт не найден'}), 404
        # Переключаем статус
        new_value = 0 if row[0] else 1
        cursor.execute('UPDATE contacts SET is_favorite = ? WHERE id = ?', (new_value, contact_id))
        conn.commit()
        # Получаем обновленные данные по тому же ID
        cursor.execute('SELECT * FROM contacts WHERE id = ?', (contact_id,))
        updated_row = cursor.fetchone()
        # Проверяем, что строка действительно была возвращена после UPDATE
        if updated_row is not None:
            updated_contact = dict(zip(updated_row.keys(), updated_row))  # Исправленное преобразование
            conn.close() # Закрываем соединение до return
            return jsonify(updated_contact), 200
        else:
            # Если строка не найдена после UPDATE, возвращаем ошибку
            conn.close()
            return jsonify({'error': 'Не удалось получить данные обновленного контакта'}), 500
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Ошибка базы данных: {str(e)}'}), 500
    except Exception as e:
        conn.close()
        return jsonify({'error': f'Внутренняя ошибка сервера: {str(e)}'}), 500

# API: Обновление порядка контактов
@app.route('/api/contacts/order', methods=['PUT'])
def update_contacts_order():
    """
    Обновление порядка контактов
    ---
    tags:
      - Контакты
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - contact_ids
          properties:
            contact_ids:
              type: array
              items:
                type: integer
              description: Массив ID контактов в нужном порядке
              example: [1, 3, 2, 4]
    responses:
      200:
        description: Порядок контактов успешно обновлён
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Порядок контактов обновлён"
      400:
        description: Ошибка валидации данных
        schema:
          type: object
          properties:
            error:
              type: string
      500:
        description: Внутренняя ошибка сервера
        schema:
          type: object
          properties:
            error:
              type: string
    """
    data = request.get_json()
    if not data or 'contact_ids' not in data:
        return jsonify({'error': 'Требуется массив contact_ids'}), 400
    
    contact_ids = data['contact_ids']
    if not isinstance(contact_ids, list):
        return jsonify({'error': 'contact_ids должен быть массивом'}), 400
    
    conn = sqlite3.connect('phonebook.db')
    cursor = conn.cursor()
    try:
        # Обновляем order_index для каждого контакта
        for index, contact_id in enumerate(contact_ids):
            cursor.execute('UPDATE contacts SET order_index = ? WHERE id = ?', (index, contact_id))
        
        conn.commit()
        conn.close()
        return jsonify({'message': 'Порядок контактов обновлён'}), 200
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Ошибка базы данных: {str(e)}'}), 500
    except Exception as e:
        conn.close()
        return jsonify({'error': f'Внутренняя ошибка сервера: {str(e)}'}), 500

if __name__ == '__main__':
    init_db()
    print("✅ Сервер запущен на http://localhost:5000")
    print("📁 Статические файлы: /static/")
    print("🔌 API доступно по /api/contacts")
    print("📚 Swagger документация: http://localhost:5000/api-docs")
    app.run(host='127.0.0.1', port=5000, debug=True)