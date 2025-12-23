document.addEventListener('DOMContentLoaded', () => {
  const contactList = document.getElementById('contact-list');
  const searchInput = document.getElementById('search');
  const modal = document.getElementById('modal');
  const addContactBtn = document.getElementById('add-contact-btn');
  const closeModalBtn = document.getElementById('close-modal');
  const addContactForm = document.getElementById('add-contact-form');
  const phoneInput = document.getElementById('phone');
  // Базовый URL API
  const API_URL = '/api/contacts';
  // Флаг для предотвращения множественных запросов при загрузке
  let isLoading = false;
  // Переменная для отслеживания перетаскиваемого элемента
  let draggedItem = null;

  // Инициализация приложения
  function init() {
    // Загружаем контакты при загрузке страницы
    loadContacts();
    // Привязываем обработчики событий
    setupEventListeners();
    // Настраиваем улучшенный ввод телефона
    setupPhoneInput();
  }

  function setupEventListeners() {
    addContactBtn.addEventListener('click', openModal);
    closeModalBtn.addEventListener('click', closeModal);
    addContactForm.addEventListener('submit', handleAddContact);
    searchInput.addEventListener('input', handleSearch);
    
    // События для drag-and-drop
    contactList.addEventListener('dragstart', handleDragStart);
    contactList.addEventListener('dragover', handleDragOver);
    contactList.addEventListener('drop', handleDrop);
    contactList.addEventListener('dragend', handleDragEnd);
    
    // Закрытие модального окна при клике вне его содержимого
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
    // Закрытие модального окна при нажатии Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeModal();
    });
  }

  function setupPhoneInput() {
    phoneInput.addEventListener('keydown', handlePhoneKeyDown);
    phoneInput.addEventListener('input', formatPhoneInput);
    phoneInput.addEventListener('focus', positionCursorOnFocus);
  }

  function handlePhoneKeyDown(e) {
    const cursorPos = phoneInput.selectionStart;
    const value = phoneInput.value;
    
    // Обработка Backspace
    if (e.key === 'Backspace' && cursorPos > 0) {
      // Если курсор находится перед разделителем, перемещаем его назад
      if (/[()\- ]/.test(value[cursorPos - 1])) {
        e.preventDefault();
        const newPosition = findPreviousDigitPosition(cursorPos - 1, value);
        phoneInput.setSelectionRange(newPosition, newPosition);
      }
    }
    
    // Обработка Delete
    if (e.key === 'Delete') {
      const cursorPos = phoneInput.selectionStart;
      const value = phoneInput.value;
      
      if (cursorPos < value.length && /[()\- ]/.test(value[cursorPos])) {
        e.preventDefault();
        const newPosition = findNextDigitPosition(cursorPos + 1, value);
        phoneInput.setSelectionRange(cursorPos, newPosition);
      }
    }
  }

  function findPreviousDigitPosition(pos, value) {
    while (pos > 0 && /[()\- ]/.test(value[pos - 1])) {
      pos--;
    }
    return pos;
  }

  function findNextDigitPosition(pos, value) {
    while (pos < value.length && /[()\- ]/.test(value[pos])) {
      pos++;
    }
    return pos;
  }

  function formatPhoneInput() {
    let value = phoneInput.value.replace(/\D/g, '');
    
    // Убираем первую 7, если она есть (оставляем только цифры после +7)
    if (value.startsWith('7') && value.length > 1) {
      value = value.slice(1);
    }
    
    // Максимум 10 цифр после +7
    value = value.slice(0, 10);
    
    // Форматируем телефон
    let formatted = '+7';
    if (value.length > 0) {
      formatted += ` (${value.slice(0, 3)}`;
      if (value.length > 3) {
        formatted += `) ${value.slice(3, 6)}`;
        if (value.length > 6) {
          formatted += `-${value.slice(6, 8)}`;
          if (value.length > 8) {
            formatted += `-${value.slice(8, 10)}`;
          }
        }
      }
    }
    
    phoneInput.value = formatted;
    
    // Восстанавливаем позицию курсора
    setTimeout(() => {
      let newCursorPos = phoneInput.selectionStart;
      // Корректировка позиции курсора, чтобы он не оказался на разделителе
      while (newCursorPos > 0 && /[()\- ]/.test(phoneInput.value[newCursorPos - 1])) {
        newCursorPos--;
      }
      phoneInput.setSelectionRange(newCursorPos, newCursorPos);
    }, 0);
  }

  function positionCursorOnFocus() {
    const value = phoneInput.value;
    if (value === '+7') {
      phoneInput.setSelectionRange(2, 2);
    }
  }

  function openModal() {
    modal.classList.remove('hidden');
    document.getElementById('name').focus();
  }

  function closeModal() {
    modal.classList.add('hidden');
    addContactForm.reset();
  }

  // Функция для выполнения API запросов
  const apiRequest = async (url, options = {}) => {
    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
          'X-Requested-With': 'XMLHttpRequest'
        }
      });
      if (!response.ok) {
        // Пытаемся распарсить ошибку как JSON
        let errorData;
        try {
          errorData = await response.json();
        } catch (jsonError) {
          // Если не удалось распарсить JSON, используем текст ответа
          errorData = { error: await response.text() };
        }
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
      }
      // Если ответ пустой, возвращаем null
      const text = await response.text();
      return text ? JSON.parse(text) : null;
    } catch (error) {
      console.error('API Error:', error);
      // Не показываем alert при загрузке контактов при старте, чтобы не раздражать пользователя
      if (url !== API_URL || options.method !== 'GET') {
        alert(`Ошибка: ${error.message}`);
      }
      throw error;
    }
  };

  // Загрузка контактов
  const loadContacts = async (searchQuery = '') => {
    if (isLoading) return;
    isLoading = true;
    try {
      contactList.innerHTML = '<li class="contact-item loading">Загрузка контактов...</li>';
      let url = API_URL;
      if (searchQuery) {
        url += `?search=${encodeURIComponent(searchQuery)}`;
      }
      const contacts = await apiRequest(url);
      
      // Проверяем, что получили массив
      if (!Array.isArray(contacts)) {
        throw new Error('Некорректный формат ответа от сервера');
      }
      
      renderContacts(contacts);
    } catch (error) {
      console.error('Error loading contacts:', error);
      contactList.innerHTML = `<li class="contact-item error">Ошибка загрузки контактов: ${error.message || 'Неизвестная ошибка'}</li>`;
    } finally {
      isLoading = false;
    }
  };

  // Добавление контакта
  async function handleAddContact(e) {
    e.preventDefault();
    const name = document.getElementById('name').value.trim();
    const phone = phoneInput.value.trim();
    const isFavorite = document.getElementById('favorite').checked;

    // Валидация данных
    if (!name) {
      alert('Имя не должно быть пустым');
      return;
    }
    if (!phone.match(/^\+7 \(\d{3}\) \d{3}-\d{2}-\d{2}$/)) {
      alert('Телефон должен быть в формате +7 (999) 999-99-99');
      return;
    }

    try {
      await apiRequest(API_URL, {
        method: 'POST',
        body: JSON.stringify({ name, phone, is_favorite: isFavorite })
      });
      closeModal();
      loadContacts();
    } catch (error) {
      console.error('Error adding contact:', error);
    }
  }

  // Отображение контактов
  function renderContacts(contacts) {
    contactList.innerHTML = '';
    
    // Проверяем, что contacts является массивом
    if (!Array.isArray(contacts) || contacts.length === 0) {
      contactList.innerHTML = '<li class="contact-item empty">Контакты не найдены</li>';
      return;
    }
    
    // Разделяем контакты на избранные и обычные
    const favorites = contacts.filter(c => c.is_favorite);
    const regular = contacts.filter(c => !c.is_favorite);
    
    // Отрисовываем сначала избранные, затем обычные
    [...favorites, ...regular].forEach(contact => {
      const li = document.createElement('li');
      li.className = 'contact-item';
      li.draggable = true; // Добавляем возможность перетаскивания
      
      if (contact.is_favorite) {
        li.classList.add('favorite');
      }
      
      li.setAttribute('data-id', contact.id); // Добавляем data-id для идентификации контакта
      li.innerHTML = `
        <span>${contact.name} (${contact.phone})</span>
        <div class="actions">
          <button class="favorite-btn" title="${contact.is_favorite ? 'Убрать из избранного' : 'Добавить в избранное'}">
            ${contact.is_favorite ? '❤️' : '♡'}
          </button>
          <button class="delete-btn" title="Удалить контакт">Удалить</button>
        </div>
      `;
      
      li.querySelector('.delete-btn').addEventListener('click', async () => {
        if (confirm(`Вы уверены, что хотите удалить контакт ${contact.name}?`)) {
          try {
            await apiRequest(`${API_URL}/${contact.id}`, { method: 'DELETE' });
            loadContacts();
          } catch (error) {
            console.error(`Error deleting contact ${contact.id}:`, error);
          }
        }
      });
      
      li.querySelector('.favorite-btn').addEventListener('click', async () => {
        try {
          await apiRequest(`${API_URL}/${contact.id}/favorite`, { method: 'PUT' });
          loadContacts();
        } catch (error) {
          console.error(`Error toggling favorite for contact ${contact.id}:`, error);
        }
      });
      
      contactList.appendChild(li);
    });
  }

  // Поиск контактов
  function handleSearch(e) {
    const query = e.target.value.trim();
    loadContacts(query);
  }
  
  // Обработчики для drag-and-drop
  function handleDragStart(e) {
    if (e.target.classList.contains('contact-item')) {
      draggedItem = e.target;
      setTimeout(() => {
        e.target.classList.add('dragging');
      }, 0);
    }
  }
  
  function handleDragOver(e) {
    e.preventDefault();
    const draggingItem = draggedItem;
    const targetItem = e.target.closest('.contact-item');
    
    if (!targetItem || !draggingItem || targetItem === draggingItem || 
        targetItem.classList.contains('favorite') !== draggingItem.classList.contains('favorite')) {
      return;
    }
    
    const rect = targetItem.getBoundingClientRect();
    const mouseY = e.clientY;
    const isAbove = mouseY < rect.top + rect.height / 2;
    
    contactList.insertBefore(
      draggingItem, 
      isAbove ? targetItem : targetItem.nextElementSibling
    );
  }
  
  function handleDrop(e) {
    e.preventDefault();
    if (draggedItem) {
      draggedItem.classList.remove('dragging');
      saveContactsOrder();
      draggedItem = null;
    }
  }
  
  // Функция для сохранения порядка контактов на сервере
  async function saveContactsOrder() {
    const contactItems = Array.from(contactList.querySelectorAll('.contact-item'));
    const contactIds = contactItems.map(item => parseInt(item.getAttribute('data-id')));
    
    if (contactIds.length === 0) return;
    
    try {
      await apiRequest(`${API_URL}/order`, {
        method: 'PUT',
        body: JSON.stringify({ contact_ids: contactIds })
      });
    } catch (error) {
      console.error('Error saving contacts order:', error);
      // Перезагружаем контакты в случае ошибки, чтобы восстановить правильный порядок
      loadContacts();
    }
  }
  
  function handleDragEnd() {
    if (draggedItem) {
      draggedItem.classList.remove('dragging');
      draggedItem = null;
    }
  }

  // Инициализируем приложение
  init();
});