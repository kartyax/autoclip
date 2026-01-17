// Electron Preload Script
// Provides secure bridge between renderer and main process

const { contextBridge, ipcRenderer } = require("electron");

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld("electronAPI", {
  // Send commands to Python backend
  startEngine: (payload) => ipcRenderer.invoke("start-engine", payload),
  stopEngine: () => ipcRenderer.invoke("stop-engine"),

  // File system operations
  selectFile: () => ipcRenderer.invoke("select-file"),
  selectFolder: () => ipcRenderer.invoke("select-folder"),

  // Receive events from Python backend
  onEvent: (callback) => {
    ipcRenderer.on("engine-event", (event, data) => callback(event, data));
  },

  // Remove event listeners
  removeEventListener: (channel) => {
    ipcRenderer.removeAllListeners(channel);
  },

  // Get app state
  getAppState: () => ipcRenderer.invoke("get-app-state"),

  // Update app state
  updateAppState: (state) => ipcRenderer.invoke("update-app-state", state),
});

// Log that preload script loaded
console.log("Preload script loaded successfully");
