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
    sheet.getRange(1, 1, 1, 2).setValues([['Codigo_Barra', 'IdArticulo']]);
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
    const values = sheet.getRange(2, 1, lastRow - 1, 2).getDisplayValues();
    const items = values
      .filter(row => String(row[0]).trim() || String(row[1]).trim())
      .map(row => ({Codigo_Barra: String(row[0]).trim(), IdArticulo: String(row[1]).trim()}));
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
    if (body.action !== 'replace_tracking' || !Array.isArray(body.items)) {
      return jsonResponse_({ok: false, error: 'Solicitud inválida.'});
    }
    const seen = new Set();
    const rows = body.items
      .map(item => [String(item.Codigo_Barra || '').trim(), String(item.IdArticulo || '').trim()])
      .filter(row => {
        if (!row[0] && !row[1]) return false;
        const key = (row[1] || row[0]).toLocaleLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    const sheet = trackingSheet_();
    sheet.clearContents();
    sheet.getRange(1, 1, 1, 2).setValues([['Codigo_Barra', 'IdArticulo']]);
    if (rows.length) sheet.getRange(2, 1, rows.length, 2).setValues(rows);
    SpreadsheetApp.flush();
    return jsonResponse_({ok: true, count: rows.length});
  } catch (error) {
    return jsonResponse_({ok: false, error: String(error && error.message || error)});
  } finally {
    if (lock.hasLock()) lock.releaseLock();
  }
}
