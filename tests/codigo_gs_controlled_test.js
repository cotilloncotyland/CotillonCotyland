const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

let rows = [['Codigo_Barra', 'IdArticulo', 'Descripcion'], ['00123', 'ART-1', 'Existente']];
const sheet = {
  getLastRow: () => rows.length,
  getRange: (row, col, count, width) => ({
    getDisplayValues: () => rows.slice(row - 1, row - 1 + count).map(item => item.slice(col - 1, col - 1 + width)),
    setValues: values => values.forEach((value, index) => { rows[row - 1 + index] = value.slice(); })
  }),
  deleteRow: row => rows.splice(row - 1, 1)
};
global.SpreadsheetApp = {openById: () => ({getSheetByName: () => sheet}), flush: () => {}};
global.LockService = {getScriptLock: () => ({waitLock: () => {}, hasLock: () => true, releaseLock: () => {}})};
global.ContentService = {
  MimeType: {JSON: 'json'},
  createTextOutput: text => ({text, setMimeType() { return this; }})
};
vm.runInThisContext(fs.readFileSync('Codigo.gs', 'utf8'));
const post = body => JSON.parse(doPost({postData: {contents: JSON.stringify(body)}}).text);

let result = post({action: 'upsert_tracking', items: [
  {Codigo_Barra: 'OTRO', IdArticulo: 'ART-1', Descripcion: 'Duplicado por Id'},
  {Codigo_Barra: '.002-AB', IdArticulo: 'ART-2', Descripcion: 'Nuevo'},
  {Codigo_Barra: '.002-AB', IdArticulo: 'ART-2', Descripcion: 'Duplicado en lote'}
]});
assert.deepStrictEqual({added: result.added, existing: result.existing, total: result.total}, {added: 1, existing: 2, total: 2});
assert.strictEqual(rows.length, 3);
assert.deepStrictEqual(rows[2], ['.002-AB', 'ART-2', 'Nuevo']);

result = post({action: 'remove_tracking', items: [{Codigo_Barra: '', IdArticulo: 'ART-1'}]});
assert.deepStrictEqual({removed: result.removed, total: result.total}, {removed: 1, total: 1});
assert.strictEqual(rows[1][1], 'ART-2');

result = post({action: 'remove_tracking', items: [{Codigo_Barra: '.002-AB', IdArticulo: 'ART-2'}]});
assert.deepStrictEqual({removed: result.removed, total: result.total}, {removed: 1, total: 0});
assert.strictEqual(rows.length, 1);
console.log('CODIGO_GS_CONTROLLED_OK');
