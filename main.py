import socket
import threading
import json
import tkinter as tk
from datetime import datetime

# --- Настройки ---
BROADCAST_PORT = 9090
BUFFER_SIZE = 1024
HISTORY_FILE = "chat_history.log"

# --- Глобальные переменные ---
username = input("Введите ваше имя: ")
tcp_port = int(input("Введите порт для этого узла: "))

# Список обнаруженных узлов
peers = {}

# --- Логирование ---
def log_event(event_type, message):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(HISTORY_FILE, "a") as file:
        file.write(f"{timestamp} {event_type}: {message}\n")


# --- Обнаружение узлов через UDP ---
def discover_peers():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    message = json.dumps({"type": "discover", "name": username, "port": tcp_port}).encode()
    sock.sendto(message, ('255.255.255.255', BROADCAST_PORT))


# --- Слушаем входящие UDP-пакеты для обнаружения узлов ---
def listen_for_peers():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", BROADCAST_PORT))

    while True:
        data, addr = sock.recvfrom(BUFFER_SIZE)
        msg = json.loads(data.decode())

        if msg["type"] == "discover" and msg["port"] != tcp_port:
            peers[msg["name"]] = msg["port"]
            log_event("NEW NODE", f"{msg['name']} ({msg['port']}) обнаружен")
            display_system_message(f"{msg['name']} присоединился к чату")


# --- Слушаем входящие сообщения ---
def listen_for_messages():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("0.0.0.0", tcp_port))
    server_socket.listen()

    while True:
        conn, addr = server_socket.accept()
        print(f"🔗 Подключился {addr}")

        while True:
            try:
                data = conn.recv(BUFFER_SIZE).decode().strip()
                if not data:
                    break

                msg = json.loads(data)
                log_event("MESSAGE", f"{msg['name']} ({msg['port']}): {msg['text']}")
                display_message(msg["name"], msg["text"])

                conn.send(json.dumps({"type": "ack", "status": "received"}).encode())  # Подтверждение
            except socket.timeout:
                break

        conn.close()


# --- Отправка сообщений ---
def send_message(msg):
    if not msg.strip():
        return

    for name, port in peers.items():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", port))
            sock.send(json.dumps({"type": "message", "name": username, "port": tcp_port, "text": msg}).encode())

            response = sock.recv(BUFFER_SIZE).decode()
            print(f"🔄 Ответ от узла {name}: {response}")

            sock.close()
        except:
            print(f"⚠ Не удалось отправить сообщение узлу {name}")

    log_event("MY MESSAGE", f"Я: {msg}")
    display_message(username, msg)


# --- Графический интерфейс ---
def display_message(sender, msg):
    chat_window.config(state="normal")
    chat_window.insert(tk.END, f"{sender}: {msg}\n")
    chat_window.config(state="disabled")


def display_system_message(msg):
    chat_window.config(state="normal")
    chat_window.insert(tk.END, f"{msg}\n", "system")
    chat_window.config(state="disabled")


def send_button_action(event=None):
    msg = entry.get() if event is None else event.widget.get()
    if msg.strip():
        send_message(msg)
        entry.delete(0, tk.END) if event is None else event.widget.delete(0, tk.END)


root = tk.Tk()
root.title(f"P2P Chat - {username}")

chat_window = tk.Text(root, height=20, width=50)
chat_window.pack()

entry = tk.Entry(root, width=50)
entry.bind("<Return>", send_button_action)
entry.pack()

send_button = tk.Button(root, text="Отправить", command=lambda: send_button_action(None))
send_button.pack()

# --- Запуск потоков ---
threading.Thread(target=listen_for_peers, daemon=True).start()
threading.Thread(target=listen_for_messages, daemon=True).start()
discover_peers()

# --- Запуск интерфейса ---
root.mainloop()
