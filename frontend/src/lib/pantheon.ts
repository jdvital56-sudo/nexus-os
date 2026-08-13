/**
 * Канон имён Nexus OS — единственное место, где живут имена на экране.
 *
 * Зачем файл вообще нужен. В двух параллельных разговорах египетские имена
 * раздали по-разному: в одном Ра — это Джарвис, в другом — персона Орфей;
 * Анубис в одном куратор памяти, в другом сторож. В коде ни та, ни другая
 * версия не осела, но столкнуться они могли в любой момент.
 *
 * Причина столкновения — попытка назвать одним набором богов две разные
 * вещи: персон, с которыми человек разговаривает, и агентов, которые молча
 * работают в фоне. Здесь они разведены по слоям, и одно имя не может
 * значить двух вещей: проверка внизу файла роняет сборку на повторе.
 *
 * Технические ключи (`orpheus`, `curator`) сюда приходят из бэкенда и НЕ
 * переименовываются: они лежат в файлах данных на диске и в тестах, а
 * пользователь их не видит. Меняется только подпись.
 */

export type Layer = 'pantheon' | 'worker' | 'tab';

export interface Named {
  /** Ключ из бэкенда — как есть, без перевода */
  key: string;
  /** Что видит человек */
  title: string;
  /** Чем занимается — одной строкой */
  duty: string;
  layer: Layer;
  /** false только у Джарвиса: он не из египетской мифологии */
  egyptian: boolean;
}

/**
 * Слой 1 — Пантеон: с кем человек разговаривает.
 * Ключи совпадают с `name` в personas.json (сравнение регистронезависимое).
 */
export const PANTHEON: Named[] = [
  { key: 'orpheus', title: 'Ра', duty: 'Общий разговор, голос по умолчанию', layer: 'pantheon', egyptian: true },
  { key: 'architect', title: 'Птах', duty: 'Код и структуры данных', layer: 'pantheon', egyptian: true },
  { key: 'mercury', title: 'Гор', duty: 'Автоматизация и расписания', layer: 'pantheon', egyptian: true },
  { key: 'philosopher', title: 'Имхотеп', duty: 'Глубокий разбор, дорогие решения', layer: 'pantheon', egyptian: true },
  { key: 'labyrinth', title: 'Сешат', duty: 'Исследование и веб-поиск', layer: 'pantheon', egyptian: true },
  { key: 'sekhmet', title: 'Сехмет', duty: 'Безопасность и проверка рисков', layer: 'pantheon', egyptian: true },
  { key: 'bastet', title: 'Бастет', duty: 'Клиенты и лиды', layer: 'pantheon', egyptian: true },
];

/**
 * Слой 2 — работники: кто делает работу в фоне (AgentRole в бэкенде).
 *
 * Богов здесь намеренно нет. Если куратора памяти тоже назвать Анубисом,
 * человеку придётся каждый раз гадать, о ком речь — о стороже или о памяти.
 * Обычные русские слова читаются без расшифровки.
 */
export const WORKERS: Named[] = [
  { key: 'builder', title: 'Строитель', duty: 'Собирает и правит', layer: 'worker', egyptian: false },
  { key: 'librarian', title: 'Библиотекарь', duty: 'Раскладывает знания', layer: 'worker', egyptian: false },
  { key: 'reviewer', title: 'Рецензент', duty: 'Проверяет сделанное', layer: 'worker', egyptian: false },
  { key: 'researcher', title: 'Исследователь', duty: 'Собирает материал', layer: 'worker', egyptian: false },
  { key: 'monitor', title: 'Монитор', duty: 'Следит за показателями', layer: 'worker', egyptian: false },
  { key: 'curator', title: 'Куратор', duty: 'Гигиена памяти, ничего не удаляет', layer: 'worker', egyptian: false },
  { key: 'jarvis', title: 'Джарвис', duty: 'Распределяет работу между остальными', layer: 'worker', egyptian: false },
];

/** Слой 3 — три вкладки наверху. Джарвис здесь единственный не-египетский. */
export const TABS: Named[] = [
  { key: 'jarvis', title: 'Джарвис', duty: 'Голос, характер, второй мозг', layer: 'tab', egyptian: false },
  { key: 'thoth', title: 'Тот', duty: 'Телеграм и дом Пантеона', layer: 'tab', egyptian: true },
  { key: 'anubis', title: 'Анубис', duty: 'Сторож: следит, что всё живо', layer: 'tab', egyptian: true },
];

/**
 * Проверка на повтор имени — ради неё файл и существует.
 *
 * «Джарвис» законно встречается дважды: как работник (`worker`) и как
 * вкладка (`tab`) — это одна и та же сущность с двух сторон. Всё остальное
 * повторяться не должно, иначе мы снова получим двух «Ра».
 */
function assertNoClash(): void {
  const seen = new Map<string, Named>();
  for (const item of [...PANTHEON, ...WORKERS, ...TABS]) {
    const prev = seen.get(item.title);
    if (prev && !(prev.key === item.key)) {
      throw new Error(
        `Имя «${item.title}» занято дважды: ${prev.layer}/${prev.key} и ${item.layer}/${item.key}. ` +
          'Канон имён нарушен — см. комментарий в lib/pantheon.ts.',
      );
    }
    seen.set(item.title, item);
  }
}

assertNoClash();

const BY_KEY = new Map<string, Named>(
  [...PANTHEON, ...WORKERS].map((item) => [item.key.toLowerCase(), item]),
);

/**
 * Подпись для ключа с бэкенда. Незнакомый ключ возвращаем как есть:
 * новая персона, заведённая через API, должна показаться под своим именем,
 * а не потеряться под прочерком.
 */
export function titleOf(key: string): string {
  return BY_KEY.get(key.trim().toLowerCase())?.title ?? key;
}

export function dutyOf(key: string): string | null {
  return BY_KEY.get(key.trim().toLowerCase())?.duty ?? null;
}

/** true, если сущность оформляется в египетском стиле (у Джарвиса — false) */
export function isEgyptian(key: string): boolean {
  return BY_KEY.get(key.trim().toLowerCase())?.egyptian ?? true;
}
