from creds import token, chat
from config import start_time, end_time, report_time, MACHINES
import paramiko
import asyncio
from telegram import Bot
from datetime import datetime, timedelta
import json
import os

TOKEN = token  # Токен вашего телеграм бота
CHAT_ID = chat  # ID вашего чата или группы. В формате "-12345678..."
bot = Bot(token=TOKEN)

DATA_FILE = "data.json"
CONFIG_FILE = "config.json"


def get_smiley(value, max_value):
    """Возвращает строку смайлов в зависимости от значения."""
    if value < 0:
        return "❌"  # Ошибка
    if max_value <= 0:
        return "⚠️"  # Предупреждение, если максимальное значение 0 или меньше

    percentage = (value / max_value) * 100
    if percentage < 10:
        return "🟩"
    elif percentage < 20:
        return "🟩🟩"
    elif percentage < 30:
        return "🟩🟩🟩"
    elif percentage < 40:
        return "🟩🟩🟩🟩"
    elif percentage < 50:
        return "🟨🟨🟨🟨🟨"
    elif percentage < 60:
        return "🟨🟨🟨🟨🟨🟨"
    elif percentage < 70:
        return "🟨🟨🟨🟨🟨🟨🟨"
    elif percentage < 80:
        return "🟥🟥🟥🟥🟥🟥🟥🟥"
    elif percentage < 90:
        return "🟥🟥🟥🟥🟥🟥🟥🟥🟥"
    else:
        return "🟥🟥🟥🟥🟥🟥🟥🟥🟥🟥"


def save_data(time_key, metrics_dict):
    data = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    data[time_key] = metrics_dict
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


