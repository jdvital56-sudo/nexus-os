import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

// Два языка интерфейса. Устройство выбрано так, чтобы перевод можно было
// доделывать по частям, а не одним махом на пятнадцать экранов:
//
// ключ словаря — сама русская строка. Русский режим ничего не ищет и
// возвращает ключ как есть, английский — берёт перевод, а если его ещё нет,
// показывает русский. Непереведённая строка выглядит недоделанной, но
// экран не ломается и не показывает «missing.key.42».
//
// Данные не переводятся никогда: заметки, факты, названия задач остаются на
// том языке, на котором их записал человек. Переключается оболочка.

export type Lang = 'ru' | 'en';

const EN: Record<string, string> = {
  // Меню
  'Дашборд': 'Dashboard',
  'Разговор': 'Chat',
  'Второй мозг': 'Second brain',
  'Память': 'Memory',
  'Ночной прогон': 'Night run',
  'Скиллы': 'Skills',
  'Агенты': 'Agents',
  'Пантеон': 'Pantheon',
  'Задачи': 'Tasks',
  'Документы': 'Documents',
  'Артефакты': 'Artifacts',
  'Контент': 'Content',
  'Почта': 'Mail',
  'Календарь': 'Calendar',
  'Подписки': 'Subscriptions',
  'События': 'Events',
  'Настройки': 'Settings',
  'Личная операционная система': 'Personal operating system',

  // Общее
  'Повторить': 'Retry',
  'Отмена': 'Cancel',
  'Создать': 'Create',
  'Сохранить': 'Save',
  'Сохранено': 'Saved',
  'Найти': 'Search',
  'Обновить': 'Refresh',
  'Бэкенд недоступен. Запущен ли он на :8420?': 'Backend is unreachable. Is it running on :8420?',
  'Язык интерфейса': 'Interface language',

  // Разговор
  'Тот же Джарвис, что в Телеграме: общая память, общий характер. Нить разговора здесь своя.':
    'The same Jarvis as in Telegram: shared memory, shared character. The thread here is its own.',
  'Начать заново': 'Start over',
  'Спроси что угодно. Он помнит прошлые разговоры и твои заметки.':
    'Ask anything. It remembers past conversations and your notes.',
  'Сообщение…': 'Message…',
  'Отправить': 'Send',
  'Сочетание занято — возвращай голосом': 'Hotkey taken — bring it back by voice',
  'персона по смыслу': 'persona by meaning',
  'думаю…': 'thinking…',
  'Ответ не пришёл.': 'No answer came back.',
  'Собирает ответ: смотрит память, заметки и нить разговора.':
    'Composing the answer: memory, notes and the thread.',
  'Готов. Память общая с Телеграмом.': 'Ready. Memory shared with Telegram.',

  // Настройки
  'Что система читает при запуске. Меняется в файле .env — отсюда не редактируется намеренно: ключи не должны проходить через браузер.':
    'What the system reads at startup. Changed in .env — deliberately not editable here: keys must not pass through the browser.',
  'Где что лежит': 'Where things live',
  'Версия': 'Version',
  'Адрес API': 'API address',
  'Папка данных': 'Data folder',
  'Папка артефактов': 'Artifacts folder',
  'Файл токена': 'Token file',
  'Пределы и расписание': 'Limits and schedule',
  'Дневной бюджет на модели': 'Daily model budget',
  'Потолок ответа': 'Reply cap',
  'Расписание ведёт процесс': 'Schedule is held by process',
  'Автопилот Jarvis': 'Jarvis autopilot',
  'Что подключено': 'What is connected',
  'включён': 'on',
  'выключен': 'off',
  'подключено': 'connected',
  'нет': 'no',
  'никто': 'nobody',
};

const DICTS: Record<Lang, Record<string, string>> = { ru: {}, en: EN };

interface Ctx {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (text: string) => string;
}

const LanguageContext = createContext<Ctx>({ lang: 'ru', setLang: () => {}, t: (s) => s });

const STORAGE_KEY = 'nexus-os-lang';

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === 'en' || saved === 'ru' ? saved : 'ru';
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, lang);
    // Тег <html lang> НЕ переключаем на "en" вместе с этой кнопкой: перевод
    // покрывает пока полсотни строк, всё остальное честно остаётся русским
    // (см. комментарий вверху файла). Если сказать браузеру «это английская
    // страница» про экран, где почти всё по-русски, Chrome сам берётся
    // «переводить» уже русский текст и выдаёт бессмыслицу («Джарвис» →
    // «Гервис» и подобное) — багрепорт фаундера 19.08.2026. Тег остаётся
    // русским, пока перевод не покроет экран целиком по-настоящему.
    document.documentElement.lang = 'ru';
  }, [lang]);

  const t = (text: string) => DICTS[lang][text] ?? text;

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>
  );
}

export function useLang(): Ctx {
  return useContext(LanguageContext);
}

/** Сколько строк уже переведено — видно, сколько работы осталось. */
export function translationProgress(): { done: number } {
  return { done: Object.keys(EN).length };
}
