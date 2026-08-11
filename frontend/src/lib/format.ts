// Русские числительные и деньги. Живут отдельно, потому что «1 находок»
// и «24 узлов» вылезали на каждом экране по-своему.

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} ${one}`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} ${few}`;
  return `${n} ${many}`;
}

/** Суммы меньше цента показываем с точностью, иначе день работы = «$0.00». */
export function money(value: number): string {
  if (value > 0 && value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

export const days = (n: number) => plural(n, 'день', 'дня', 'дней');
export const nodes = (n: number) => plural(n, 'узел', 'узла', 'узлов');
export const links = (n: number) => plural(n, 'связь', 'связи', 'связей');
