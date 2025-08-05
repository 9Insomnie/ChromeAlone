// ChromeAlone Web Frontend Configuration
// This file contains all default configuration values
// Modify these values to customize the application for your environment

window.ChromeAloneConfig = {
  server: {
    defaultHost: "1.2.3.4",
    defaultPort: "1080"
  },
  auth: {
    defaultUsername: "admin",
    defaultPassword: "thiswillbechanged"
  },
  fileBrowser: {
    defaultStartPath: "c:\\"
  },
  ui: {
    autoRefreshInterval: 10000,
    taskHistoryLimit: 100,
    capturedDataLimit: 100
  }
};