async def get_remote_metrics(host, user, password=None, key_filename=None):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password, key_filename=key_filename)

    stdin, stdout, stderr = ssh.exec_command(
        "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'"
    )
    cpu = float(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command(
        "free | grep Mem | awk '{print $3/$2 * 100}'"
    )
    ram = float(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command(
        "free | grep Swap | awk '{print $3/$2 * 100}'"
    )
    swap = float(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command(
        "df | grep /dev/mapper/ubuntu--vg-ubuntu--lv | awk '{print ($2/1024)/1024}'"
    )
    disk_max = float(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command(
        "df | grep /dev/mapper/ubuntu--vg-ubuntu--lv | awk '{print ($3/1024)/1024}'"
    )
    disk_used = float(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command(
        "sudo sysctl net.ipv4.tcp_mem | awk '{print $5}'"
    )
    tcp_mem_max = int(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command(
        "cat /proc/net/sockstat | grep TCP | awk '{print $11}'"
    )
    tcp_mem_used = int(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command("ss -4 | wc -l")
    cc = int(stdout.read().decode().strip())

    ssh.close()

    tcp_mem_free_pct = (tcp_mem_used / tcp_mem_max) * 100 if tcp_mem_max > 0 else 0
    disk_used_pct = (disk_used / disk_max) * 100 if disk_max > 0 else 0

    return {
        "cpu": cpu,
        "ram": ram,
        "swap": swap,
        "disk": f"{disk_used:.2f}GB ({disk_used_pct:.1f}%)",
        "tcp_mem": f"{tcp_mem_used}/{tcp_mem_max} ({tcp_mem_free_pct:.1f}% used)",
        "cpu_smiley": get_smiley(cpu, 100),
        "ram_smiley": get_smiley(ram, 100),
        "swap_smiley": get_smiley(swap, 100),
        "disk_smiley": get_smiley(disk_used_pct, 100),
        "tcp_mem_smiley": get_smiley(tcp_mem_free_pct, 100),
        "cc": cc,
    }


async def generate_report():
    report = f"📊 Системный отчет ({datetime.now().strftime('%H:%M %d.%m.%Y')})\n\n"

    for machine in MACHINES:
        try:
            metrics = await get_remote_metrics(
                machine["host"],
                machine["user"],
                password=machine.get("password"),
                key_filename=machine.get("key_filename"),
            )
            report += (
                f"🖥 {machine['name']}:\n"
                f"\n"
                f"  CC: {metrics['cc']}\n"
                f"\n"
                f"  CPU: {metrics['cpu']:.1f}%\n"
                f"  {metrics['cpu_smiley']}\n"
                f"  RAM: {metrics['ram']:.1f}%\n"
                f"  {metrics['ram_smiley']}\n"
                f"  Swap: {metrics['swap']:.1f}%\n"
                f"  {metrics['swap_smiley']}\n"
                f"  Disk Used: {metrics['disk']}\n"
                f"  {metrics['disk_smiley']}\n"
                f"  TCP Mem: {metrics['tcp_mem']}\n"
                f"  {metrics['tcp_mem_smiley']}\n"
                f"\n"
                f"————————————————————\n\n"
            )
        except Exception as e:
            report += f"❌ {machine['name']}: ошибка подключения - {str(e)}\n\n"

    return report


async def collect_specific_metrics():
    metrics_dict = {}
    for machine in MACHINES:
        try:
            metrics = await get_remote_metrics(
                machine["host"],
                machine["user"],
                password=machine.get("password"),
                key_filename=machine.get("key_filename"),
            )
            metrics_dict[machine["host"]] = {
                "name": machine["name"],
                "swap": metrics["swap"],
                "disk_used": metrics["disk"],
                "tcp_mem": metrics["tcp_mem"],
            }
        except Exception as e:
            metrics_dict[machine["host"]] = {"name": machine["name"], "error": str(e)}
    return metrics_dict


async def generate_diff_report():
    config = load_config()
    start_time = config.get("start_time")
    end_time = config.get("end_time")
    data = load_data()
    if start_time not in data or end_time not in data:
        return "❌ Недостаточно данных для дневного отчета"

    report = f"📊 Дневной отчет ({end_time} - {start_time}) ({datetime.now().strftime('%H:%M %d.%m.%Y')})\n\n"

    for host in data[start_time]:
        if host in data[end_time]:
            start_metrics = data[start_time][host]
            end_metrics = data[end_time][host]
            if "error" in start_metrics or "error" in end_metrics:
                report += f"❌ {start_metrics['name']}: ошибка в данных\n\n"
                continue
            try:
                swap_diff = end_metrics["swap"] - start_metrics["swap"]
                # Для disk_used, парсить строку, например "10.50GB (50.0%)" -> 10.50
                start_disk_used_gb = float(start_metrics["disk_used"].split("GB")[0].strip())
                end_disk_used_gb = float(end_metrics["disk_used"].split("GB")[0].strip())
                disk_diff = end_disk_used_gb - start_disk_used_gb
                # Для tcp_mem, парсить "used/max (pct%)" -> used
                start_tcp_used = int(start_metrics["tcp_mem"].split("/")[0].strip())
                end_tcp_used = int(end_metrics["tcp_mem"].split("/")[0].strip())
                tcp_diff = end_tcp_used - start_tcp_used

                report += (
                    f"🖥 {start_metrics['name']}:\n"
                    f"  Swap diff: {swap_diff:.1f}%\n"
                    f"  Disk Used diff: {disk_diff:.2f}GB\n"
                    f"  TCP Mem diff: {tcp_diff}\n"
                    f"\n"
                    f"————————————————————\n\n"
                )
            except Exception as e:
                report += f"❌ {start_metrics['name']}: ошибка расчета - {str(e)}\n\n"
        else:
            name = data[start_time][host].get("name", host)
            report += f"❌ {name}: отсутствуют данные для {end_time}\n\n"

    return report


async def send_report():
    config = load_config()
    start_time = config.get("start_time")
    end_time = config.get("end_time")
    report_time = config.get("report_time")
    start_hour, start_min = map(int, start_time.split(":"))
    end_hour, end_min = map(int, end_time.split(":"))
    report_hour, report_min = map(int, report_time.split(":"))

    while True:
        now = datetime.now()
        # Вычислить время до следующего 1-минутного интервала
        next_check = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
        wait_seconds = (next_check - now).total_seconds()

        await asyncio.sleep(wait_seconds)

        now = datetime.now()
        try:
            if now.minute == 0:
                # Отправить полный отчет каждый час
                report = await generate_report()
                await bot.send_message(chat_id=CHAT_ID, text=report)
            elif now.hour == start_hour and now.minute == start_min:
                # Собрать и сохранить данные в start_time
                metrics = await collect_specific_metrics()
                save_data(start_time, metrics)
            elif now.hour == end_hour and now.minute == end_min:
                # Собрать и сохранить данные в end_time
                metrics = await collect_specific_metrics()
                save_data(end_time, metrics)
            elif now.hour == report_hour and now.minute == report_min:
                # Отправить дневной отчет с разницей
                report = await generate_diff_report()
                await bot.send_message(chat_id=CHAT_ID, text=report)
        except Exception as e:
            print(f"Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(send_report())
