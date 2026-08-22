// Цвета и подписи типов узлов второго мозга — одно место на оба экрана
// (GraphScreen и Джарвис-фон), чтобы категория «память» не оказалась
// зелёной в одном месте и другим цветом в другом.

export const TYPE_COLORS: Record<string, string> = {
  memory: '#00DC82',
  concept: '#F5B642',
  document: '#3B82F6',
  file: '#38BDF8',
  task: '#A78BFA',
  agent: '#EC4899',
  decision: '#FB923C',
  session: '#94A3B8',
};

export const TYPE_LABELS: Record<string, string> = {
  memory: 'Память',
  concept: 'Понятия',
  document: 'Документы',
  file: 'Файлы',
  task: 'Задачи',
  agent: 'Агенты',
  decision: 'Решения',
  session: 'Сессии',
};

export function colorOfType(type: string): string {
  return TYPE_COLORS[type] ?? '#6B7280';
}

export function labelOfType(type: string): string {
  return TYPE_LABELS[type] ?? type;
}
