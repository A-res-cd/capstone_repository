import { cpSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Bundle decoders/fonts so viewing a PDF never depends on a third-party CDN.
const source = new URL('../node_modules/pdfjs-dist/', import.meta.url);
const target = new URL('../public/pdfjs/', import.meta.url);
mkdirSync(target, { recursive: true });
for (const folder of ['cmaps', 'standard_fonts', 'wasm', 'iccs']) {
  cpSync(fileURLToPath(new URL(folder, source)), fileURLToPath(new URL(folder, target)), { recursive: true });
}
