// ==========================================
// Тёмная тема
// ==========================================
(function() {
    // Проверяем сохранённую тему
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
        document.body.classList.add('dark');
    }
    
    // Переключатель темы (кнопка в меню)
    const themeSwitch = document.getElementById('theme-switch-mobile');
    if (themeSwitch) {
        // Устанавливаем правильный текст при загрузке
        const isDark = document.body.classList.contains('dark');
        themeSwitch.textContent = isDark ? '☀️ Светлая' : '🌙 Тема';
        
        themeSwitch.addEventListener('click', () => {
            document.body.classList.toggle('dark');
            const isDarkNow = document.body.classList.contains('dark');
            localStorage.setItem('theme', isDarkNow ? 'dark' : 'light');
            
            // Меняем текст кнопки
            themeSwitch.textContent = isDarkNow ? '☀️ Светлая' : '🌙 Тема';
        });
    }
})();

// ==========================================
// Мобильное меню
// ==========================================
document.addEventListener('DOMContentLoaded', function() {
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    if (navToggle && navMenu) {
        navToggle.addEventListener('click', () => {
            navMenu.classList.toggle('active');
        });
    }
});

// ==========================================
// Копирование реферальной ссылки
// ==========================================
function copyReferralLink() {
    const input = document.getElementById('referral-link');
    if (input) {
        input.select();
        input.setSelectionRange(0, 99999);
        document.execCommand('copy');
        
        // Показываем уведомление
        const button = event.target;
        const originalText = button.textContent;
        button.textContent = '✅ Скопировано!';
        setTimeout(() => {
            button.textContent = originalText;
        }, 2000);
    }
}

// ==========================================
// Форматирование номера телефона
// ==========================================
function formatPhoneNumber(input) {
    let value = input.value.replace(/\D/g, '');
    if (value.startsWith('7') || value.startsWith('8')) {
        value = value.substring(1);
    }
    if (value.length > 10) value = value.substring(0, 10);
    
    let formatted = '+7';
    if (value.length > 0) formatted += ' ' + value.substring(0, 3);
    if (value.length > 3) formatted += ' ' + value.substring(3, 6);
    if (value.length > 6) formatted += '-' + value.substring(6, 8);
    if (value.length > 8) formatted += '-' + value.substring(8, 10);
    
    input.value = formatted;
}

// Применяем форматирование к полям телефона
document.addEventListener('DOMContentLoaded', function() {
    const phoneInputs = document.querySelectorAll('input[type="tel"]');
    phoneInputs.forEach(input => {
        input.addEventListener('input', () => formatPhoneNumber(input));
    });
});