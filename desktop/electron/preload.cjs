// The only bridge between the page and the desktop shell.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("friday", {
  /** Where the engine is listening and the token for it. */
  engine: () => ipcRenderer.invoke("engine:info"),
  /** Widget -> full view. */
  expand: () => ipcRenderer.send("window:expand"),
  /** Full view -> widget. */
  collapse: () => ipcRenderer.send("window:collapse"),
  /** Grow or shrink the widget window (for the approval card). */
  resizeWidget: (height) => ipcRenderer.send("widget:resize", height),
  quit: () => ipcRenderer.send("app:quit"),
});
