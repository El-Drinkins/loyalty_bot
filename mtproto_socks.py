import asyncio
import logging
from pyrogram import Client
from pyrogram.raw import functions
import socket
import threading
import socks
import select
import struct

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ==================================================
# ВАШ MTProto ПРОКСИ
# ==================================================
MT_PROXY_HOST = "91.107.123.239"
MT_PROXY_PORT = 8443
MT_PROXY_SECRET = "ee368fefe53d5eadfb36ac2319969f887e6d61696c2e7275"
# ==================================================

# Локальный SOCKS5 прокси
SOCKS5_HOST = "127.0.0.1"
SOCKS5_PORT = 1080

class SimpleSOCKS5Server:
    """Простой SOCKS5 сервер для тестирования"""
    
    def __init__(self, host='127.0.0.1', port=1080):
        self.host = host
        self.port = port
        self.server = None
        self.running = False
        
    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(5)
        self.server.settimeout(1)
        self.running = True
        
        logging.info(f"🚀 SOCKS5 сервер запущен на {self.host}:{self.port}")
        
        while self.running:
            try:
                client, addr = self.server.accept()
                threading.Thread(target=self.handle_client, args=(client, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Ошибка принятия соединения: {e}")
                
    def stop(self):
        self.running = False
        if self.server:
            self.server.close()
            
    def handle_client(self, client, addr):
        """Обрабатывает SOCKS5 клиента (просто перенаправляет на внешний сервер)"""
        try:
            # Принимаем handshake
            data = client.recv(256)
            if not data:
                return
                
            # Отправляем ответ
            client.send(b'\x05\x00')
            
            # Получаем запрос
            data = client.recv(256)
            if not data:
                return
                
            # Парсим запрос
            cmd = data[1]
            if cmd != 1:  # CONNECT
                client.close()
                return
                
            # Определяем тип адреса
            atyp = data[3]
            if atyp == 1:  # IPv4
                dst_addr = socket.inet_ntoa(data[4:8])
                dst_port = struct.unpack('>H', data[8:10])[0]
                reply = b'\x05\x00\x00\x01' + data[4:8] + data[8:10]
            elif atyp == 3:  # Domain name
                domain_len = data[4]
                dst_addr = data[5:5+domain_len].decode()
                dst_port = struct.unpack('>H', data[5+domain_len:7+domain_len])[0]
                reply = b'\x05\x00\x00\x03' + data[4:7+domain_len]
            else:
                client.close()
                return
                
            logging.info(f"📡 Запрос к {dst_addr}:{dst_port}")
            
            # Подключаемся к внешнему серверу (MTProto)
            remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote.connect((MT_PROXY_HOST, MT_PROXY_PORT))
            
            # Отправляем секрет
            remote.send(bytes.fromhex(MT_PROXY_SECRET))
            
            # Отправляем ответ клиенту
            client.send(reply)
            
            # Передаем данные
            self.forward_data(client, remote)
            
        except Exception as e:
            logging.error(f"Ошибка обработки клиента: {e}")
        finally:
            client.close()
            
    def forward_data(self, client, remote):
        """Пересылает данные между сокетами"""
        sockets = [client, remote]
        while True:
            try:
                r, _, _ = select.select(sockets, [], [], 1)
                if not r:
                    continue
                    
                for sock in r:
                    data = sock.recv(4096)
                    if not data:
                        return
                    if sock is client:
                        remote.send(data)
                    else:
                        client.send(data)
            except Exception as e:
                logging.error(f"Ошибка передачи: {e}")
                return

if __name__ == "__main__":
    server = SimpleSOCKS5Server()
    try:
        server.start()
    except KeyboardInterrupt:
        logging.info("🛑 Сервер остановлен")
        server.stop()