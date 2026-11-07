const fs = require('fs');
const token = fs.readFileSync(__dirname + '/session-token.txt', 'utf8').trim();

module.exports = {
  apps: [{
    name: 'pocket-alfred-serve',
    script: '/home/leo/.hermes/hermes-agent/venv/bin/python3',
    args: '/home/leo/.hermes/hermes-agent/venv/bin/hermes -p alfred-tools serve --isolated --port 9215 --host 127.0.0.1 --skip-build',
    env: { HERMES_DASHBOARD_SESSION_TOKEN: token, HERMES_DASHBOARD_PUBLIC_URL: 'https://pocket.kranium.me', HERMES_DESKTOP: '1' },
    max_memory_restart: '2G',
  }]
};
