import assert from 'node:assert/strict';
import test from 'node:test';
import { filterRows, queryRows } from '../ui/assets/query.js';

const rows = [
  { id: 'a', game_date: '2026-09-01', sword_score: 95, batter: 10, pitch_type: 'SL' },
  { id: 'b', game_date: '2026-09-02', sword_score: 120, batter: 11, pitch_type: null },
  { id: 'c', game_date: '2026-09-02', sword_score: 100, batter: 10, pitch_type: 'FF' },
];

test('numbers compare as numbers', () => {
  assert.deepEqual(filterRows(rows, { sword_score: 'gte.100' }).map((r) => r.id), ['b', 'c']);
  assert.deepEqual(filterRows(rows, { batter: 'eq.10' }).map((r) => r.id), ['a', 'c']);
});

test('several filters on one column all apply', () => {
  const found = filterRows(rows, { game_date: ['gte.2026-09-02', 'lt.2026-09-03'] });
  assert.deepEqual(found.map((r) => r.id), ['b', 'c']);
});

test('ids with dashes match exactly', () => {
  assert.equal(filterRows([{ id: '824300-20-3' }], { id: 'eq.824300-20-3' }).length, 1);
  assert.equal(filterRows([{ id: '824300-20-3' }], { id: 'eq.824300' }).length, 0);
});

test('nulls', () => {
  assert.deepEqual(filterRows(rows, { pitch_type: 'not.is.null' }).map((r) => r.id), ['a', 'c']);
  assert.deepEqual(filterRows(rows, { pitch_type: 'is.null' }).map((r) => r.id), ['b']);
});

test('sorting, paging and select', () => {
  const page = queryRows(rows, { select: 'id', order: 'game_date.desc,sword_score.asc', offset: 1, limit: 1 });
  assert.deepEqual(page.map((r) => r.id), ['b']);
});

test('an unknown filter fails loudly', () => {
  assert.throws(() => filterRows(rows, { id: 'like.a' }), /Unsupported/);
});
