import socket
import threading
import json
import tkinter as tk
from datetime import datetime

# --- Настройки ---
BROADCAST_PORT = 9090
BUFFER_SIZE = 1024
HISTORY_FILE = "chat_history.log"
PEER_TIMEOUT = 100

# --- Глобальные переменные ---
username = input("Введите ваше имя: ")
tcp_port = int(input("Введите порт для этого узла: "))

peers = {}
running = True


# --- Логирование ---
def log_event(event_type, message):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(HISTORY_FILE, "a") as file:
        file.write(f"{timestamp} {event_type}: {message}\n")


# --- Отправка широковещательного сообщения о выходе ---
def send_goodbye():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    message = json.dumps({"type": "goodbye", "name": username, "port": tcp_port}).encode()
    sock.sendto(message, ('255.255.255.255', BROADCAST_PORT))
    sock.close()


# --- Обнаружение узлов ---
def discover_peers():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    message = json.dumps({"type": "discover", "name": username, "port": tcp_port}).encode()
    sock.sendto(message, ('255.255.255.255', BROADCAST_PORT))
    sock.close()


# --- Проверка активности узлов ---
def check_peers_alive():
    now = datetime.now()
    dead_peers = []

    for name, (ip, port, last_seen) in peers.items():
        if (now - last_seen).total_seconds() > PEER_TIMEOUT:
            dead_peers.append(name)

    for name in dead_peers:
        del peers[name]
        display_system_message(f"{name} неактивен (таймаут)")
        log_event("PEER_LEFT", f"{name} неактивен по таймауту")

    root.after(100000, check_peers_alive)


# --- Слушаем UDP-пакеты ---
def listen_for_peers():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", BROADCAST_PORT))

    while running:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            msg = json.loads(data.decode())

            if msg["port"] != tcp_port:  # Игнорируем свои сообщения
                if msg["type"] == "discover":
                    handle_new_peer(msg["name"], addr[0], msg["port"])
                elif msg["type"] == "goodbye":
                    handle_peer_leaving(msg["name"])
        except:
            pass

    sock.close()


def handle_new_peer(name, ip, port):
    if name not in peers:
        peers[name] = (ip, port, datetime.now())
        display_system_message(f"{name} присоединился к чату")
        log_event("PEER_JOINED", f"{name} ({ip}:{port})")
    else:
        # Обновляем информацию и время последней активности
        peers[name] = (ip, port, datetime.now())


def handle_peer_leaving(name):
    if name in peers:
        del peers[name]
        display_system_message(f"{name} покинул чат")
        log_event("PEER_LEFT", f"{name} покинул чат")


# --- Слушаем TCP-соединения ---
def listen_for_messages():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("0.0.0.0", tcp_port))
    server_socket.listen()

    while running:
        try:
            conn, addr = server_socket.accept()
            threading.Thread(target=handle_client, args=(conn, addr)).start()
        except:
            pass

    server_socket.close()


def handle_client(conn, addr):
    try:
        while True:
            data = conn.recv(BUFFER_SIZE).decode().strip()
            if not data:
                break

            msg = json.loads(data)
            peers[msg["name"]] = (addr[0], msg["port"], datetime.now())  # Обновляем время активности

            if msg["type"] == "message":
                display_message(msg["name"], msg["text"])
                log_event("MESSAGE", f"{msg['name']} ({addr[0]}:{msg['port']}): {msg['text']}")

            conn.send(json.dumps({"type": "ack"}).encode())
    except:
        pass
    finally:
        conn.close()


# --- Отправка сообщений ---
def send_message(msg):
    if not msg.strip():
        return

    failed_peers = []
    for name, (ip, port, _) in peers.items():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((ip, port))
            sock.send(json.dumps({
                "type": "message",
                "name": username,
                "port": tcp_port,
                "text": msg
            }).encode())
            sock.recv(BUFFER_SIZE)  # Ждем подтверждение
            sock.close()
        except:
            failed_peers.append(name)

    # Обрабатываем недоступные узлы
    for name in failed_peers:
        handle_peer_leaving(name)

    display_message(username, msg)
    log_event("MY_MESSAGE", f"Я: {msg}")


# --- GUI ---
def display_message(sender, msg):
    chat_window.config(state="normal")
    chat_window.insert(tk.END, f"{sender}: {msg}\n")
    chat_window.config(state="disabled")
    chat_window.see(tk.END)


def display_system_message(msg):
    chat_window.config(state="normal")
    chat_window.insert(tk.END, f"SYSTEM: {msg}\n", "system")
    chat_window.config(state="disabled")
    chat_window.see(tk.END)


def on_closing():
    global running
    running = False
    send_goodbye()
    root.destroy()


# --- Инициализация GUI ---
root = tk.Tk()
root.title(f"P2P Chat - {username}")
root.protocol("WM_DELETE_WINDOW", on_closing)

chat_window = tk.Text(root, height=20, width=50)
chat_window.tag_config("system", foreground="blue")
chat_window.pack()

entry = tk.Entry(root, width=50)
entry.pack()


def send():
    msg = entry.get()
    if msg.strip():
        send_message(msg)
        entry.delete(0, tk.END)


entry.bind("<Return>", lambda e: send())
tk.Button(root, text="Отправить", command=send).pack()

# --- Запуск сервисов ---
threading.Thread(target=listen_for_peers, daemon=True).start()
threading.Thread(target=listen_for_messages, daemon=True).start()
root.after(1000, discover_peers)
root.after(10000, check_peers_alive)

root.mainloop()
