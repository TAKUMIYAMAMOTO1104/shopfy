/**
 * 美容室専用 Instagram投稿キャプション 30日分自動生成ツール
 *
 * 使い方:
 *   1. Googleスプレッドシートを開く
 *   2. 拡張機能 → Apps Script を開く
 *   3. このコードを貼り付ける
 *   4. スクリプトプロパティに GEMINI_API_KEY を設定
 *      （プロジェクト設定 → スクリプトプロパティ）
 *   5. スプレッドシートをリロード
 *   6. メニューから「キャプション生成」→「30日分一括生成」を実行
 */

const GEMINI_MODEL = 'gemini-2.0-flash';
const GEMINI_ENDPOINT = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`;

const SHEET_INPUT = '店舗情報';
const SHEET_OUTPUT = '生成キャプション';

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('キャプション生成')
    .addItem('店舗情報シートを初期化', 'initInputSheet')
    .addItem('30日分一括生成', 'generateMonthlyCaptions')
    .addItem('1日分だけ生成（テスト用）', 'generateSingleCaption')
    .addToUi();
}

function initInputSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_INPUT);
  if (!sheet) sheet = ss.insertSheet(SHEET_INPUT);
  sheet.clear();

  const rows = [
    ['項目', '入力値', '記入例'],
    ['店舗名', '', 'hair salon LUNA'],
    ['エリア', '', '東京都渋谷区'],
    ['コンセプト', '', '大人女性のための上質な空間 / 髪質改善特化'],
    ['ターゲット客層', '', '30〜40代女性 / OL・主婦'],
    ['得意メニュー', '', '髪質改善トリートメント、白髪ぼかしハイライト、顔まわりカット'],
    ['価格帯', '', 'カット6,600円 / カラー11,000円〜'],
    ['投稿トーン', '', '丁寧・親しみやすい / 絵文字多め'],
    ['ハッシュタグ固定', '', '#渋谷美容室 #髪質改善 #大人ヘアサロン'],
    ['NGワード', '', '激安、最安値'],
  ];
  sheet.getRange(1, 1, rows.length, 3).setValues(rows);
  sheet.getRange(1, 1, 1, 3).setFontWeight('bold').setBackground('#f0f0f0');
  sheet.setColumnWidth(1, 160);
  sheet.setColumnWidth(2, 360);
  sheet.setColumnWidth(3, 360);

  SpreadsheetApp.getUi().alert('「店舗情報」シートを作成しました。B列に情報を入力してください。');
}

function readSalonInfo() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_INPUT);
  if (!sheet) throw new Error('「店舗情報」シートがありません。先に「店舗情報シートを初期化」を実行してください。');

  const values = sheet.getRange(2, 1, 9, 2).getValues();
  const info = {};
  values.forEach(([key, val]) => { info[key] = (val || '').toString().trim(); });

  if (!info['店舗名']) throw new Error('店舗名が未入力です。');
  return info;
}

function getApiKey() {
  const key = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');
  if (!key) throw new Error('GEMINI_API_KEY が未設定です。プロジェクト設定 → スクリプトプロパティ から登録してください。');
  return key;
}

function buildPrompt(info, dayCount) {
  return `あなたは美容室専門のSNS運用プロです。以下の美容室の Instagram 投稿用キャプションを ${dayCount} 日分作成してください。

【店舗情報】
- 店舗名: ${info['店舗名']}
- エリア: ${info['エリア']}
- コンセプト: ${info['コンセプト']}
- ターゲット: ${info['ターゲット客層']}
- 得意メニュー: ${info['得意メニュー']}
- 価格帯: ${info['価格帯']}
- トーン: ${info['投稿トーン']}
- 固定ハッシュタグ: ${info['ハッシュタグ固定']}
- NGワード: ${info['NGワード']}

【投稿ネタの配分（${dayCount}日分でバランスよく）】
- スタイル紹介（カット/カラー/パーマ事例）: 40%
- お役立ち情報（ヘアケア/季節アドバイス）: 25%
- 店舗の雰囲気/スタッフ紹介: 15%
- お客様の声/ビフォーアフター: 10%
- キャンペーン/予約促進: 10%

