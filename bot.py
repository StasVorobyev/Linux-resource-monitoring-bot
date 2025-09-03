import paramiko
import asyncio
from telegram import Bot
from datetime import datetime, timedelta

TOKEN = "YOUR TOKEN" # Токен вашего телеграм бота
CHAT_ID = "-ID" # ID вашего чата или группы. В формате "-12345678..."
bot = Bot(token=TOKEN)

# Конфигурация машин
MACHINES = [
    {"name": "Name of your machine (1.1.1.1)", "host": "1.1.1.1", "user": "login", "password": "password"}, # Имя, IP адрес, логин, пароль
    {"name": "Name of your machine (1.1.1.1)", "host": "1.1.1.1", "user": "login", "password": "password"}, # Имя, IP адрес, логин, пароль
    {"name": "Name of your machine (1.1.1.1)", "host": "1.1.1.1", "user": "login", "password": "password"}, # Имя, IP адрес, логин, пароль
    {"name": "Name of your machine (1.1.1.1)", "host": "1.1.1.1", "user": "login", "password": "password"}, # Имя, IP адрес, логин, пароль
]

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

async def get_remote_metrics(host, user, password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password)
    
    stdin, stdout, stderr = ssh.exec_command("top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'")
    cpu = float(stdout.read().decode().strip())
    
    stdin, stdout, stderr = ssh.exec_command("free | grep Mem | awk '{print $3/$2 * 100}'")
    ram = float(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command("free | grep Swap | awk '{print $3/$2 * 100}'")
    swap = float(stdout.read().decode().strip())
    
    stdin, stdout, stderr = ssh.exec_command("df | grep /dev/mapper/ubuntu--vg-ubuntu--lv | awk '{print ($2/1024)/1024}'")
    disk_max = float(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command("df | grep /dev/mapper/ubuntu--vg-ubuntu--lv | awk '{print ($3/1024)/1024}'")
    disk_used = float(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command("sudo sysctl net.ipv4.tcp_mem | awk '{print $5}'")
    tcp_mem_max = int(stdout.read().decode().strip())
    
    stdin, stdout, stderr = ssh.exec_command("cat /proc/net/sockstat | grep TCP | awk '{print $11}'")
    tcp_mem_used = int(stdout.read().decode().strip())

    stdin, stdout, stderr = ssh.exec_command("ss -4 | wc -l")
    cc = int(stdout.read().decode().strip())
    
    ssh.close()
    
    tcp_mem_free_pct = (tcp_mem_used / tcp_mem_max) * 100 if tcp_mem_max > 0 else 0
    disk_used_pct = (disk_used / disk_max) * 100 if disk_max > 0 else 0

    return {
        'cpu': cpu,
        'ram': ram,
        'swap': swap,
        'disk': f"{disk_used:.2f}GB ({disk_used_pct:.1f}%)",
        'tcp_mem': f"{tcp_mem_used}/{tcp_mem_max} ({tcp_mem_free_pct:.1f}% used)",
        'cpu_smiley': get_smiley(cpu, 100),
        'ram_smiley': get_smiley(ram, 100),
        'swap_smiley': get_smiley(swap, 100),
        'disk_smiley': get_smiley(disk_used_pct, 100),
        'tcp_mem_smiley': get_smiley(tcp_mem_free_pct, 100),
        'cc': cc
    }

async def generate_report():
    report = f"📊 Системный отчет ({datetime.now().strftime('%H:%M %d.%m.%Y')})\n\n"
    
    for machine in MACHINES:
        try:
            metrics = await get_remote_metrics(machine['host'], machine['user'], machine['password'])
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

async def send_report():
    while True:
        now = datetime.now()
        next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        wait_seconds = (next_hour - now).total_seconds()
        
        await asyncio.sleep(wait_seconds)
        
        try:
            report = await generate_report()
            await bot.send_message(chat_id=CHAT_ID, text=report)
        except Exception as e:
            print(f"Ошибка отправки отчета: {e}")

if __name__ == '__main__':
    asyncio.run(send_report())
