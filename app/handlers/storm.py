from datetime import datetime, timedelta
from sqlalchemy import select, func
import time
from functools import lru_cache
from typing import Optional, Tuple, Dict, Any

from ..models import AsyncSessionLocal, Whitelist, SecuritySettings, StormLog, RegistrationRequest

class StormProtection:
    """Класс для защиты от массовых регистраций с кэшированием"""
    
    def __init__(self, db_session):
        self.db = db_session
        # Кэш для настроек (обновляется раз в минуту)
        self._settings_cache = {}
        self._settings_cache_time = {}
        self._settings_cache_ttl = 60  # 60 секунд
        
        # Кэш для белого списка (обновляется раз в 5 минут)
        self._whitelist_cache = {
            'ip': {},
            'referral_code': {}
        }
        self._whitelist_cache_time = {}
        self._whitelist_cache_ttl = 300  # 5 минут
        
        # Кэш для счетчика запросов (храним в памяти)
        self._request_counter = {}
        self._request_counter_cleanup_time = time.time()
    
    async def _cleanup_old_cache(self):
        """Очищает устаревшие записи из кэша счетчика запросов"""
        now = time.time()
        if now - self._request_counter_cleanup_time > 3600:  # Раз в час
            cutoff = datetime.utcnow() - timedelta(hours=24)
            self._request_counter = {
                k: v for k, v in self._request_counter.items() 
                if v['timestamp'] > cutoff
            }
            self._request_counter_cleanup_time = now
    
    async def get_setting(self, key: str, default: str) -> str:
        """
        Получает настройку из БД с кэшированием на 60 секунд
        """
        now = time.time()
        
        # Проверяем кэш
        if key in self._settings_cache:
            if now - self._settings_cache_time.get(key, 0) < self._settings_cache_ttl:
                return self._settings_cache[key]
        
        # Загружаем из БД
        result = await self.db.execute(
            select(SecuritySettings).where(SecuritySettings.key == key)
        )
        setting = result.scalar_one_or_none()
        value = setting.value if setting else default
        
        # Сохраняем в кэш
        self._settings_cache[key] = value
        self._settings_cache_time[key] = now
        
        return value
    
    async def _load_whitelist_to_cache(self):
        """
        Загружает весь белый список в кэш
        """
        now = datetime.utcnow()
        
        # Загружаем все активные записи из белого списка
        result = await self.db.execute(
            select(Whitelist).where(
                (Whitelist.expires_at > now) | (Whitelist.expires_at.is_(None))
            )
        )
        whitelist_entries = result.scalars().all()
        
        # Очищаем кэш
        self._whitelist_cache = {
            'ip': {},
            'referral_code': {}
        }
        
        # Заполняем кэш
        for entry in whitelist_entries:
            if entry.type in ['ip', 'referral_code']:
                self._whitelist_cache[entry.type][entry.value] = {
                    'id': entry.id,
                    'reason': entry.reason,
                    'expires_at': entry.expires_at
                }
        
        self._whitelist_cache_time['last_update'] = time.time()
    
    async def is_whitelisted(self, ip: str, referral_code: str = None) -> bool:
        """
        Проверяет, находится ли IP или код в белом списке (с кэшированием)
        """
        now = time.time()
        
        # Обновляем кэш если нужно (раз в 5 минут)
        if now - self._whitelist_cache_time.get('last_update', 0) > self._whitelist_cache_ttl:
            await self._load_whitelist_to_cache()
        
        # Проверяем IP
        if ip in self._whitelist_cache['ip']:
            entry = self._whitelist_cache['ip'][ip]
            # Проверяем, не истек ли срок
            if entry['expires_at'] and entry['expires_at'] < datetime.utcnow():
                # Удаляем из кэша
                del self._whitelist_cache['ip'][ip]
            else:
                return True
        
        # Проверяем реферальный код
        if referral_code and referral_code in self._whitelist_cache['referral_code']:
            entry = self._whitelist_cache['referral_code'][referral_code]
            if entry['expires_at'] and entry['expires_at'] < datetime.utcnow():
                del self._whitelist_cache['referral_code'][referral_code]
            else:
                return True
        
        return False
    
    async def check_ip_limit(self, ip: str) -> Tuple[bool, int]:
        """
        Проверяет лимит регистраций с одного IP с использованием кэша в памяти
        """
        limit = int(await self.get_setting('ip_limit', '5'))
        
        # Очищаем старые записи
        await self._cleanup_old_cache()
        
        # Используем кэш в памяти вместо запроса к БД
        cache_key = f"ip_{ip}"
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        
        if cache_key not in self._request_counter:
            # Если нет в кэше, считаем из БД
            result = await self.db.execute(
                select(func.count())
                .where(
                    RegistrationRequest.ip_address == ip,
                    RegistrationRequest.created_at > day_ago
                )
            )
            count = result.scalar() or 0
            
            # Сохраняем в кэш
            self._request_counter[cache_key] = {
                'count': count,
                'timestamp': now
            }
        else:
            # Берем из кэша
            count = self._request_counter[cache_key]['count']
        
        return count < limit, count
    
    async def check_storm(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Проверяет, не начался ли шторм (с кэшированием на 30 секунд)
        """
        threshold = int(await self.get_setting('storm_threshold', '100'))
        cooldown = int(await self.get_setting('storm_cooldown', '60'))
        
        # Кэшируем результат проверки шторма на 30 секунд
        cache_key = "storm_check"
        now = time.time()
        
        if hasattr(self, '_storm_cache') and now - self._storm_cache_time < 30:
            return self._storm_cache['in_storm'], self._storm_cache['stats']
        
        # Считаем количество заявок за последние cooldown минут
        cutoff = datetime.utcnow() - timedelta(minutes=cooldown)
        
        result = await self.db.execute(
            select(func.count())
            .where(RegistrationRequest.created_at > cutoff)
        )
        count = result.scalar() or 0
        
        # Получаем уникальные IP
        ips_result = await self.db.execute(
            select(RegistrationRequest.ip_address)
            .where(RegistrationRequest.created_at > cutoff)
            .distinct()
        )
        ips = [row[0] for row in ips_result if row[0]]
        
        in_storm = count >= threshold
        
        stats = {
            'count': count,
            'threshold': threshold,
            'ips': len(ips),
            'in_storm': in_storm
        }
        
        # Если шторм начался, логируем его
        if in_storm:
            log = StormLog(
                requests_count=count,
                ip_addresses=','.join(ips[:10]),
                action_taken='storm_activated'
            )
            self.db.add(log)
            await self.db.commit()
        
        # Сохраняем в кэш
        self._storm_cache = {
            'in_storm': in_storm,
            'stats': stats
        }
        self._storm_cache_time = now
        
        return in_storm, stats
    
    async def add_to_whitelist(self, type: str, value: str, reason: str, 
                               created_by: int, expires_at: datetime = None):
        """
        Добавляет запись в белый список и обновляет кэш
        """
        entry = Whitelist(
            type=type,
            value=value,
            reason=reason,
            created_by=created_by,
            expires_at=expires_at
        )
        self.db.add(entry)
        await self.db.commit()
        
        # Обновляем кэш
        if type in ['ip', 'referral_code']:
            self._whitelist_cache[type][value] = {
                'id': entry.id,
                'reason': reason,
                'expires_at': expires_at
            }
        
        return entry
    
    async def remove_from_whitelist(self, entry_id: int) -> bool:
        """
        Удаляет запись из белого списка и обновляет кэш
        """
        entry = await self.db.get(Whitelist, entry_id)
        if entry:
            # Удаляем из кэша
            if entry.type in ['ip', 'referral_code']:
                if entry.value in self._whitelist_cache[entry.type]:
                    del self._whitelist_cache[entry.type][entry.value]
            
            await self.db.delete(entry)
            await self.db.commit()
            return True
        return False
    
    async def increment_ip_counter(self, ip: str):
        """
        Увеличивает счетчик запросов с IP (для ручного обновления после регистрации)
        """
        cache_key = f"ip_{ip}"
        now = datetime.utcnow()
        
        if cache_key in self._request_counter:
            self._request_counter[cache_key]['count'] += 1
        else:
            # Если нет в кэше, считаем из БД и добавляем
            day_ago = now - timedelta(days=1)
            result = await self.db.execute(
                select(func.count())
                .where(
                    RegistrationRequest.ip_address == ip,
                    RegistrationRequest.created_at > day_ago
                )
            )
            count = (result.scalar() or 0) + 1
            
            self._request_counter[cache_key] = {
                'count': count,
                'timestamp': now
            }