【各キャプションの構成】
1. 冒頭フック（1行・絵文字あり）
2. 本文（150〜250文字・改行を入れて読みやすく）
3. 行動喚起（予約導線・コメント促進）
4. ハッシュタグ（固定タグ + 投稿内容に関連したタグ 計15〜25個）

【出力形式】必ず以下のJSON配列のみで返してください（前置き・後書き禁止）:
[
  {
    "day": 1,
    "category": "スタイル紹介",
    "theme": "髪質改善トリートメントの仕上がり紹介",
    "caption": "（フック・本文・CTA・ハッシュタグを全て含めた完成形のキャプション全文）",
    "image_idea": "撮影すべき写真の指示（例: サイドからのツヤ髪アップ写真）"
  }
]

NGワード「${info['NGワード']}」は絶対に使わないでください。`;
}

function callGemini(prompt) {
  const apiKey = getApiKey();
  const url = `${GEMINI_ENDPOINT}?key=${apiKey}`;
  const payload = {
    contents: [{ role: 'user', parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: 0.9,
      maxOutputTokens: 8192,
      responseMimeType: 'application/json',
    },
  };

  const res = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });

  const code = res.getResponseCode();
  const body = res.getContentText();
  if (code !== 200) throw new Error(`Gemini API エラー (${code}): ${body}`);

  const json = JSON.parse(body);
  const text = json?.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error('Gemini レスポンスが空です: ' + body);
  return text;
}

function parseCaptions(rawText) {
  let text = rawText.trim();
  if (text.startsWith('```')) {
    text = text.replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '');
  }
  const arr = JSON.parse(text);
  if (!Array.isArray(arr)) throw new Error('JSON配列ではありません');
  return arr;
}

function writeOutput(captions) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_OUTPUT);
  if (!sheet) sheet = ss.insertSheet(SHEET_OUTPUT);
  sheet.clear();

  const header = ['Day', '投稿予定日', 'カテゴリ', 'テーマ', 'キャプション', '撮影指示', 'ステータス'];
  sheet.getRange(1, 1, 1, header.length).setValues([header])
    .setFontWeight('bold').setBackground('#1a73e8').setFontColor('#ffffff');

  const today = new Date();
  const rows = captions.map((c, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() + i);
    return [
      c.day || (i + 1),
      Utilities.formatDate(d, Session.getScriptTimeZone(), 'yyyy/MM/dd (E)'),
      c.category || '',
      c.theme || '',
      c.caption || '',
      c.image_idea || '',
      '未投稿',
    ];
  });

  sheet.getRange(2, 1, rows.length, header.length).setValues(rows);
  sheet.setColumnWidth(1, 50);
  sheet.setColumnWidth(2, 130);
  sheet.setColumnWidth(3, 110);
  sheet.setColumnWidth(4, 220);
  sheet.setColumnWidth(5, 500);
  sheet.setColumnWidth(6, 280);
  sheet.setColumnWidth(7, 90);
  sheet.getRange(2, 5, rows.length, 1).setWrap(true).setVerticalAlignment('top');
  sheet.getRange(2, 6, rows.length, 1).setWrap(true).setVerticalAlignment('top');
  sheet.setFrozenRows(1);
}

function generateMonthlyCaptions() {
  const ui = SpreadsheetApp.getUi();
  try {
    const info = readSalonInfo();
    ui.alert('30日分のキャプションを生成します。30〜60秒ほどかかります。OKを押すと開始します。');

    const prompt = buildPrompt(info, 30);
    const raw = callGemini(prompt);
    const captions = parseCaptions(raw);

    if (captions.length < 25) {
      throw new Error(`生成数が少なすぎます（${captions.length}件）。再実行してください。`);
    }
    writeOutput(captions);
    ui.alert(`${captions.length}日分のキャプションを「生成キャプション」シートに出力しました。`);
  } catch (e) {
    ui.alert('エラー: ' + e.message);
  }
}

function generateSingleCaption() {
  const ui = SpreadsheetApp.getUi();
  try {
    const info = readSalonInfo();
    const prompt = buildPrompt(info, 1);
    const raw = callGemini(prompt);
    const captions = parseCaptions(raw);
    writeOutput(captions);
    ui.alert('1日分のテスト生成が完了しました。「生成キャプション」シートを確認してください。');
  } catch (e) {
    ui.alert('エラー: ' + e.message);
  }
}
