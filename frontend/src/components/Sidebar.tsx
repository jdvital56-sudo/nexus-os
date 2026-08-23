import { Link, useLocation } from 'react-router-dom';
import { useLang } from '../lib/i18n';
import { TABS } from '../lib/pantheon';
import { 
  LayoutDashboard, 
  Brain, 
  Sparkles, 
  Bot, 
  FileText, 
  Settings,
  Activity,
  Network,
  Calendar,
  CheckSquare,
  Workflow,
  Drama,
  CreditCard,
  Package,
  MessageSquare,
  Mail,
  Lightbulb
} from 'lucide-react';

// Названия по-русски: система личная, и половина экранов уже говорит
// по-русски. Смесь языков в одном меню читается хуже любого из них.
const menuItems = [
  { path: '/', label: 'Дашборд', icon: LayoutDashboard },
  { path: '/chat', label: 'Разговор', icon: MessageSquare },
  { path: '/graph', label: 'Второй мозг', icon: Network },
  { path: '/memory', label: 'Память', icon: Brain },
  { path: '/dream-review', label: 'Ночной прогон', icon: Calendar },
  { path: '/skills', label: 'Скиллы', icon: Sparkles },
  { path: '/agents', label: 'Агенты', icon: Bot },
  { path: '/personas', label: 'Пантеон', icon: Drama },
  { path: '/tasks', label: 'Задачи', icon: CheckSquare },
  { path: '/ideas', label: 'Идеи', icon: Lightbulb },
  { path: '/documents', label: 'Документы', icon: FileText },
  { path: '/artifacts', label: 'Артефакты', icon: Package },
  { path: '/pipeline', label: 'Контент', icon: Workflow },
  { path: '/mail', label: 'Почта', icon: Mail },
  { path: '/calendar', label: 'Календарь', icon: Calendar },
  { path: '/wallet', label: 'Подписки', icon: CreditCard },
  { path: '/activity', label: 'События', icon: Activity },
  { path: '/settings', label: 'Настройки', icon: Settings },
];

// Египетские иероглифы для двух богов и латинская J для Джарвиса —
// разница видна ещё до того, как прочитаешь подпись.
const TAB_GLYPH: Record<string, string> = {
  thoth: '𓅝',   // ибис — Тот
  anubis: '𓃣',  // шакал — Анубис
  jarvis: 'J',
};

// Куда ведёт каждая вкладка. У Анубиса маршрута нет — по канону визуала
// для него ещё не существует макета, карточка честно остаётся неактивной,
// а не ведёт в пустоту.
const TAB_ROUTE: Record<string, string | null> = {
  jarvis: '/chat',
  thoth: '/personas',
  anubis: null,
};

export default function Sidebar() {
  const location = useLocation();
  const { lang, setLang, t } = useLang();

  return (
    // Колонка, а не absolute-подвал: вкладки агентов удлинили меню, и
    // прижатый к низу блок языка начинал наезжать на последние пункты.
    <aside className="fixed left-0 top-0 flex h-screen w-64 flex-col overflow-y-auto border-r border-gray-800 bg-darker">
      <div className="p-6">
        <h1 className="font-display text-2xl text-primary-bright">Nexus OS</h1>
        <p className="mt-1 text-xs uppercase tracking-[0.1em] text-gray-600">
          {t('Личная операционная система')}
        </p>
      </div>

      {/* Три вкладки агентов — три разные вещи в системе, не синонимы.
          Джарвис оформлен графитом: он единственный не из египетской
          мифологии, и это видно глазом, а не только по подписи. */}
      <div className="px-3">
        <p className="mb-2 px-2 text-[0.62rem] uppercase tracking-[0.14em] text-gray-600">
          {t('Агенты')}
        </p>
        {TABS.map((tab) => {
          const route = TAB_ROUTE[tab.key] ?? null;
          const active = route !== null && location.pathname === route;
          const classes = `mb-1.5 flex items-start gap-2 rounded-md border px-2 py-1.5 transition-colors duration-200 ${
            tab.egyptian
              ? `border-gray-800 text-primary-bright ${route ? 'hover:bg-gray-800' : ''}`
              : `border-jarvis-line bg-jarvis-panel/40 text-jarvis-bright ${route ? 'hover:bg-jarvis-panel/70' : ''}`
          } ${active ? 'ring-1 ring-primary/50' : ''} ${route ? 'cursor-pointer' : 'cursor-default opacity-60'}`;
          const glyph = (
            <span
              className={`grid h-6 w-6 shrink-0 place-items-center rounded border font-display text-xs ${
                tab.egyptian
                  ? 'border-gray-800 bg-primary/10'
                  : 'border-jarvis-line bg-jarvis-line/25'
              }`}
              aria-hidden
            >
              {TAB_GLYPH[tab.key] ?? tab.title[0]}
            </span>
          );
          const label = (
            <span className="min-w-0">
              <span className="block text-sm leading-tight">{t(tab.title)}</span>
              <span className="mt-0.5 block text-[0.68rem] leading-snug text-gray-600">
                {route ? t(tab.duty) : `${t(tab.duty)} · ${t('экран ещё не готов')}`}
              </span>
            </span>
          );

          return route ? (
            <Link key={tab.key} to={route} className={classes}>
              {glyph}
              {label}
            </Link>
          ) : (
            <div key={tab.key} className={classes} title={t('Экран для этой вкладки ещё не сделан')}>
              {glyph}
              {label}
            </div>
          );
        })}
      </div>

      <nav className="mt-4">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path;
          
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center px-6 py-3 text-sm transition-colors ${
                isActive
                  ? 'bg-primary/10 text-primary border-r-2 border-primary'
                  : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800'
              }`}
            >
              <Icon className="w-5 h-5 mr-3" />
              {t(item.label)}
            </Link>
          );
        })}
      </nav>
      
      <div className="mt-auto border-t border-gray-800 p-6">
        <div className="mb-3 flex gap-1" title={t('Язык интерфейса')}>
          {(['ru', 'en'] as const).map((code) => (
            <button
              key={code}
              onClick={() => setLang(code)}
              className={`cursor-pointer rounded px-2 py-1 text-xs uppercase transition-colors duration-200 focus:outline-none focus:ring-1 focus:ring-primary ${
                lang === code ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:text-gray-100'
              }`}
            >
              {code}
            </button>
          ))}
        </div>
        <div className="flex items-center space-x-3">
          <div className="h-2 w-2 animate-pulse rounded-full bg-green-500 motion-reduce:animate-none" />
          <span className="text-xs text-gray-400">{lang === 'ru' ? 'Система на связи' : 'System online'}</span>
        </div>
      </div>
    </aside>
  );
}
