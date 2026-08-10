#!/bin/bash

# Скрипт безопасного обновления репозитория Nexus-OS
# Использование: ./scripts/deploy.sh "Сообщение коммита"

MESSAGE="${1:-Update: Hermes integration, Agents, and Security fixes}"

echo "🚀 Начало процесса деплоя..."

# Проверка наличия git
if ! command -v git &> /dev/null; then
    echo "❌ Git не установлен. Пожалуйста, установите git."
    exit 1
fi

# Проверка статуса git
echo "📊 Статус репозитория:"
git status

# Добавление всех изменений
echo "📦 Добавление изменений..."
git add .

# Коммит
echo "💾 Создание коммита: $MESSAGE"
git commit -m "$MESSAGE"

# Пуш
echo "⬆️ Отправка изменений в удаленный репозиторий..."
echo "💡 Убедитесь, что вы настроили git credentials или используете SSH."
git push origin main

if [ $? -eq 0 ]; then
    echo "✅ Успешно! Изменения отправлены в репозиторий."
else
    echo "❌ Ошибка при пуше. Проверьте свои учетные данные GitHub."
    echo "💡 Совет: Используйте Personal Access Token вместо пароля."
    echo "   git config --global credential.helper store"
    echo "   Затем выполните git push снова и введите токен при запросе пароля."
fi
