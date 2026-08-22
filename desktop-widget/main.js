// Плавающее окно Джарвиса поверх рабочего стола Windows.
//
// Шаг 1 из договорённости с фаундером 19.08.2026: держать разговор на виду,
// пока он переключается между окнами и вкладками. Никакого управления
// компьютером здесь нет и не будет — это отдельные, более осторожные шаги
// 2 и 3, за которые фаундер решил спрашивать подтверждение всегда.
//
// 19.08.2026, продолжение: «закрыть» теперь не закрывает окно насовсем, а
// прячет (win.hide) — страница внутри продолжает жить (см. WidgetScreen.tsx,
// stopOnHide: false). Настоящий выход — через правый клик по кольцу →
// «Выйти совсем».
//
// 19.08.2026, вечер: выяснилось, что «вернуть голосом» ненадёжно —
// облачное распознавание Chrome в Electron не работает вообще (нет ключа
// Google, зашитого только в настоящий Chrome), фаундер проверил вживую
// («Джарвис, ты слышишь меня?» — тишина). Спрятанное окно без другого
// способа вернуть было бы потеряно до перезапуска процесса целиком —
// поэтому здесь всегда есть надёжный путь без единого слова: глобальное
// сочетание клавиш, работает из любой программы, ничего не может сломаться
// в распознавании.
const SHOW_SHORTCUT = 'Alt+J';
//
// Окно грузит /widget — обычную страницу того же фронтенда Nexus OS
// (localhost:5173 в разработке), просто без сайдбара. Голос, память,
// разговор — тот же самый бэкенд на :8420, что и у полного экрана
// «Разговор»: это один и тот же Джарвис, просто в другом окне.

const { app, BrowserWindow, screen, ipcMain, Menu, globalShortcut } = require('electron');
const path = require('path');

// Окно шире, чем сам круг: в состоянии покоя видно только кольцо (прозрачный
// фон вокруг), при наведении внизу проявляется панель разговора — тот же
// приём, что у обычных плавающих ассистентов, не отдельное окно на каждое
// состояние.
const WIDTH = 300;
// 380, не 320 — при 320 нижняя строка (микрофон/наушник/поле ввода)
// обрезалась панелью (overflow-hidden впритык под контент), багрепорт
// фаундера 19.08.2026 со скриншотом. Запас, а не точный подгон под текущий
// текст — иначе любая новая строка подсказки снова всё обрежет.
const HEIGHT = 380;
const MARGIN = 24;

const WIDGET_URL = process.env.NEXUS_WIDGET_URL || 'http://localhost:5173/widget';

let win = null;

function createWindow() {
  const display = screen.getPrimaryDisplay();
  const { x, y, width, height } = display.workArea;

  win = new BrowserWindow({
    width: WIDTH,
    height: HEIGHT,
    x: x + width - WIDTH - MARGIN,
    y: y + height - HEIGHT - MARGIN,
    frame: false,
    resizable: false,
    transparent: true,
    backgroundColor: '#00000000',
    skipTaskbar: true,
    alwaysOnTop: true,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  win.setAlwaysOnTop(true, 'screen-saver');
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  win.loadURL(WIDGET_URL);
  win.once('ready-to-show', () => win.showInactive());

  // Крестик в самом окне прячет его, а не убивает процесс — 'closed' здесь
  // не наступает почти никогда, только через настоящий quit из меню
  win.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      win.hide();
    }
  });
}

ipcMain.on('widget:hide', () => win?.hide());

ipcMain.on('widget:show', showWindow);

ipcMain.on('widget:quit', () => {
  app.isQuitting = true;
  app.quit();
});

ipcMain.on('widget:context-menu', () => {
  if (!win) return;
  const menu = Menu.buildFromTemplate([
    { label: 'Спрятать', click: () => win.hide() },
    { type: 'separator' },
    { label: 'Выйти совсем', click: () => { app.isQuitting = true; app.quit(); } },
  ]);
  menu.popup({ window: win });
});

function showWindow() {
  if (!win) return;
  win.showInactive();
  win.setAlwaysOnTop(true, 'screen-saver');
}

app.whenReady().then(() => {
  createWindow();
  const ok = globalShortcut.register(SHOW_SHORTCUT, showWindow);
  if (!ok) console.error('[widget] не удалось занять сочетание', SHOW_SHORTCUT);
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
  app.quit();
});
