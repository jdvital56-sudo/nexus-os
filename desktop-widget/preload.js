// Мостик между веб-страницей виджета и Electron. contextIsolation включён
// (nodeIntegration выключен) — страница не получает прямой доступ к Node
// или Electron API, только вот эти три конкретных действия, явно
// перечисленных здесь. Так безопаснее: страница грузится с localhost:5173,
// но даже если бы в неё что-то подсунули, «спрятать окно» и «выйти» —
// единственное, что она вообще может попросить сделать с самой системой.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('nexusWidgetAPI', {
  hide: () => ipcRenderer.send('widget:hide'),
  show: () => ipcRenderer.send('widget:show'),
  quit: () => ipcRenderer.send('widget:quit'),
  contextMenu: () => ipcRenderer.send('widget:context-menu'),
  // Какое сочетание клавиш реально занято (25.08.2026). Читать, а не
  // зашивать в подписи: «Alt+J» могло не зарегистрироваться, и подпись
  // обещала бы клавишу, которая ничего не делает — ровно на это фаундер и
  // пожаловался.
  shortcut: () => ipcRenderer.invoke('widget:shortcut'),
});
