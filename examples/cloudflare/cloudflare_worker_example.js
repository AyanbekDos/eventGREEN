/**
 * CLOUDFLARE WORKER ДЛЯ EVENTGREEN BOT УВЕДОМЛЕНИЙ
 * Обрабатывает cron triggers и отправляет уведомления
 */

// Конфигурация уведомлений (будет обновляться из Python бота)
const NOTIFICATIONS_CONFIG = {
  "cron_triggers": [
    {
      "cron": "53 09 * * *",
      "notification_id": "notification_09_53"
    },
    {
      "cron": "55 09 * * *", 
      "notification_id": "notification_09_55"
    }
  ],
  "notifications": {
    "notification_09_53": {
      "utc_time": "09:53",
      "user_ids": ["34975055"],
      "local_info": "14:53 Asia/Almaty",
      "cron_expression": "53 09 * * *"
    },
    "notification_09_55": {
      "utc_time": "09:55", 
      "user_ids": ["7059952799"],
      "local_info": "14:55 Asia/Almaty",
      "cron_expression": "55 09 * * *"
    }
  }
};

// Основной обработчик Worker
export default {
  async scheduled(event, env, ctx) {
    // Обрабатываем cron triggers
    console.log('🕐 Cloudflare Worker cron trigger запущен:', new Date().toISOString());
    
    try {
      // Определяем какое уведомление нужно отправить на основе времени
      const currentUTC = new Date();
      const currentTime = currentUTC.getUTCHours().toString().padStart(2, '0') + 
                         ':' + currentUTC.getUTCMinutes().toString().padStart(2, '0');
      
      console.log('🕐 Текущее UTC время:', currentTime);
      
      // Ищем соответствующее уведомление
      let notificationToSend = null;
      for (const [notificationId, notification] of Object.entries(NOTIFICATIONS_CONFIG.notifications)) {
        if (notification.utc_time === currentTime) {
          notificationToSend = { id: notificationId, ...notification };
          break;
        }
      }
      
      if (notificationToSend) {
        console.log('📤 Найдено уведомление для отправки:', notificationToSend.id);
        await sendNotifications(notificationToSend, env);
      } else {
        console.log('⚠️ Не найдено уведомлений для текущего времени:', currentTime);
      }
      
    } catch (error) {
      console.error('❌ Ошибка обработки cron trigger:', error);
    }
  },

  async fetch(request, env, ctx) {
    // HTTP обработчик для ручного вызова уведомлений и управления
    const url = new URL(request.url);
    
    if (url.pathname === '/health') {
      return new Response(JSON.stringify({
        status: 'ok',
        timestamp: new Date().toISOString(),
        notifications_count: Object.keys(NOTIFICATIONS_CONFIG.notifications).length
      }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    if (url.pathname === '/notifications/trigger' && request.method === 'POST') {
      // Ручной запуск уведомления
      const { notification_id } = await request.json();
      
      const notification = NOTIFICATIONS_CONFIG.notifications[notification_id];
      if (!notification) {
        return new Response(JSON.stringify({
          error: 'Notification not found',
          notification_id
        }), { 
          status: 404,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      
      try {
        await sendNotifications({ id: notification_id, ...notification }, env);
        return new Response(JSON.stringify({
          success: true,
          notification_id,
          user_count: notification.user_ids.length
        }), {
          headers: { 'Content-Type': 'application/json' }
        });
      } catch (error) {
        return new Response(JSON.stringify({
          error: error.message,
          notification_id
        }), { 
          status: 500,
          headers: { 'Content-Type': 'application/json' }
        });
      }
    }
    
    if (url.pathname === '/notifications/status') {
      // Статус системы уведомлений
      return new Response(JSON.stringify({
        notifications_count: Object.keys(NOTIFICATIONS_CONFIG.notifications).length,
        cron_triggers_count: NOTIFICATIONS_CONFIG.cron_triggers.length,
        notifications: NOTIFICATIONS_CONFIG.notifications,
        current_utc: new Date().toISOString()
      }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    return new Response('EventGREEN Bot Notifications Worker', { status: 200 });
  }
};

/**
 * Отправляет уведомления пользователям через Telegram Bot API
 */
async function sendNotifications(notification, env) {
  console.log('📤 Начинаем отправку уведомлений:', notification.id);
  console.log('👥 Пользователи:', notification.user_ids);
  console.log('🌍 Локальная информация:', notification.local_info);
  
  const telegramToken = env.TELEGRAM_BOT_TOKEN;
  if (!telegramToken) {
    throw new Error('TELEGRAM_BOT_TOKEN не настроен в переменных окружения');
  }
  
  const results = [];
  
  for (const userId of notification.user_ids) {
    try {
      // Получаем события для пользователя
      const events = await getUserEvents(userId, env);
      
      if (events && events.length > 0) {
        // Форматируем сообщение
        const message = await formatDailyNotification(events, notification.local_info);
        
        // Отправляем в Telegram
        const telegramUrl = `https://api.telegram.org/bot${telegramToken}/sendMessage`;
        const response = await fetch(telegramUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: userId,
            text: message,
            parse_mode: 'HTML'
          })
        });
        
        if (response.ok) {
          console.log(`✅ Уведомление отправлено пользователю ${userId}`);
          results.push({ userId, status: 'sent', events_count: events.length });
        } else {
          const error = await response.text();
          console.error(`❌ Ошибка отправки пользователю ${userId}:`, error);
          results.push({ userId, status: 'failed', error });
        }
      } else {
        console.log(`📭 Нет событий для пользователя ${userId}`);
        results.push({ userId, status: 'no_events' });
      }
      
    } catch (error) {
      console.error(`❌ Ошибка обработки пользователя ${userId}:`, error);
      results.push({ userId, status: 'error', error: error.message });
    }
  }
  
  console.log('📊 Результаты отправки:', results);
  return results;
}

/**
 * Получает события пользователя из Google Sheets (через API или KV)
 */
async function getUserEvents(userId, env) {
  // В реальной реализации здесь будет обращение к Google Sheets API
  // или кэшированным данным в Cloudflare KV
  
  // Пример Mock данных
  return [
    {
      type: 'birthday',
      name: 'Иван Петров',
      date: '2025-08-17',
      phone: '+7 777 123 4567',
      notes: 'День рождения'
    }
  ];
}

/**
 * Форматирует ежедневное уведомление
 */
async function formatDailyNotification(events, localInfo) {
  const today = new Date().toLocaleDateString('ru-RU');
  
  let message = `🎉 <b>Поздравления на сегодня (${today})</b>\n\n`;
  
  for (const event of events) {
    message += `🎂 <b>${event.name}</b>\n`;
    message += `📞 ${event.phone}\n`;
    if (event.notes) {
      message += `💬 ${event.notes}\n`;
    }
    message += '\n';
  }
  
  message += `⏰ Уведомление отправлено в ${localInfo}\n`;
  message += `🤖 EventGREEN Bot`;
  
  return message;
}

// Пример wrangler.toml конфигурации:
/*
name = "eventgreen-notifications"
compatibility_date = "2023-10-30"

[env.production.vars]
TELEGRAM_BOT_TOKEN = "your_bot_token_here"

[[triggers.crons]]
cron = "53 09 * * *"

[[triggers.crons]] 
cron = "55 09 * * *"
*/