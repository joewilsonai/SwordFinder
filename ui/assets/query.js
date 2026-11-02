// Filters rows the way the old database API did, so pages can keep asking for
// "sword_score=gte.90&order=game_date.desc" against a plain JSON file.

function compare(left, right) {
  const a = Number(left);
  const b = Number(right);
  if (left !== null && left !== '' && right !== '' && Number.isFinite(a) && Number.isFinite(b)) {
    return a - b;
  }
  return String(left ?? '').localeCompare(String(right ?? ''));
}

function matches(value, expression) {
  const text = String(expression);
  if (text === 'is.null') return value === null || value === undefined;
  if (text === 'not.is.null') return value !== null && value !== undefined;
  const dot = text.indexOf('.');
  const op = text.slice(0, dot);
  const operand = text.slice(dot + 1);
  if (value === null || value === undefined) return false;
  const order = compare(value, operand);
  switch (op) {
    case 'eq': return order === 0;
    case 'neq': return order !== 0;
    case 'gt': return order > 0;
    case 'gte': return order >= 0;
    case 'lt': return order < 0;
    case 'lte': return order <= 0;
    default: throw new Error(`Unsupported filter: ${text}`);
  }
}

const NOT_FILTERS = new Set(['select', 'order', 'limit', 'offset']);

export function filterRows(rows, params = {}) {
  const filters = Object.entries(params).filter(
    ([key, value]) => !NOT_FILTERS.has(key) && value !== undefined && value !== null && value !== '',
  );
  return rows.filter((row) => filters.every(([key, value]) => (
    (Array.isArray(value) ? value : [value]).every((expression) => matches(row[key], expression))
  )));
}

function sortRows(rows, order) {
  if (!order) return rows;
  const keys = String(order).split(',').map((part) => {
    const [column, direction] = part.split('.');
    return { column, sign: direction === 'desc' ? -1 : 1 };
  });
  return [...rows].sort((a, b) => {
    for (const { column, sign } of keys) {
      const result = compare(a[column], b[column]);
      if (result !== 0) return result * sign;
    }
    return 0;
  });
}

export function queryRows(rows, params = {}) {
  const sorted = sortRows(filterRows(rows, params), params.order);
  const offset = Number(params.offset || 0);
  const limit = params.limit === undefined ? sorted.length : Number(params.limit);
  return sorted.slice(offset, offset + limit);
}
