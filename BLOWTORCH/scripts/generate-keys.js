import { execSync } from 'child_process';
import fs from 'fs';
import { fileURLToPath } from 'url';
import path from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.join(__dirname, '..');

// Generate private key if it doesn't exist
const privateKeyPath = path.join(rootDir, 'private.key');
if (!fs.existsSync(privateKeyPath)) {
    console.log('Generating private key...');
    execSync(`openssl genpkey -algorithm ED25519 -out "${privateKeyPath}"`);
    console.log('Private key generated at:', privateKeyPath);
}

// Generate certificate if it doesn't exist
const certPath = path.join(rootDir, 'cert.pem');
if (!fs.existsSync(certPath)) {
    console.log('Generating certificate...');
    execSync(`openssl req -x509 -key "${privateKeyPath}" -out "${certPath}" -days 365 -nodes -subj "/CN=localhost"`);
    console.log('Certificate generated at:', certPath);
}

console.log('Key generation complete!'); 