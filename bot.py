from config import MACHINES, TOKEN, CHAT_ID, TIMEZONE_OFFSET
from datetime import datetime, timedelta
from telegram import Bot
import paramiko
import asyncio
import json
import os
import subprocess

# Проверка на уже запущенный экземпляр
result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
lines = [line for line in result.stdout.split('\n') if 'python' in line and 'bot.py' in line and 'grep' not in line]
if len(lines) > 1:
    print("Bot already running")
    exit(1)

bot = Bot(token=TOKEN)
PREVIOUS_METRICS_FILE = "data.json"


def load_previous_metrics():
    if os.path.exists(PREVIOUS_METRICS_FILE):
        try:
            with open(PREVIOUS_METRICS_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_previous_metrics(metrics):
    # Сохраняем только числовые метрики
    numerical_keys = ["cpu", "ram", "swap", "disk", "tcp_mem", "cc"]
    numerical_metrics = {
        host: (
            {k: v for k, v in host_metrics.items() if k in numerical_keys}
            if host_metrics
            else None
        )
        for host, host_metrics in metrics.items()
    }
    with open(PREVIOUS_METRICS_FILE, "w") as f:
        json.dump(numerical_metrics, f, indent=4)


previous_full_metrics = load_previous_metrics()


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


async def generate_report_with_diff(current_metrics, previous_metrics):
    time = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
    report = f"📊 Системный отчет ({time.strftime('%H:%M %d.%m.%Y')})\n\n"

    for machine in MACHINES:
        host = machine["host"]
        if host in current_metrics and current_metrics[host] is not None:
            metrics = current_metrics[host]
            diffs = {}
            if host in previous_metrics and previous_metrics[host] is not None:
                prev = previous_metrics[host]
                diffs["cpu"] = metrics["cpu"] - prev["cpu"]
                diffs["ram"] = metrics["ram"] - prev["ram"]
                diffs["swap"] = metrics["swap"] - prev["swap"]
                # For disk, parse GB
                curr_disk_gb = float(metrics["disk"].split("GB")[0].strip())
                prev_disk_gb = float(prev["disk"].split("GB")[0].strip())
                diffs["disk"] = curr_disk_gb - prev_disk_gb
                # For tcp_mem, parse used
                curr_tcp_used = int(metrics["tcp_mem"].split("/")[0].strip())
                prev_tcp_used = int(prev["tcp_mem"].split("/")[0].strip())
                diffs["tcp_mem"] = curr_tcp_used - prev_tcp_used
                diffs["cc"] = metrics["cc"] - prev["cc"]
            else:
                diffs = {k: 0 for k in ["cpu", "ram", "swap", "disk", "tcp_mem", "cc"]}

            def format_diff(key, value, unit):
                diff = diffs[key]
                sign = "+" if diff >= 0 else ""
                if key in ["cpu", "ram", "swap"]:
                    return f"{value} ({sign}{diff:.1f}{unit})"
                elif key == "disk":
                    return f"{value} ({sign}{diff:.2f}{unit})"
                else:
                    return f"{value} ({sign}{int(diff)})"

            cpu_value = f"{metrics['cpu']:.1f}%"
            ram_value = f"{metrics['ram']:.1f}%"
            swap_value = f"{metrics['swap']:.1f}%"

            report += (
                f"🖥 {machine['name']}:\n"
                f"\n"
                f"  CC: {format_diff('cc', metrics['cc'], '')}\n"
                f"\n"
                f"  CPU: {format_diff('cpu', cpu_value, '%')}\n"
                f"  {metrics['cpu_smiley']}\n"
                f"  RAM: {format_diff('ram', ram_value, '%')}\n"
                f"  {metrics['ram_smiley']}\n"
                f"  Swap: {format_diff('swap', swap_value, '%')}\n"
                f"  {metrics['swap_smiley']}\n"
                f"  Disk Used: {format_diff('disk', metrics['disk'], 'GB')}\n"
                f"  {metrics['disk_smiley']}\n"
                f"  TCP Mem: {format_diff('tcp_mem', metrics['tcp_mem'], '')}\n"
                f"  {metrics['tcp_mem_smiley']}\n"
                f"\n"
                f"————————————————————\n\n"
            )
        else:
            report += f"❌ {machine['name']}: ошибка подключения\n\n"

    return report


async def send_report():
    global previous_full_metrics

    while True:
        now = datetime.now()
        # Вычислить время до следующего 1-минутного интервала
        next_check = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
        wait_seconds = (next_check - now).total_seconds()

        await asyncio.sleep(wait_seconds)

        now = datetime.now()
        try:
            if now.minute == 0:
                # Собрать текущие метрики
                current_full_metrics = {}
                for machine in MACHINES:
                    try:
                        metrics = await get_remote_metrics(
                            machine["host"],
                            machine["user"],
                            password=machine.get("password"),
                            key_filename=machine.get("key_filename"),
                        )
                        current_full_metrics[machine["host"]] = metrics
                    except Exception as e:
                        current_full_metrics[machine["host"]] = None
                        print(f"Ошибка подключения к {machine['name']}: {e}")

                # Генерировать отчет с разницей
                report = await generate_report_with_diff(
                    current_full_metrics, previous_full_metrics
                )
                await bot.send_message(chat_id=CHAT_ID, text=report)

                # Обновить предыдущие метрики
                previous_full_metrics = current_full_metrics
                save_previous_metrics(previous_full_metrics)

        except Exception as e:
            print(f"Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(send_report())
