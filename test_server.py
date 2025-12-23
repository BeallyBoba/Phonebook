import pytest
import sqlite3
import os
import tempfile
import json
from server import app, init_db, validate_phone


@pytest.fixture
def client(monkeypatch):
    """Создает тестовый клиент Flask с временной базой данных"""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    app.config['TESTING'] = True
    
    def test_init_db():
        conn = sqlite3.connect(db_path)
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
        try:
            cursor.execute('ALTER TABLE contacts ADD COLUMN order_index INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass
        cursor.execute('UPDATE contacts SET order_index = id WHERE order_index = 0 OR order_index IS NULL')
        conn.commit()
        conn.close()
    
    original_connect = sqlite3.connect
    
    def test_connect(database, *args, **kwargs):
        if database == 'phonebook.db':
            return original_connect(db_path, *args, **kwargs)
        return original_connect(database, *args, **kwargs)
    
    import server
    monkeypatch.setattr(server.sqlite3, 'connect', test_connect)
    
    test_init_db()
    
    with app.test_client() as client:
        yield client
    
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def sample_contacts(client):
    """Создает тестовые контакты"""
    contacts = [
        {'name': 'Иван Иванов', 'phone': '+7 (999) 111-22-33', 'is_favorite': True},
        {'name': 'Петр Петров', 'phone': '+7 (999) 222-33-44', 'is_favorite': False},
        {'name': 'Мария Сидорова', 'phone': '+7 (999) 333-44-55', 'is_favorite': False},
        {'name': 'Анна Козлова', 'phone': '+7 (999) 444-55-66', 'is_favorite': True},
    ]
    
    created_ids = []
    for contact in contacts:
        response = client.post('/api/contacts', 
                              data=json.dumps(contact),
                              content_type='application/json')
        assert response.status_code == 201
        created_ids.append(response.get_json()['id'])
    
    return created_ids


class TestGetContacts:
    """Тесты для получения контактов"""
    
    def test_get_all_contacts_empty(self, client):
        """Тест получения пустого списка контактов"""
        response = client.get('/api/contacts')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == 0
    
    def test_get_all_contacts(self, client, sample_contacts):
        """Тест получения всех контактов"""
        response = client.get('/api/contacts')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 4
        assert data[0]['is_favorite'] == True
        assert data[1]['is_favorite'] == True
    
    def test_search_by_name_lowercase(self, client, sample_contacts):
        """Тест поиска по имени (строчные буквы)"""
        response = client.get('/api/contacts?search=иван')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert 'Иван' in data[0]['name']
    
    def test_search_by_name_uppercase(self, client, sample_contacts):
        """Тест поиска по имени (заглавные русские буквы)"""
        response = client.get('/api/contacts?search=ИВАН')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert 'Иван' in data[0]['name']
    
    def test_search_by_name_mixed_case(self, client, sample_contacts):
        """Тест поиска по имени (смешанный регистр)"""
        response = client.get('/api/contacts?search=МаРиЯ')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert 'Мария' in data[0]['name']
    
    def test_search_by_phone_digits(self, client, sample_contacts):
        """Тест поиска по телефону (только цифры)"""
        response = client.get('/api/contacts?search=11122')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert '111-22-33' in data[0]['phone']
    
    def test_search_by_phone_full(self, client, sample_contacts):
        """Тест поиска по телефону (полный формат)"""
        response = client.get('/api/contacts?search=+7 (999) 222-33-44')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert '222-33-44' in data[0]['phone']
    
    def test_search_no_results(self, client, sample_contacts):
        """Тест поиска без результатов"""
        response = client.get('/api/contacts?search=Несуществующий')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 0


class TestAddContact:
    """Тесты для добавления контакта"""
    
    def test_add_contact_success(self, client):
        """Тест успешного добавления контакта"""
        contact_data = {
            'name': 'Тестовый Контакт',
            'phone': '+7 (999) 123-45-67',
            'is_favorite': False
        }
        response = client.post('/api/contacts',
                              data=json.dumps(contact_data),
                              content_type='application/json')
        assert response.status_code == 201
        data = response.get_json()
        assert data['name'] == 'Тестовый Контакт'
        assert data['phone'] == '+7 (999) 123-45-67'
        assert data['is_favorite'] == False
        assert 'id' in data
        assert 'order_index' in data
    
    def test_add_contact_with_favorite(self, client):
        """Тест добавления контакта в избранное"""
        contact_data = {
            'name': 'Избранный Контакт',
            'phone': '+7 (999) 987-65-43',
            'is_favorite': True
        }
        response = client.post('/api/contacts',
                              data=json.dumps(contact_data),
                              content_type='application/json')
        assert response.status_code == 201
        data = response.get_json()
        assert data['is_favorite'] == True
    
    def test_add_contact_missing_name(self, client):
        """Тест добавления контакта без имени"""
        contact_data = {
            'phone': '+7 (999) 123-45-67'
        }
        response = client.post('/api/contacts',
                              data=json.dumps(contact_data),
                              content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
    
    def test_add_contact_missing_phone(self, client):
        """Тест добавления контакта без телефона"""
        contact_data = {
            'name': 'Тестовый Контакт'
        }
        response = client.post('/api/contacts',
                              data=json.dumps(contact_data),
                              content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
    
    def test_add_contact_empty_name(self, client):
        """Тест добавления контакта с пустым именем"""
        contact_data = {
            'name': '   ',
            'phone': '+7 (999) 123-45-67'
        }
        response = client.post('/api/contacts',
                              data=json.dumps(contact_data),
                              content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
    
    def test_add_contact_invalid_phone_format(self, client):
        """Тест добавления контакта с неверным форматом телефона"""
        contact_data = {
            'name': 'Тестовый Контакт',
            'phone': '1234567890'  
        }
        response = client.post('/api/contacts',
                              data=json.dumps(contact_data),
                              content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'формат' in data['error'].lower() or 'формат' in data['error']
    
    def test_add_contact_empty_json(self, client):
        """Тест добавления контакта с пустым JSON"""
        response = client.post('/api/contacts',
                              data=json.dumps({}),
                              content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data


class TestDeleteContact:
    """Тесты для удаления контакта"""
    
    def test_delete_contact_success(self, client, sample_contacts):
        """Тест успешного удаления контакта"""
        contact_id = sample_contacts[0]
        response = client.delete(f'/api/contacts/{contact_id}')
        assert response.status_code == 200
        data = response.get_json()
        assert 'message' in data
        
        get_response = client.get('/api/contacts')
        contacts = get_response.get_json()
        assert len(contacts) == 3
        assert not any(c['id'] == contact_id for c in contacts)
    
    def test_delete_nonexistent_contact(self, client):
        """Тест удаления несуществующего контакта"""
        response = client.delete('/api/contacts/99999')
        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data


class TestToggleFavorite:
    """Тесты для переключения статуса избранного"""
    
    def test_toggle_favorite_to_true(self, client, sample_contacts):
        """Тест переключения статуса на избранное"""
        # Находим контакт, который не в избранном
        response = client.get('/api/contacts')
        contacts = response.get_json()
        regular_contact = next(c for c in contacts if not c['is_favorite'])
        
        response = client.put(f'/api/contacts/{regular_contact["id"]}/favorite')
        assert response.status_code == 200
        data = response.get_json()
        assert data['is_favorite'] == True
    
    def test_toggle_favorite_to_false(self, client, sample_contacts):
        """Тест переключения статуса с избранного"""
        response = client.get('/api/contacts')
        contacts = response.get_json()
        favorite_contact = next(c for c in contacts if c['is_favorite'])
        
        response = client.put(f'/api/contacts/{favorite_contact["id"]}/favorite')
        assert response.status_code == 200
        data = response.get_json()
        assert data['is_favorite'] == False
    
    def test_toggle_favorite_nonexistent(self, client):
        """Тест переключения статуса для несуществующего контакта"""
        response = client.put('/api/contacts/99999/favorite')
        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data


class TestUpdateOrder:
    """Тесты для обновления порядка контактов"""
    
    def test_update_order_success(self, client, sample_contacts):
        """Тест успешного обновления порядка"""
        response = client.get('/api/contacts')
        contacts = response.get_json()
        original_order = [c['id'] for c in contacts]
        original_order_indices = {c['id']: c['order_index'] for c in contacts}
        
        assert len(original_order) >= 2, "Нужно минимум 2 контакта для теста изменения порядка"
        
        original_favorites = [c['id'] for c in contacts if c['is_favorite']]
        original_regular = [c['id'] for c in contacts if not c['is_favorite']]
        
        new_favorites = list(reversed(original_favorites)) if len(original_favorites) > 1 else original_favorites
        new_regular = list(reversed(original_regular)) if len(original_regular) > 1 else original_regular
        
        new_order = new_favorites + new_regular
        
        if len(original_favorites) > 1 or len(original_regular) > 1:
            assert new_order != original_order, "Порядок должен отличаться от исходного"
        
        response = client.put('/api/contacts/order',
                             data=json.dumps({'contact_ids': new_order}),
                             content_type='application/json')
        assert response.status_code == 200
        data = response.get_json()
        assert 'message' in data
        
        response = client.get('/api/contacts')
        contacts = response.get_json()
        new_order_check = [c['id'] for c in contacts]
        
        if len(original_favorites) > 1 or len(original_regular) > 1:
            assert new_order_check != original_order, \
                f"Порядок должен был измениться. Исходный: {original_order}, Текущий: {new_order_check}"
        
        new_order_indices = {c['id']: c['order_index'] for c in contacts}
        
        indices_changed = any(
            original_order_indices[cid] != new_order_indices[cid] 
            for cid in original_order_indices.keys()
        )
        assert indices_changed, "Хотя бы один order_index должен был измениться"
        
        favorites_in_result = [c['id'] for c in contacts if c['is_favorite']]
        assert favorites_in_result == new_favorites, \
            f"Порядок избранных контактов не соответствует. Ожидалось: {new_favorites}, Получено: {favorites_in_result}"
        
        regular_in_result = [c['id'] for c in contacts if not c['is_favorite']]
        assert regular_in_result == new_regular, \
            f"Порядок обычных контактов не соответствует. Ожидалось: {new_regular}, Получено: {regular_in_result}"
    
    def test_update_order_missing_contact_ids(self, client):
        """Тест обновления порядка без contact_ids"""
        response = client.put('/api/contacts/order',
                             data=json.dumps({}),
                             content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
    
    def test_update_order_not_array(self, client):
        """Тест обновления порядка с не массивом"""
        response = client.put('/api/contacts/order',
                             data=json.dumps({'contact_ids': 'not an array'}),
                             content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data


class TestValidatePhone:
    """Тесты для функции валидации телефона"""
    
    def test_validate_phone_correct(self):
        """Тест валидации правильного формата телефона"""
        assert validate_phone('+7 (999) 123-45-67') == True
    
    def test_validate_phone_incorrect_format(self):
        """Тест валидации неправильного формата"""
        assert validate_phone('1234567890') == False
        assert validate_phone('+79991234567') == False
        assert validate_phone('7 (999) 123-45-67') == False
        assert validate_phone('+7 (999) 1234567') == False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

