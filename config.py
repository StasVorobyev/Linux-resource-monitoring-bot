# Время сбора начальных данных для дневного отчета
start_time = "00:01"

# Время сбора конечных данных для дневного отчета
end_time = "23:59"

# Время отправки дневного отчета с разницей
report_time = "00:00"

# Список машин для мониторинга
MACHINES = [
    {
        "name": "Name of your machine (1.1.1.1)",
        "host": "1.1.1.1",
        "user": "login",
        "password": None,  # Если используете ключ, пароль можно оставить None
        "key_filename": "/home/youruser/.ssh/id_rsa"  # Путь к приватному ключу
    },
    {
        "name": "Name of your machine (2.2.2.2)",
        "host": "2.2.2.2",
        "user": "login",
        "password": None,  # Если используете ключ, пароль можно оставить None
        "key_filename": "/home/youruser/.ssh/id_rsa"  # Путь к приватному ключу, можно выставить None если используете логин и пароль
    },
]
