import socket
import threading
import select
import logging
import socks
import struct
import time
from urllib.parse import urlparse

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

class MTProtoToSOCKS5Proxy:
    def __init__(self):
        self.server_socket = None
        self.running = False
        self.proxy_timeout = 30  # таймаут для прокси
        
    def start(self):
        """Запускает SOCKS5 прокси-сервер"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((SOCKS5_HOST, SOCKS5_PORT))
        self.server_socket.listen(100)
        self.server_socket.settimeout(1)  # таймаут для accept
        self.running = True
        
        logging.info(f"🚀 SOCKS5 прокси запущен на {SOCKS5_HOST}:{SOCKS5_PORT}")
        logging.info(f"🔌 Перенаправляет через MTProto: {MT_PROXY_HOST}:{MT_PROXY_PORT}")
        logging.info(f"⏱️ Таймаут соединения: {self.proxy_timeout} секунд")
        
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                client_socket.settimeout(self.proxy_timeout)
                threading.Thread(
                    target=self.handle_client, 
                    args=(client_socket, addr),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Ошибка принятия соединения: {e}")
    
    def handle_client(self, client_socket, addr):
        """Обрабатывает клиентское соединение (SOCKS5 handshake)"""
        try:
            logging.info(f"📡 Новое соединение от {addr[0]}:{addr[1]}")
            
            # SOCKS5 handshake
            data = self.recv_all(client_socket, 2)
            if not data or len(data) < 2:
                return
            
            # Отправляем ответ на handshake
            client_socket.send(b'\x05\x00')
            
            # Получаем запрос на соединение
            data = self.recv_all(client_socket, 4)
            if not data or len(data) < 4:
                return
            
            # Проверяем версию и команду
            if data[0] != 0x05 or data[1] != 0x01:
                logging.error(f"Неверный SOCKS запрос: {data.hex()}")
                return
            
            # Извлекаем адрес и порт назначения
            addr_type = data[3]
            
            if addr_type == 0x01:  # IPv4
                data = self.recv_all(client_socket, 6)  # 4 IP + 2 порт
                if not data:
                    return
                host = socket.inet_ntoa(data[:4])
                port = struct.unpack('>H', data[4:6])[0]
            elif addr_type == 0x03:  # Доменное имя
                data = self.recv_all(client_socket, 1)
                if not data:
                    return
                addr_len = data[0]
                data = self.recv_all(client_socket, addr_len + 2)
                if not data:
                    return
                host = data[:addr_len].decode()
                port = struct.unpack('>H', data[addr_len:addr_len+2])[0]
            else:
                logging.error(f"Неизвестный тип адреса: {addr_type}")
                return
            
            logging.info(f"🌐 Запрос к {host}:{port}")
            
            # Создаем соединение с MTProto прокси
            mt_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            mt_socket.settimeout(self.proxy_timeout)
            mt_socket.connect((MT_PROXY_HOST, MT_PROXY_PORT))
            
            # Отправляем секрет MTProto
            secret_bytes = bytes.fromhex(MT_PROXY_SECRET)
            mt_socket.send(secret_bytes)
            
            # Отправляем адрес назначения через MTProto
            # Упаковываем адрес в формат, понятный MTProto
            if addr_type == 0x01:  # IPv4
                mt_socket.send(data[:6])  # адрес (4 байта) + порт (2 байта)
            elif addr_type == 0x03:  # Доменное имя
                mt_socket.send(bytes([addr_len]) + host.encode() + struct.pack('>H', port))
            
            # Отправляем ответ клиенту (успешное соединение)
            client_socket.send(b'\x05\x00\x00\x01' + socket.inet_aton('0.0.0.0') + struct.pack('>H', 0))
            
            logging.info(f"✅ Соединение установлено, передача данных...")
            
            # Передаем данные между клиентом и MTProto
            self.forward_data(client_socket, mt_socket)
            
        except socket.timeout:
            logging.error(f"❌ Таймаут при обработке клиента {addr}")
        except Exception as e:
            logging.error(f"❌ Ошибка обработки клиента {addr}: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def recv_all(self, sock, n):
        """Получает точно n байт из сокета"""
        data = bytearray()
        while len(data) < n:
            try:
                packet = sock.recv(n - len(data))
                if not packet:
                    return None
                data.extend(packet)
            except socket.timeout:
                return None
            except Exception:
                return None
        return bytes(data)
    
    def forward_data(self, src, dst):
        """Пересылает данные между двумя сокетами"""
        sockets = [src, dst]
        while True:
            try:
                r_sockets, _, _ = select.select(sockets, [], [], 5)
                if not r_sockets:
                    continue
                    
                for sock in r_sockets:
                    data = sock.recv(4096)
                    if not data:
                        return
                    if sock is src:
                        dst.send(data)
                    else:
                        src.send(data)
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Ошибка передачи данных: {e}")
                return

if __name__ == "__main__":
    proxy = MTProtoToSOCKS5Proxy()
    try:
        proxy.start()
    except KeyboardInterrupt:
        logging.info("🛑 Прокси остановлен")