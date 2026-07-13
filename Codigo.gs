/**
 * Puente opcional para ETIQUETAS_SEGUIDAS.
 * El PDF se genera en Python y nunca depende de este servicio.
 */
const SPREADSHEET_ID = '1z1naxcQyryThMHj3H9K3xi27EDuugBPnFKrrwrJ8v1Y';
const TRACKING_SHEET = 'ETIQUETAS_SEGUIDAS';

function jsonResponse_(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function trackingSheet_() {
  const book = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = book.getSheetByName(TRACKING_SHEET);
  if (!sheet) {
    sheet = book.insertSheet(TRACKING_SHEET);
    sheet.getRange(1, 1, 1, 3).setValues([['Codigo_Barra', 'IdArticulo', 'Descripcion']]);
  }
  return sheet;
}

function doGet(event) {
  try {
    const action = (event && event.parameter && event.parameter.action) || 'health';
    if (action === 'health') {
      return jsonResponse_({ok: true, service: 'cotyland-etiquetas'});
    }
    if (action !== 'get_tracking') {
      return jsonResponse_({ok: false, error: 'Acción GET no permitida.'});
    }
    const sheet = trackingSheet_();
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return jsonResponse_({ok: true, items: []});
    const values = sheet.getRange(2, 1, lastRow - 1, 3).getDisplayValues();
    const items = values
      .filter(row => String(row[0]).trim() || String(row[1]).trim())
      .map(row => ({Codigo_Barra: String(row[0]).trim(), IdArticulo: String(row[1]).trim(), Descripcion: String(row[2]).trim()}));
    return jsonResponse_({ok: true, items: items});
  } catch (error) {
    return jsonResponse_({ok: false, error: String(error && error.message || error)});
  }
}

function doPost(event) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(20000);
    const body = JSON.parse((event && event.postData && event.postData.contents) || '{}');
    if (!['add_tracking', 'upsert_tracking', 'remove_tracking'].includes(body.action) || !Array.isArray(body.items)) {
      return jsonResponse_({ok: false, error: 'Solicitud inválida.'});
    }
    const sheet = trackingSheet_();
    const lastRow = sheet.getLastRow();
    const existing = lastRow < 2 ? [] : sheet.getRange(2, 1, lastRow - 1, 3).getDisplayValues();
    const norm = value => String(value || '').trim().toLocaleLowerCase();
    const incoming = body.items.map(item => [
      String(item.Codigo_Barra || '').trim(),
      String(item.IdArticulo || '').trim(),
      String(item.Descripcion || '').trim()
    ]).filter(row => row[0] || row[1]);
    if (body.action === 'remove_tracking') {
      const ids = new Set(incoming.map(row => norm(row[1])).filter(Boolean));
      const barcodes = new Set(incoming.map(row => norm(row[0])).filter(Boolean));
      const rowsToDelete = [];
      existing.forEach((row, index) => {
        if ((norm(row[1]) && ids.has(norm(row[1]))) || (!norm(row[1]) && norm(row[0]) && barcodes.has(norm(row[0])))) rowsToDelete.push(index + 2);
      });
      rowsToDelete.sort((a, b) => b - a).forEach(rowNumber => sheet.deleteRow(rowNumber));
      SpreadsheetApp.flush();
      return jsonResponse_({ok: true, removed: rowsToDelete.length, total: existing.length - rowsToDelete.length});
    }
    const existingIds = new Set(existing.map(row => norm(row[1])).filter(Boolean));
    const existingBarcodes = new Set(existing.map(row => norm(row[0])).filter(Boolean));
    const batchKeys = new Set();
    const additions = incoming.filter(row => {
      const id = norm(row[1]);
      const barcode = norm(row[0]);
      const key = id ? 'id:' + id : 'barcode:' + barcode;
      if (batchKeys.has(key) || (id && existingIds.has(id)) || (!id && barcode && existingBarcodes.has(barcode))) return false;
      batchKeys.add(key);
      return true;
    });
    if (additions.length) sheet.getRange(sheet.getLastRow() + 1, 1, additions.length, 3).setValues(additions);
    SpreadsheetApp.flush();
    return jsonResponse_({ok: true, added: additions.length, existing: incoming.length - additions.length, total: existing.length + additions.length});
  } catch (error) {
    return jsonResponse_({ok: false, error: String(error && error.message || error)});
  } finally {
    if (lock.hasLock()) lock.releaseLock();
  }
}
