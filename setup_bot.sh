#!/bin/bash

set -e

usage() {
  echo "Usage: $0 [-s] [-d] [-n <service_name>] [-h]"
  echo "  -s                 Запустить с созданием systemd сервиса"
  echo "  -d                 Удалить скрипт после выполнения"
  echo "  -n <service_name>  Имя systemd сервиса (по умолчанию telegram-bot)"
  echo "  -h                 Помощь"
  exit 1
}

USE_SERVICE=0
DELETE_SCRIPT=0
SERVICE_NAME="telegram-bot"

# Получаем имя текущего пользователя
USERNAME=$(whoami)

# Парсим аргументы
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s)
      USE_SERVICE=1
      shift
      ;;
    -d)
      DELETE_SCRIPT=1
      shift
      ;;
    -n)
      shift
      if [[ -z "$1" ]]; then
        echo "Ошибка: после -n нужно указать имя сервиса"
        usage
      fi
      SERVICE_NAME="$1"
      shift
      ;;
    -h)
      usage
      ;;
    *)
      usage
      ;;
  esac
done

HOME_DIR="/home/$USERNAME"
VENV_DIR="$HOME_DIR/venv"
BOT_PATH="$HOME_DIR/bot.py"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Используется пользователь: $USERNAME"
echo "Имя сервиса: $SERVICE_NAME"

echo "=== Шаг 1: Проверка наличия bot.py в $BOT_PATH ==="
if [[ ! -f "$BOT_PATH" ]]; then
  echo "Ошибка: $BOT_PATH не найден. Поместите туда ваш bot.py"
  exit 1
fi

echo "=== Шаг 2: Создаём виртуальное окружение в $VENV_DIR ==="
python3 -m venv "$VENV_DIR"

echo "=== Шаг 3: Активируем виртуальное окружение и устанавливаем зависимости ==="
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install python-telegram-bot paramiko
deactivate

# Удаляем скрипт до запуска бота или сервиса
if [[ $DELETE_SCRIPT -eq 1 ]]; then
  echo "=== Удаляем скрипт setup_bot.sh ==="
  SCRIPT_PATH="$(realpath "$0")"
  rm -f "$SCRIPT_PATH"
  echo "Скрипт удалён."
fi

if [[ $USE_SERVICE -eq 1 ]]; then
  echo "=== Создаём systemd сервис ==="

  SERVICE_CONTENT="[Unit]
Description=Telegram Bot Service
After=network.target

[Service]
User =$USERNAME
WorkingDirectory=$HOME_DIR
ExecStart=$VENV_DIR/bin/python $BOT_PATH
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
"

  echo "$SERVICE_CONTENT" | sudo tee "$SERVICE_FILE" > /dev/null

  echo "=== Перезагружаем systemd и запускаем сервис ==="
  sudo systemctl daemon-reload
  sudo systemctl start "${SERVICE_NAME}.service"
  sudo systemctl enable "${SERVICE_NAME}.service"

  echo "=== Готово! Сервис $SERVICE_NAME запущен и включён в автозапуск ==="
else
  echo "=== Запуск бота из виртуального окружения (без создания сервиса) ==="
  source "$VENV_DIR/bin/activate"
  python "$BOT_PATH"
  deactivate
fi