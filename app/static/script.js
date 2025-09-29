document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('userModal');
    const modalUserId = document.getElementById('modalUserId');
    const saveUserIdBtn = document.getElementById('saveUserId');
    const changeUserIdBtn = document.getElementById('changeUserId');
    const currentUserIdSpan = document.getElementById('currentUserId');
    const form = document.getElementById('askForm');
    const hiddenUserId = document.getElementById('user_id');
    const submitButton = document.getElementById('submitButton');
    const responseSection = document.getElementById('responseSection');
    const responseContent = document.getElementById('responseContent');
    const queryExamples = document.querySelectorAll('.query-example');

    // Check if user ID is already saved
    function getSavedUserId() {
        return localStorage.getItem('rag_sql_user_id');
    }

    function setSavedUserId(userId) {
        localStorage.setItem('rag_sql_user_id', userId);
    }

    function updateUI() {
        const savedUserId = getSavedUserId();
        if (savedUserId) {
            currentUserIdSpan.textContent = savedUserId;
            hiddenUserId.value = savedUserId;
            submitButton.disabled = false;
            submitButton.textContent = 'Отправить запрос';
            modal.style.display = 'none';
        } else {
            currentUserIdSpan.textContent = 'не установлен';
            hiddenUserId.value = '';
            submitButton.disabled = true;
            submitButton.textContent = 'Отправить запрос (требуется User ID)';
            modal.style.display = 'block';
        }
    }

    // Show modal for changing user ID
    function showUserModal() {
        modal.style.display = 'block';
        modalUserId.value = getSavedUserId() || '';
        modalUserId.focus();
    }

    // Save user ID from modal
    saveUserIdBtn.addEventListener('click', function() {
        const userId = modalUserId.value.trim();
        if (!userId) {
            alert('Пожалуйста, введите User ID');
            return;
        }
        
        setSavedUserId(userId);
        updateUI();
        
        // Show success message
        const successMsg = document.createElement('div');
        successMsg.className = 'success';
        successMsg.textContent = `User ID ${userId} успешно сохранен! Теперь вы можете запрашивать свои задачи.`;
        document.querySelector('.test-form').insertBefore(successMsg, form);
        
        setTimeout(() => {
            successMsg.remove();
        }, 3000);
    });

    // Change user ID button
    changeUserIdBtn.addEventListener('click', showUserModal);

    // Allow Enter key in modal input
    modalUserId.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            saveUserIdBtn.click();
        }
    });

    // Query example buttons
    queryExamples.forEach(button => {
        button.addEventListener('click', function() {
            document.getElementById('question').value = this.getAttribute('data-query');
        });
    });

    // Form submission
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const savedUserId = getSavedUserId();
        if (!savedUserId) {
            alert('Пожалуйста, сначала установите User ID');
            showUserModal();
            return;
        }

        const originalText = submitButton.textContent;
        
        // Show loading state
        submitButton.disabled = true;
        submitButton.textContent = 'Отправка...';
        responseSection.style.display = 'none';
        responseContent.innerHTML = '<div class="loading">Loading...</div>';

        try {
            const formData = new FormData(form);
            const requestData = {
                question: formData.get('question'),
                identity: {
                    user_id: parseInt(savedUserId) // Используем сохраненный ID
                }
            };

            const response = await fetch('/ask', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Request failed');
            }

            displayResponse(data);
            responseSection.style.display = 'block';

        } catch (error) {
            responseContent.innerHTML = `
                <div class="error">
                    <strong>Error:</strong> ${error.message}
                </div>
            `;
            responseSection.style.display = 'block';
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = originalText;
        }
    });
    
    

    function displayResponse(data) {
        let html = '';

        // User statistics
        if (data.user_info) {
            html += `
                <div class="user-stats">
                    <h4>📊 Статистика пользователя #${data.user_info.user_id}</h4>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-value">${data.user_info.total_tasks}</div>
                            <div class="stat-label">Всего задач</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value">${data.user_info.filtered_tasks}</div>
                            <div class="stat-label">Найдено по запросу</div>
                        </div>
                    </div>
                </div>
            `;
        }

        // Main response info
        html += `
            <div class="response-block">
                <h4>📋 Информация о запросе</h4>
                <div class="data-field">
                    <span class="field-name">SQL запрос:</span>
                    <span class="field-value">${escapeHtml(data.sql)}</span>
                </div>
                <div class="data-field">
                    <span class="field-name">Объяснение:</span>
                    <span class="field-value">${escapeHtml(data.explanation)}</span>
                </div>
                <div class="data-field">
                    <span class="field-name">Требует уточнения:</span>
                    <span class="field-value">${data.needs_clarification ? 'Да' : 'Нет'}</span>
                </div>
                ${data.clarification_question ? `
                <div class="data-field">
                    <span class="field-name">Вопрос для уточнения:</span>
                    <span class="field-value">${escapeHtml(data.clarification_question)}</span>
                </div>
                ` : ''}
            </div>
        `;

        // Data rows
        if (data.rows && data.rows.length > 0) {
            html += `
                <div class="response-block">
                    <h4>📂 Результаты (${data.rows.length} задач)</h4>
            `;

            data.rows.forEach((row, index) => {
                html += `
                    <div class="data-block">
                        <h5>
                            🎯 Задача #${row.id}
                            ${row.status ? `<span class="status-badge status-${row.status}">${getStatusText(row.status)}</span>` : ''}
                        </h5>
                `;

                Object.entries(row).forEach(([key, value]) => {
                    let displayValue = value;
                    let valueClass = 'field-value';
                    let fieldName = getFieldName(key);
                    
                    if (key === 'priority') {
                        valueClass += ` priority-${value}`;
                        displayValue = getPriorityText(value);
                    } else if (key === 'status') {
                        displayValue = getStatusText(value);
                    } else if (key === 'created_at') {
                        displayValue = formatDate(value);
                    }
                    
                    if (value === null || value === undefined) {
                        displayValue = '<em>не указано</em>';
                    } else if (typeof value === 'object') {
                        displayValue = '<pre>' + escapeHtml(JSON.stringify(value, null, 2)) + '</pre>';
                    } else {
                        displayValue = escapeHtml(String(displayValue));
                    }

                    html += `
                        <div class="data-field">
                            <span class="field-name">${fieldName}:</span>
                            <span class="${valueClass}">${displayValue}</span>
                        </div>
                    `;
                });

                html += `</div>`;
            });

            html += `</div>`;
        } else {
            html += `
                <div class="response-block">
                    <h4>📂 Результаты</h4>
                    <p>По вашему запросу задач не найдено.</p>
                </div>
            `;
        }

        responseContent.innerHTML = html;
    }

    function getFieldName(key) {
        const fieldNames = {
            'id': 'ID',
            'title': 'Название',
            'description': 'Описание',
            'status': 'Статус',
            'priority': 'Приоритет',
            'created_at': 'Дата создания',
            'assigned_to': 'Исполнитель',
            'user_id': 'User ID'
        };
        return fieldNames[key] || key;
    }

    function getStatusText(status) {
        const statuses = {
            'pending': 'Ожидает',
            'in_progress': 'В процессе',
            'completed': 'Завершена'
        };
        return statuses[status] || status;
    }

    function getPriorityText(priority) {
        const priorities = {
            'low': 'Низкий',
            'medium': 'Средний',
            'high': 'Высокий'
        };
        return priorities[priority] || priority;
    }

    function formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleString('ru-RU');
    }

    function escapeHtml(unsafe) {
        if (unsafe === null || unsafe === undefined) return '';
        return unsafe
            .toString()
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
    
    // Обработчик для ссылки Health Check
    const healthLink = document.querySelector('a[href="/health"]');
    
    if (healthLink) {
        healthLink.addEventListener('click', async function(e) {
            e.preventDefault(); // Предотвращаем переход по ссылке
            
            try {
                const response = await fetch('/health');
                const data = await response.json();
                
                if (response.ok) {
                    showModal('✅ Статус системы', `Сервер работает нормально<br><strong>Статус:</strong> ${data.status}`);
                } else {
                    showModal('❌ Ошибка', `Проблема с сервером: ${data.detail || 'Неизвестная ошибка'}`);
                }
            } catch (error) {
                showModal('❌ Ошибка', `Не удалось подключиться к серверу: ${error.message}`);
            }
        });
    }

    // Функция для показа всплывающего окна
    function showModal(title, content) {
        // Создаем модальное окно если его нет
        let modal = document.getElementById('healthModal');
        
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'healthModal';
            modal.className = 'modal';
            modal.innerHTML = `
                <div class="modal-content">
                    <h3>${title}</h3>
                    <div class="modal-body">${content}</div>
                    <div class="modal-buttons">
                        <button class="btn btn-primary" id="healthModalOk">OK</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
            
            // Добавляем обработчик для кнопки OK
            document.getElementById('healthModalOk').addEventListener('click', function() {
                modal.style.display = 'none';
            });
            
            // Закрытие модального окна при клике вне его
            modal.addEventListener('click', function(e) {
                if (e.target === modal) {
                    modal.style.display = 'none';
                }
            });
        } else {
            // Обновляем содержимое существующего модального окна
            modal.querySelector('h3').textContent = title;
            modal.querySelector('.modal-body').innerHTML = content;
        }
        
        modal.style.display = 'block';
    }
    

    // Initialize the UI
    updateUI();
    
});